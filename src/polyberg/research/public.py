"""Public discovery and allowlisted normalization; never loads personal-position APIs."""

from __future__ import annotations

import json
import math
import re
from urllib.parse import quote, unquote, urlencode, urlsplit

from polyberg.collectors.polymarket_gamma import search_events
from polyberg.http import HttpReadError, ReadOnlyHttpClient
from polyberg.research.models import (
    BookLevel,
    CollectedMarket,
    Discovery,
    Event,
    Identification,
    MarketActivity,
    MarketBook,
    Outcome,
    OutcomeBook,
    Quote,
    RulesInput,
    digest,
    utcnow,
)

GAMMA = "https://gamma-api.polymarket.com"
CLOB = "https://clob.polymarket.com"
DATA = "https://data-api.polymarket.com"
OPEN_INTEREST_BATCH = 20
BOOK_DEPTH = 10


class PublicDataError(ValueError):
    """Safe, fixed diagnostics: never include upstream payloads or transport exceptions."""


def string(value: object) -> str | None:
    # Do not stringify dicts/lists: arbitrary nested objects must never enter exports.
    return value if isinstance(value, str) else str(value) if type(value) is int else None


def array(value: object) -> list:
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except ValueError:
            return []
    return value if isinstance(value, list) else []


def price(value: object) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float, str)):
        return None
    try:
        number = float(value)
        return number if math.isfinite(number) and 0 <= number <= 1 else None
    except ValueError:
        return None


def number(value: object, low: float | None = None, high: float | None = None) -> float | None:
    """Finite numeric field (Gamma sends some as strings); out-of-range values stay missing."""
    if isinstance(value, bool) or not isinstance(value, (int, float, str)):
        return None
    try:
        result = float(value)
    except ValueError:
        return None
    if not math.isfinite(result) or (low is not None and result < low):
        return None
    return None if high is not None and result > high else result


def book_levels(
    raw_levels: object, side: str, warnings: list[str]
) -> list[tuple[float, float | None]]:
    """(price, size) pairs in upstream order; malformed prices are omitted with a warning."""
    if not isinstance(raw_levels, list):
        warnings.append(f"Malformed {side}")
        raise PublicDataError("Malformed order book levels")
    levels = []
    for level in raw_levels:
        p = price(level.get("price")) if isinstance(level, dict) else None
        if p is None:
            warnings.append(f"Malformed {side} level omitted")
        else:
            levels.append((p, number(level.get("size"), low=0)))
    return levels


def activity(raw: dict, at: str, source_api_url: str) -> MarketActivity:
    def first(*keys: str, low: float | None = 0, high: float | None = None) -> float | None:
        for key in keys:
            value = number(raw.get(key), low, high)
            if value is not None:
                return value
        return None

    return MarketActivity(
        retrieved_at=at,
        volume_total=first("volumeNum", "volume"),
        volume_24h=first("volume24hr"),
        volume_1w=first("volume1wk"),
        liquidity=first("liquidityNum", "liquidity"),
        price_change_1d=first("oneDayPriceChange", low=-1, high=1),
        price_change_1w=first("oneWeekPriceChange", low=-1, high=1),
        spread=first("spread", high=1),
        source_urls=[source_api_url],
    )


def market_identity(
    raw: dict, event_id: str | None = None, event_slug: str | None = None
) -> Identification:
    mid = string(raw.get("id"))
    if not mid or not mid.isdigit():
        raise PublicDataError("Market is missing a Gamma market ID")
    slug = string(raw.get("slug"))
    parents = array(raw.get("events"))
    if not event_slug and len(parents) == 1 and isinstance(parents[0], dict):
        event_slug = string(parents[0].get("slug"))
    page_url = None
    if slug:
        path = (
            f"{quote(event_slug, safe='')}/{quote(slug, safe='')}"
            if event_slug
            else quote(slug, safe="")
        )
        page_url = f"https://polymarket.com/event/{path}"
    version = string(raw.get("version"))
    # Pre-versioned Gamma CTF responses are recognized only by their explicit token array.
    protocol = version or ("v1" if array(raw.get("clobTokenIds")) else None)
    labels = array(raw.get("outcomes"))
    tokens, positions = array(raw.get("clobTokenIds")), array(raw.get("positionIds"))
    outcomes = []
    for index, label in enumerate(labels):
        if not isinstance(label, str):
            continue
        token = string(tokens[index]) if index < len(tokens) else None
        position = string(positions[index]) if index < len(positions) else None
        asset = position if protocol == "v2" else token if protocol == "v1" else None
        outcomes.append(
            Outcome(
                outcome_id=f"{mid}:{index}",
                index=index,
                label=label,
                token_id=token,
                position_id=position,
                asset_id=asset,
            )
        )
    lifecycle = "unknown"
    if raw.get("archived") is True:
        lifecycle = "archived"
    elif raw.get("closed") is True:
        lifecycle = "closed"
    elif raw.get("active") is True:
        lifecycle = "active"
    elif raw.get("active") is False:
        lifecycle = "inactive"
    return Identification(
        market_id=mid,
        event_id=event_id,
        slug=slug,
        question=string(raw.get("question")) or string(raw.get("title")) or "Untitled market",
        condition_id=string(raw.get("conditionId")),
        question_id=string(raw.get("questionID")),
        protocol=protocol,
        lifecycle=lifecycle,
        trading_start=string(raw.get("startDate")),
        trading_end=string(raw.get("endDate")),
        page_url=page_url,
        api_url=f"{GAMMA}/markets/{quote(mid, safe='')}",
        outcomes=outcomes,
    )


def normalize_market(
    raw: dict,
    at: str,
    event_id: str | None = None,
    source_api_url: str | None = None,
    event_slug: str | None = None,
) -> CollectedMarket:
    identity = market_identity(raw, event_id, event_slug)
    source_api_url = source_api_url or identity.api_url
    displayed = array(raw.get("outcomePrices"))
    warnings = []
    if not identity.outcomes:
        warnings.append("Outcome labels unavailable")
    if len(identity.outcomes) != len(array(raw.get("outcomes"))):
        warnings.append("Malformed outcome labels omitted; outcome collection incomplete")
    if identity.protocol not in {"v1", "v2"}:
        warnings.append("Unsupported or missing market protocol; public asset IDs unavailable")
    if len(displayed) != len(identity.outcomes):
        warnings.append("Incomplete displayed-price distribution; prices are not normalized")
    rules = None
    # Gamma's market description is the market rules. Event text is never a fallback.
    text = raw.get("description")
    if isinstance(text, str) and text.strip():
        rules = RulesInput(
            text=text,
            text_sha256=digest(text),
            api_url=source_api_url,
            page_url=identity.page_url,
            resolution_source=string(raw.get("resolutionSource")),
            resolution_status=string(raw.get("umaResolutionStatus")),
        )
    else:
        warnings.append("Market rules unavailable from public source")
    quotes = []
    for outcome in identity.outcomes:
        p = price(displayed[outcome.index]) if outcome.index < len(displayed) else None
        quotes.append(
            Quote(
                outcome_id=outcome.outcome_id,
                displayed_price=p,
                displayed_at=at if p is not None else None,
                source_urls=[source_api_url],
                warnings=[] if p is not None else ["Displayed price unavailable"],
            )
        )
    return CollectedMarket(
        identification=identity,
        retrieved_at=at,
        quotes=quotes,
        rules=rules,
        activity=activity(raw, at, source_api_url),
        warnings=warnings,
    )


def normalize_event(
    raw: dict, at: str, source_api_url: str | None = None
) -> tuple[Event, list[CollectedMarket]]:
    eid = string(raw.get("id"))
    if not eid or not eid.isdigit():
        raise PublicDataError("Event is missing a Gamma event ID")
    slug = string(raw.get("slug"))
    source_api_url = source_api_url or f"{GAMMA}/events/{quote(eid, safe='')}"
    children = array(raw.get("markets"))
    markets, warnings = [], []
    for child in children:
        try:
            if not isinstance(child, dict):
                raise PublicDataError("Malformed child contract")
            markets.append(normalize_market(child, at, eid, source_api_url, slug))
        except PublicDataError:
            warnings.append("A child contract could not be identified; event collection incomplete")
    if not children:
        warnings.append("Child contracts unavailable; event collection incomplete")
    event = Event(
        event_id=eid,
        slug=slug,
        title=string(raw.get("title")) or "Untitled event",
        description=string(raw.get("description")),
        page_url=f"https://polymarket.com/event/{quote(slug, safe='')}" if slug else None,
        api_url=source_api_url,
        retrieved_at=at,
        expected_market_ids=sorted({m.identification.market_id for m in markets}),
        contracts=[m.identification for m in markets],
        warnings=warnings,
    )
    return event, markets


class PublicClient:
    def __init__(
        self,
        gamma: ReadOnlyHttpClient | None = None,
        clob: ReadOnlyHttpClient | None = None,
        data: ReadOnlyHttpClient | None = None,
    ):
        self.gamma = gamma or ReadOnlyHttpClient(GAMMA, timeout=15)
        self.clob = clob or ReadOnlyHttpClient(CLOB, timeout=15)
        self.data = data or ReadOnlyHttpClient(DATA, timeout=15)

    def _get(self, path: str, params: dict | None = None) -> object:
        try:
            return self.gamma.get_json(path, params=params)
        except (HttpReadError, OSError, TimeoutError) as exc:
            raise PublicDataError("Public metadata request failed") from exc

    def search(self, query: str, include_closed: bool = False) -> Discovery:
        try:
            events = search_events(query=query, include_closed=include_closed, http=self.gamma)
        except (RuntimeError, OSError, TimeoutError) as exc:
            raise PublicDataError("Public search failed") from exc
        result = Discovery()
        at = utcnow()
        for raw in events:
            try:
                event, markets = normalize_event(raw, at)
                result.events.append(event)
                result.markets.extend(markets)
            except PublicDataError:
                result.warnings.append("A search result was missing its public identity")
        return result

    @staticmethod
    def _matches(raw: object) -> list[dict]:
        if isinstance(raw, list):
            return [m for m in raw if isinstance(m, dict)]
        return [raw] if isinstance(raw, dict) and raw.get("id") is not None else []

    def resolve(self, reference: str) -> Discovery:
        ref, child = reference.strip(), None
        kind, value = "slug", ref
        if "://" in ref:
            url = urlsplit(ref)
            if (
                url.scheme != "https"
                or url.hostname not in {"polymarket.com", "www.polymarket.com"}
                or url.username
                or url.password
                or url.port not in {None, 443}
            ):
                raise PublicDataError("Use an https polymarket.com market or event URL")
            parts = [unquote(p) for p in url.path.strip("/").split("/")]
            if len(parts) not in {2, 3} or parts[0] not in {"event", "market"}:
                raise PublicDataError("Unsupported public market URL path")
            if parts[0] == "market" and len(parts) != 2:
                raise PublicDataError("Unsupported market URL path")
            kind, value = parts[:2]
            child = parts[2] if len(parts) == 3 else None
        elif ":" in ref:
            kind, value = ref.split(":", 1)
            if kind not in {"market", "event", "condition", "slug"}:
                raise PublicDataError("Use market:, event:, condition: or slug: identifiers")
        elif ref.startswith("0x"):
            raise PublicDataError("Condition IDs require the explicit condition: prefix")
        elif ref.isdigit():
            kind = "market"
        if not value or not re.fullmatch(r"[A-Za-z0-9_-]+", value):
            raise PublicDataError("Invalid public reference")
        event_matches, market_matches = [], []
        event_source = f"{GAMMA}/events?{urlencode({'slug': value})}"
        market_source = f"{GAMMA}/markets?{urlencode({'slug': value})}"
        if kind == "event":
            event_source = f"{GAMMA}/events/{value}" if value.isdigit() else event_source
            event_matches = self._matches(
                self._get(
                    f"/events/{value}" if value.isdigit() else "/events",
                    None if value.isdigit() else {"slug": value},
                )
            )
        elif kind in {"market", "condition"}:
            if kind == "condition":
                if not re.fullmatch(r"0x[0-9a-fA-F]{64}", value):
                    raise PublicDataError("Condition ID must contain 64 hexadecimal digits")
                path, params = "/markets", {"condition_ids": value}
            else:
                path = f"/markets/{value}" if value.isdigit() else "/markets"
                params = None if value.isdigit() else {"slug": value}
            market_matches = self._matches(self._get(path, params))
            market_source = GAMMA + path + (f"?{urlencode(params)}" if params else "")
        else:
            event_matches = self._matches(self._get("/events", {"slug": value}))
            market_matches = self._matches(self._get("/markets", {"slug": value}))
        if len(event_matches) + len(market_matches) > 1:
            raise PublicDataError("Ambiguous reference; select an explicit event: or market: ID")
        at = utcnow()
        if event_matches:
            if value.isdigit() and kind == "event" and string(event_matches[0].get("id")) != value:
                raise PublicDataError("Public event identity mismatch")
            event, markets = normalize_event(event_matches[0], at, event_source)
            if child:
                markets = [m for m in markets if m.identification.slug == child]
                if len(markets) != 1:
                    raise PublicDataError("Child contract not uniquely present in event")
            return Discovery(events=[event], markets=markets)
        if market_matches:
            raw = market_matches[0]
            if kind == "market" and value.isdigit() and string(raw.get("id")) != value:
                raise PublicDataError("Public market identity mismatch")
            events = array(raw.get("events"))
            parent = events[0] if len(events) == 1 and isinstance(events[0], dict) else None
            eid = string(parent.get("id")) if parent else None
            result = Discovery(markets=[normalize_market(raw, at, eid, market_source)])
            if parent and eid:
                # A single contract still needs complete parent membership for an event packet.
                try:
                    parents = self._matches(self._get(f"/events/{eid}"))
                    if len(parents) != 1 or string(parents[0].get("id")) != eid:
                        raise PublicDataError("Public parent event unavailable")
                    event, _ = normalize_event(parents[0], utcnow())
                except PublicDataError:
                    event, _ = normalize_event(parent, at)
                    event.retrieved_at = None
                    event.warnings.append("Full parent event collection unavailable")
                result.events.append(event)
            elif len(events) > 1:
                result.markets[0].warnings.append(
                    "Parent event ambiguous; select an explicit event"
                )
            return result
        raise PublicDataError("No public match; use research search and select an explicit ID")

    def collect_quotes(self, market: CollectedMarket) -> CollectedMarket:
        for outcome, quote_data in zip(market.identification.outcomes, market.quotes, strict=True):
            if not outcome.asset_id:
                quote_data.warnings.append("Public outcome asset ID unavailable")
                continue
            params = {"token_id": outcome.asset_id}
            book_url = f"{CLOB}/book?{urlencode(params)}"
            try:
                raw = self.clob.get_json("/book", params=params)
                if not isinstance(raw, dict):
                    raise PublicDataError("Malformed book")
                # Verify returned identity when supplied. Keep unknown payload fields out.
                asset = string(raw.get("asset_id"))
                if asset and asset != outcome.asset_id:
                    raise PublicDataError("Book identity mismatch")
                levels = [
                    [p for p, _ in book_levels(raw.get(side), side, quote_data.warnings)]
                    for side in ("bids", "asks")
                ]
                quote_data.best_bid = max(levels[0]) if levels[0] else None
                quote_data.best_ask = min(levels[1]) if levels[1] else None
                quote_data.book_timestamp = string(raw.get("timestamp"))
                quote_data.book_retrieved_at = utcnow()
                quote_data.source_urls.append(book_url)
                if quote_data.best_bid is None or quote_data.best_ask is None:
                    quote_data.warnings.append("Incomplete order book")
                elif quote_data.best_bid > quote_data.best_ask:
                    quote_data.warnings.append("Crossed order book")
            except (RuntimeError, ValueError, OSError, TimeoutError):
                quote_data.warnings.append("Public order book unavailable")
            for path, key, attr, time_attr in [
                ("/midpoint", "mid", "midpoint", "midpoint_retrieved_at"),
                ("/last-trade-price", "price", "last_trade", "last_trade_retrieved_at"),
            ]:
                try:
                    raw = self.clob.get_json(path, params=params)
                    value = price(raw.get(key)) if isinstance(raw, dict) else None
                    if value is None:
                        raise PublicDataError("Public price unavailable")
                    setattr(quote_data, attr, value)
                    setattr(quote_data, time_attr, utcnow())
                    quote_data.source_urls.append(f"{CLOB}{path}?{urlencode(params)}")
                except (RuntimeError, ValueError, OSError, TimeoutError):
                    quote_data.warnings.append(f"Public {attr} unavailable")
        return market

    def collect_open_interest(self, markets: list[CollectedMarket]) -> None:
        """Batched Data API open interest. Failure leaves the value missing, never the refresh."""
        pending: dict[str, list[MarketActivity]] = {}
        for market in markets:
            if market.activity is None:
                continue
            cid = market.identification.condition_id
            if cid and re.fullmatch(r"0x[0-9a-fA-F]{64}", cid):
                pending.setdefault(cid.lower(), []).append(market.activity)
            else:
                market.activity.warnings.append("Open interest needs a public condition ID")
        conditions = sorted(pending)
        for start in range(0, len(conditions), OPEN_INTEREST_BATCH):
            chunk = conditions[start : start + OPEN_INTEREST_BATCH]
            params = {"condition": ",".join(chunk)}
            values: dict[str, float] | None = {}
            try:
                raw = self.data.get_json("/v2/oi", params=params)
                rows = raw.get("data") if isinstance(raw, dict) else None
                if not isinstance(rows, list):
                    raise PublicDataError("Malformed open interest")
                for row in rows:
                    cid = string(row.get("condition_id")) if isinstance(row, dict) else None
                    value = number(row.get("value"), low=0) if cid else None
                    if cid and value is not None:
                        values[cid.lower()] = value
            except (RuntimeError, ValueError, OSError, TimeoutError):
                values = None
            at, url = utcnow(), f"{DATA}/v2/oi?{urlencode(params)}"
            for cid in chunk:
                for record in pending[cid]:
                    if values is None:
                        record.warnings.append("Public open interest unavailable")
                    elif cid not in values:
                        record.warnings.append("Open interest not reported for this condition")
                    else:
                        record.open_interest = values[cid]
                        record.open_interest_retrieved_at = at
                        record.source_urls.append(url)

    def order_book(self, identity: Identification) -> MarketBook:
        """On-demand top-of-book depth per outcome. A live view: nothing is persisted."""
        books = []
        for outcome in identity.outcomes:
            book = OutcomeBook(
                outcome_id=outcome.outcome_id, label=outcome.label, asset_id=outcome.asset_id
            )
            books.append(book)
            if not outcome.asset_id:
                book.warnings.append("Public outcome asset ID unavailable")
                continue
            params = {"token_id": outcome.asset_id}
            try:
                raw = self.clob.get_json("/book", params=params)
                if not isinstance(raw, dict):
                    raise PublicDataError("Malformed book")
                asset = string(raw.get("asset_id"))
                if asset and asset != outcome.asset_id:
                    raise PublicDataError("Book identity mismatch")
                sides = {}
                for side in ("bids", "asks"):
                    levels = book_levels(raw.get(side), side, book.warnings)
                    sized = [(p, size) for p, size in levels if size is not None]
                    if len(sized) != len(levels):
                        book.warnings.append(f"{side.capitalize()} level without size omitted")
                    # Never depend on upstream ordering: best bid is highest, best ask lowest.
                    sized.sort(key=lambda level: level[0], reverse=side == "bids")
                    sides[side] = sized
            except (RuntimeError, ValueError, OSError, TimeoutError):
                book.warnings.append("Public order book unavailable")
                continue
            for side, sized in sides.items():
                total, depth = 0.0, []
                for p, size in sized[:BOOK_DEPTH]:
                    total += size
                    depth.append(BookLevel(price=p, size=size, cumulative=total))
                setattr(book, side, depth)
                setattr(book, f"{side[:-1]}_levels", len(sized))
            book.best_bid = sides["bids"][0][0] if sides["bids"] else None
            book.best_ask = sides["asks"][0][0] if sides["asks"] else None
            if book.best_bid is not None and book.best_ask is not None:
                book.spread = round(book.best_ask - book.best_bid, 6)
                book.book_midpoint = round((book.best_ask + book.best_bid) / 2, 6)
                if book.spread < 0:
                    book.warnings.append("Crossed order book")
            else:
                book.warnings.append("Incomplete order book")
            # The book's last_trade_price is market-wide (identical for every outcome token,
            # verified live 2026-10-27), so it is not shown as an outcome's last trade.
            book.tick_size = number(raw.get("tick_size"), low=0)
            book.min_order_size = number(raw.get("min_order_size"), low=0)
            book.book_timestamp = string(raw.get("timestamp"))
            book.retrieved_at = utcnow()
            book.source_url = f"{CLOB}/book?{urlencode(params)}"
        return MarketBook(market_id=identity.market_id, outcomes=books)
