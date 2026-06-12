"""Read-only Polymarket CLOB order book depth fetcher.

Fetches live order book depth for every registry market flagged
``data_collection.fetch_orderbook`` and emits packet-ready artifacts to
``live/``. This module is strictly read-only: GET requests against public,
unauthenticated CLOB endpoints only — no order placement, no signing, no
credentials anywhere.

Endpoints (verified against docs.polymarket.com, June 2026):
- ``GET /book?token_id=`` on clob.polymarket.com (public, 1500 req/10s)
- ``GET /markets/{condition_id}`` for stale token re-resolution

The batch ``POST /books`` endpoint exists but is deliberately not used:
``ReadOnlyHttpClient`` permits GET only as a repo-wide safety invariant, and
sequential fetches with spacing stay far below the rate limit.
"""

from __future__ import annotations

import json
import re
import time as time_module
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from urllib.error import HTTPError

from polyberg.collectors.polymarket_account import AccountImportError, ReadOnlyHttpClient
from polyberg.collectors.polymarket_clob import (
    CLOB_API_BASE_URL,
    ClobCollectorError,
    fetch_clob_market,
    fetch_order_book,
)
from polyberg.config import get_timezone, repo_path
from polyberg.loaders import load_market_registry, load_open_orders
from polyberg.models import Market, OpenOrders

BOOK_DEPTH = 10
REQUEST_SPACING_SECONDS = 0.2
RETRY_BACKOFF_SECONDS = (0.5, 1.0, 2.0)
QUEUE_POSITION_NOTE = (
    "APPROXIMATE: public books do not expose intra-level queue position. "
    "approx_shares_ahead = cumulative shares at strictly better prices "
    "+ max(0, level size - my size)."
)

SleepFn = Callable[[float], None]


class BookUnavailableError(RuntimeError):
    """A token's book could not be fetched (after stale re-resolution)."""


@dataclass
class BookLevel:
    price: float
    shares: float
    cum_shares: float
    cum_notional: float
    my_resting: bool = False
    my_shares: float = 0.0
    approx_shares_ahead: float | None = None

    def to_dict(self) -> dict[str, object]:
        out: dict[str, object] = {
            "price": self.price,
            "shares": self.shares,
            "cum_shares": round(self.cum_shares, 4),
            "cum_notional": round(self.cum_notional, 4),
            "my_resting": self.my_resting,
        }
        if self.my_resting:
            out["my_shares"] = self.my_shares
            out["approx_shares_ahead"] = self.approx_shares_ahead
        return out


@dataclass
class SideBook:
    """Computed view of one outcome token's book (top BOOK_DEPTH levels)."""

    token_id: str
    bids: list[BookLevel]
    asks: list[BookLevel]
    best_bid: float | None
    best_ask: float | None
    spread: float | None
    midpoint: float | None
    last_trade_price: float | None
    tick_size: str | None
    book_imbalance: float | None
    my_orders_beyond_depth: list[dict[str, object]] = field(default_factory=list)
    # Open orders whose price matched no live level — filled/cancelled/stale export.
    my_orders_not_in_book: list[dict[str, float]] = field(default_factory=list)

    def to_dict(self) -> dict[str, object]:
        return {
            "token_id": self.token_id,
            "best_bid": self.best_bid,
            "best_ask": self.best_ask,
            "spread": self.spread,
            "midpoint": self.midpoint,
            "last_trade_price": self.last_trade_price,
            "tick_size": self.tick_size,
            "book_imbalance": self.book_imbalance,
            "bids": [level.to_dict() for level in self.bids],
            "asks": [level.to_dict() for level in self.asks],
            "my_orders_beyond_depth": self.my_orders_beyond_depth,
            "my_orders_not_in_book": self.my_orders_not_in_book,
        }


@dataclass
class MarketBooks:
    market_id: str
    fetched_at: str
    status: str  # "ok" | "unavailable"
    preferred_side: str
    error: str | None = None
    sides: dict[str, SideBook] = field(default_factory=dict)

    def to_dict(self) -> dict[str, object]:
        out: dict[str, object] = {
            "market_id": self.market_id,
            "fetched_at": self.fetched_at,
            "status": self.status,
            "preferred_side": self.preferred_side,
        }
        if self.error is not None:
            out["error"] = self.error
        out["sides"] = {side: book.to_dict() for side, book in self.sides.items()}
        return out


def default_books_json_path() -> Path:
    return repo_path("live", "order_books.json")


def default_books_md_path() -> Path:
    return repo_path("live", "order_books.md")


def default_token_map_path() -> Path:
    return repo_path("live", "token_map.json")


def default_session_starter_path() -> Path:
    return repo_path("live", "session_starter.md")


def session_starter_template_path() -> Path:
    return repo_path("prompts", "session_starter_template.md")


# --- token map cache ---------------------------------------------------------


def load_token_map(path: Path) -> dict[str, dict[str, str]]:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    markets = raw.get("markets")
    return markets if isinstance(markets, dict) else {}


def save_token_map(path: Path, token_map: dict[str, dict[str, str]], now: datetime) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"updated_at": now.isoformat(), "markets": token_map}
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def resolve_tokens(
    market: Market,
    token_map: dict[str, dict[str, str]],
) -> tuple[str | None, str | None]:
    """Token ids for (YES, NO): re-resolved cache wins over the static registry."""
    cached = token_map.get(market.market_id, {})
    yes = cached.get("yes_token_id") or market.yes_token_id
    no = cached.get("no_token_id") or market.no_token_id
    return yes, no


def reresolve_tokens(
    market: Market,
    http: ReadOnlyHttpClient | None = None,
) -> tuple[str, str]:
    """Re-resolve YES/NO token ids from the CLOB market record (condition_id).

    Raises BookUnavailableError when the market has no condition_id or the
    CLOB record does not carry both outcomes.
    """
    if not market.condition_id:
        raise BookUnavailableError(
            f"{market.market_id}: no condition_id in registry; cannot re-resolve tokens"
        )
    try:
        record = fetch_clob_market(market.condition_id, http=http)
    except ClobCollectorError as exc:
        raise BookUnavailableError(
            f"{market.market_id}: token re-resolution failed: {exc}"
        ) from exc
    yes_token: str | None = None
    no_token: str | None = None
    for token in record.get("tokens") or []:
        if not isinstance(token, dict):
            continue
        outcome = str(token.get("outcome") or "").strip().lower()
        if outcome == "yes":
            yes_token = str(token.get("token_id") or "") or None
        elif outcome == "no":
            no_token = str(token.get("token_id") or "") or None
    if not yes_token or not no_token:
        raise BookUnavailableError(
            f"{market.market_id}: CLOB market record for {market.condition_id} "
            "does not expose both YES and NO tokens"
        )
    return yes_token, no_token


# --- fetching with retry -----------------------------------------------------


def _http_status(exc: AccountImportError) -> int | None:
    cause = exc.__cause__
    if isinstance(cause, HTTPError):
        return cause.code
    match = re.search(r"HTTP (\d{3})", str(exc))
    return int(match.group(1)) if match else None


def fetch_book_with_retry(
    token_id: str,
    http: ReadOnlyHttpClient | None = None,
    sleep: SleepFn = time_module.sleep,
) -> dict:
    """GET /book with retry-and-backoff on 429/5xx. 404 raises immediately.

    Raises BookUnavailableError carrying the failure reason.
    """
    last_error = ""
    for backoff in (*RETRY_BACKOFF_SECONDS, None):
        try:
            return fetch_order_book(token_id, http=http)
        except ClobCollectorError as exc:
            cause = exc.__cause__
            status = _http_status(cause) if isinstance(cause, AccountImportError) else None
            if status is None:
                match = re.search(r"HTTP (\d{3})", str(exc))
                status = int(match.group(1)) if match else None
            last_error = str(exc)
            retryable = status == 429 or (status is not None and 500 <= status <= 599)
            if not retryable or backoff is None:
                raise BookUnavailableError(last_error) from exc
            sleep(backoff)
    raise BookUnavailableError(last_error)


def _book_is_empty(book: dict) -> bool:
    return not book.get("bids") and not book.get("asks")


# --- level math ---------------------------------------------------------------


def _parse_levels(raw_levels: list, descending: bool) -> list[tuple[float, float]]:
    levels = []
    for entry in raw_levels or []:
        try:
            price = float(entry.get("price"))
            size = float(entry.get("size"))
        except (AttributeError, TypeError, ValueError):
            continue
        levels.append((price, size))
    return sorted(levels, key=lambda pair: pair[0], reverse=descending)


def build_ladder(
    raw_levels: list,
    side: str,
    my_orders: list[tuple[float, float]],
    depth: int = BOOK_DEPTH,
) -> tuple[list[BookLevel], list[dict[str, object]], list[dict[str, float]]]:
    """Top-``depth`` ladder for one side ("bids" or "asks") of one token book.

    ``my_orders`` is a list of (price, shares) resting on this side. Returns
    (ladder, my_orders_beyond_depth, my_orders_not_in_book). Queue position is
    computed over the FULL sorted side so an order deeper than ``depth`` still
    gets an estimate. An open order whose price matches no live level at all is
    reported in the third element — it was likely filled, cancelled, or the
    open-orders export is stale.
    """
    if side not in ("bids", "asks"):
        raise ValueError(f"side must be 'bids' or 'asks', got {side!r}")
    sorted_levels = _parse_levels(raw_levels, descending=side == "bids")

    mine_by_price: dict[float, float] = {}
    for price, shares in my_orders:
        key = round(price, 6)
        mine_by_price[key] = mine_by_price.get(key, 0.0) + shares

    ladder: list[BookLevel] = []
    beyond_depth: list[dict[str, object]] = []
    cum_shares = 0.0
    cum_notional = 0.0
    for index, (price, size) in enumerate(sorted_levels):
        cum_shares += size
        cum_notional += price * size
        key = round(price, 6)
        my_shares = mine_by_price.pop(key, 0.0)
        level = BookLevel(
            price=price,
            shares=size,
            cum_shares=cum_shares,
            cum_notional=cum_notional,
            my_resting=my_shares > 0,
            my_shares=my_shares,
        )
        if my_shares > 0:
            better_shares = cum_shares - size
            level.approx_shares_ahead = round(better_shares + max(0.0, size - my_shares), 4)
        if index < depth:
            ladder.append(level)
        elif my_shares > 0:
            beyond_depth.append(
                {
                    "side": "BID" if side == "bids" else "ASK",
                    "price": price,
                    "my_shares": my_shares,
                    "approx_shares_ahead": level.approx_shares_ahead or 0.0,
                }
            )
    not_in_book = [
        {"price": price, "my_shares": shares} for price, shares in sorted(mine_by_price.items())
    ]
    return ladder, beyond_depth, not_in_book


def build_side_book(
    token_id: str,
    book: dict,
    my_bids: list[tuple[float, float]],
    my_asks: list[tuple[float, float]],
    depth: int = BOOK_DEPTH,
) -> SideBook:
    bids, bids_beyond, bids_missing = build_ladder(
        book.get("bids") or [], "bids", my_bids, depth=depth
    )
    asks, asks_beyond, asks_missing = build_ladder(
        book.get("asks") or [], "asks", my_asks, depth=depth
    )

    best_bid = bids[0].price if bids else None
    best_ask = asks[0].price if asks else None
    two_sided = best_bid is not None and best_ask is not None
    spread = round(best_ask - best_bid, 6) if two_sided else None
    midpoint = round((best_bid + best_ask) / 2, 6) if two_sided else None

    bid_notional = bids[-1].cum_notional if bids else 0.0
    ask_notional = asks[-1].cum_notional if asks else 0.0
    total_notional = bid_notional + ask_notional
    imbalance = round(bid_notional / total_notional, 4) if total_notional > 0 else None

    last_trade = book.get("last_trade_price")
    try:
        last_trade_price = float(last_trade) if last_trade not in (None, "") else None
    except (TypeError, ValueError):
        last_trade_price = None

    tick_size = book.get("tick_size")
    return SideBook(
        token_id=token_id,
        bids=bids,
        asks=asks,
        best_bid=best_bid,
        best_ask=best_ask,
        spread=spread,
        midpoint=midpoint,
        last_trade_price=last_trade_price,
        tick_size=str(tick_size) if tick_size is not None else None,
        book_imbalance=imbalance,
        my_orders_beyond_depth=bids_beyond + asks_beyond,
        my_orders_not_in_book=bids_missing + asks_missing,
    )


def my_orders_for(open_orders: OpenOrders, market_id: str, outcome: str) -> tuple[
    list[tuple[float, float]], list[tuple[float, float]]
]:
    """(resting bids, resting asks) on ``outcome``'s token book for one market.

    A buy order on an outcome rests on that outcome token's bid side; a sell
    order rests on its ask side.
    """
    bids = [
        (order.price, order.shares)
        for order in open_orders.buy_orders
        if order.market_id == market_id and order.side == outcome
    ]
    asks = [
        (order.price, order.shares)
        for order in open_orders.sell_orders
        if order.market_id == market_id and order.side == outcome
    ]
    return bids, asks


# --- per-market orchestration --------------------------------------------------


def fetch_market_books(
    market: Market,
    open_orders: OpenOrders,
    token_map: dict[str, dict[str, str]],
    now_fn: Callable[[], datetime],
    http: ReadOnlyHttpClient | None = None,
    sleep: SleepFn = time_module.sleep,
    depth: int = BOOK_DEPTH,
) -> MarketBooks:
    """Fetch and compute both outcome books for one market.

    Stale-cache guard: a 404 or fully-empty book triggers one token
    re-resolution via the market's condition_id before the market is declared
    unavailable. Never raises — failures come back as status="unavailable".
    """
    fetched_at = now_fn().isoformat()
    result = MarketBooks(
        market_id=market.market_id,
        fetched_at=fetched_at,
        status="ok",
        preferred_side=market.preferred_side,
    )

    yes_token, no_token = resolve_tokens(market, token_map)
    tokens = {"YES": yes_token, "NO": no_token}
    if not yes_token or not no_token:
        missing = ", ".join(side for side, token in tokens.items() if not token)
        try:
            yes_token, no_token = reresolve_tokens(market, http=http)
        except BookUnavailableError as exc:
            result.status = "unavailable"
            result.error = f"missing token ids ({missing}); {exc}"
            return result
        tokens = {"YES": yes_token, "NO": no_token}
        token_map[market.market_id] = {
            "condition_id": market.condition_id or "",
            "yes_token_id": yes_token,
            "no_token_id": no_token,
            "cached_at": fetched_at,
        }

    raw_books: dict[str, dict] = {}
    stale = False
    errors: list[str] = []
    for side, token_id in tokens.items():
        try:
            book = fetch_book_with_retry(token_id or "", http=http, sleep=sleep)
        except BookUnavailableError as exc:
            stale = True
            errors.append(f"{side}: {exc}")
            continue
        finally:
            sleep(REQUEST_SPACING_SECONDS)
        if _book_is_empty(book):
            stale = True
            errors.append(f"{side}: book is empty on both sides")
            continue
        raw_books[side] = book

    if stale:
        # Stale-cache guard: invalidate and re-resolve once, then retry the
        # missing sides with the fresh token ids.
        try:
            yes_token, no_token = reresolve_tokens(market, http=http)
            token_map[market.market_id] = {
                "condition_id": market.condition_id or "",
                "yes_token_id": yes_token,
                "no_token_id": no_token,
                "cached_at": fetched_at,
            }
            tokens = {"YES": yes_token, "NO": no_token}
            for side in ("YES", "NO"):
                if side in raw_books:
                    continue
                try:
                    book = fetch_book_with_retry(tokens[side], http=http, sleep=sleep)
                except BookUnavailableError as exc:
                    errors.append(f"{side} (after re-resolve): {exc}")
                    continue
                finally:
                    sleep(REQUEST_SPACING_SECONDS)
                if _book_is_empty(book):
                    errors.append(f"{side} (after re-resolve): book is empty on both sides")
                    continue
                raw_books[side] = book
        except BookUnavailableError as exc:
            errors.append(str(exc))

    for side, book in raw_books.items():
        my_bids, my_asks = my_orders_for(open_orders, market.market_id, side)
        result.sides[side] = build_side_book(
            tokens[side] or "", book, my_bids, my_asks, depth=depth
        )

    if len(raw_books) < 2:
        result.status = "unavailable"
        result.error = "; ".join(errors) or "book fetch failed"
    return result


def fetch_all_books(
    registry_path: Path | None = None,
    open_orders_path: Path | None = None,
    token_map_path: Path | None = None,
    market_ids: list[str] | None = None,
    http: ReadOnlyHttpClient | None = None,
    sleep: SleepFn = time_module.sleep,
    now_fn: Callable[[], datetime] | None = None,
    depth: int = BOOK_DEPTH,
) -> list[MarketBooks]:
    """Fetch books for every registry market flagged data_collection.fetch_orderbook.

    One market failing never kills the run: it comes back status="unavailable".
    """
    if now_fn is None:
        now_fn = lambda: datetime.now(get_timezone())  # noqa: E731
    registry = load_market_registry(registry_path)
    open_orders = load_open_orders(open_orders_path, registry=registry)
    client = http or ReadOnlyHttpClient(CLOB_API_BASE_URL)

    map_path = token_map_path or default_token_map_path()
    token_map = load_token_map(map_path)
    map_before = json.dumps(token_map, sort_keys=True)

    selected = [
        market
        for market in registry.markets
        if (market_ids is None or market.market_id in market_ids)
        and market.data_collection is not None
        and market.data_collection.fetch_orderbook
    ]

    results = [
        fetch_market_books(
            market, open_orders, token_map, now_fn, http=client, sleep=sleep, depth=depth
        )
        for market in selected
    ]

    if json.dumps(token_map, sort_keys=True) != map_before:
        save_token_map(map_path, token_map, now_fn())
    return results


# --- artifacts -----------------------------------------------------------------


def write_books_json(results: list[MarketBooks], path: Path, now: datetime) -> Path:
    payload = {
        "generated_at": now.isoformat(),
        "queue_position_note": QUEUE_POSITION_NOTE,
        "markets": {result.market_id: result.to_dict() for result in results},
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return path


def _format_shares(value: float) -> str:
    return f"{value:,.0f}" if value == int(value) else f"{value:,.2f}"


def _side_summary_line(outcome: str, book: SideBook) -> str:
    def fmt(value: float | None) -> str:
        return "—" if value is None else f"{value:.3f}"

    imbalance = "—" if book.book_imbalance is None else f"{book.book_imbalance:.2f}"
    return (
        f"- {outcome}: bid {fmt(book.best_bid)} / ask {fmt(book.best_ask)} · "
        f"spread {fmt(book.spread)} · mid {fmt(book.midpoint)} · "
        f"last {fmt(book.last_trade_price)} · bid-imbalance {imbalance}"
    )


def _render_ladder_table(book: SideBook) -> str:
    lines = [
        "| | Price | Shares | Cum shares | Cum $ |",
        "| --- | ---: | ---: | ---: | ---: |",
    ]
    for level in reversed(book.asks):
        marker = "ASK •" if level.my_resting else "ASK"
        lines.append(
            f"| {marker} | {level.price:.3f} | {_format_shares(level.shares)} | "
            f"{_format_shares(level.cum_shares)} | {level.cum_notional:,.2f} |"
        )
    spread = "—" if book.spread is None else f"{book.spread:.3f}"
    mid = "—" if book.midpoint is None else f"{book.midpoint:.3f}"
    lines.append(f"| | _spread {spread}_ | _mid {mid}_ | | |")
    for level in book.bids:
        marker = "BID •" if level.my_resting else "BID"
        lines.append(
            f"| {marker} | {level.price:.3f} | {_format_shares(level.shares)} | "
            f"{_format_shares(level.cum_shares)} | {level.cum_notional:,.2f} |"
        )
    if not book.asks:
        lines.insert(2, "| ASK | _none — empty side_ | | | |")
    if not book.bids:
        lines.append("| BID | _none — empty side_ | | | |")
    return "\n".join(lines)


def _render_my_resting_notes(book: SideBook) -> list[str]:
    notes = []
    for label, levels in (("BID", book.bids), ("ASK", book.asks)):
        for level in levels:
            if level.my_resting:
                notes.append(
                    f"  - • {label} {level.price:.3f}: my "
                    f"{_format_shares(level.my_shares)} shares, "
                    f"≈{_format_shares(level.approx_shares_ahead or 0.0)} shares ahead "
                    "(APPROXIMATE)"
                )
    for entry in book.my_orders_beyond_depth:
        notes.append(
            f"  - • {entry['side']} {entry['price']:.3f} (beyond top {BOOK_DEPTH}): my "
            f"{_format_shares(entry['my_shares'])} shares, "
            f"≈{_format_shares(entry['approx_shares_ahead'])} shares ahead (APPROXIMATE)"
        )
    for entry in book.my_orders_not_in_book:
        notes.append(
            f"  - ⚠ {entry['price']:.3f}: my {_format_shares(entry['my_shares'])} shares "
            "NOT FOUND in live book — filled, cancelled, or stale open-orders export"
        )
    return notes


def render_books_markdown(results: list[MarketBooks], now: datetime) -> str:
    live_ids = [result.market_id for result in results if result.status == "ok"]
    sections = [
        "## Live Order Books",
        f"- Generated: {now.isoformat()}",
        f"- Markets with live books: {', '.join(live_ids) if live_ids else 'NONE'}",
        f"- Queue positions are {QUEUE_POSITION_NOTE}",
        "- Rule: no live book = no order. Do not price orders on markets marked "
        "BOOK UNAVAILABLE.",
    ]
    for result in results:
        if result.status != "ok":
            sections.append(
                f"### {result.market_id} — BOOK UNAVAILABLE — do not price orders\n"
                f"- fetched_at: {result.fetched_at}\n"
                f"- error: {result.error}"
            )
            continue
        preferred = result.sides.get(result.preferred_side)
        other_outcome = "YES" if result.preferred_side == "NO" else "NO"
        other = result.sides.get(other_outcome)
        block = [
            f"### {result.market_id} — {result.preferred_side} book "
            f"(preferred side) · fetched_at {result.fetched_at}"
        ]
        if other is not None:
            block.append(_side_summary_line(other_outcome, other))
        if preferred is not None:
            block.append(_side_summary_line(result.preferred_side, preferred))
            block.append("")
            block.append(_render_ladder_table(preferred))
            notes = [
                f"  - [{result.preferred_side} book]" + note.removeprefix("  -")
                for note in _render_my_resting_notes(preferred)
            ]
            if other is not None:
                notes.extend(
                    f"  - [{other_outcome} book]" + note.removeprefix("  -")
                    for note in _render_my_resting_notes(other)
                )
            if notes:
                block.append("- My resting orders (•):")
                block.extend(notes)
        sections.append("\n".join(block))
    return "\n\n".join(sections).strip() + "\n"


def write_books_markdown(results: list[MarketBooks], path: Path, now: datetime) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render_books_markdown(results, now), encoding="utf-8")
    return path


def write_session_starter(
    results: list[MarketBooks],
    now: datetime,
    template_path: Path | None = None,
    output_path: Path | None = None,
) -> Path | None:
    """Fill the session starter template; field [3] gets the live-book market ids."""
    template_file = template_path or session_starter_template_path()
    if not template_file.exists():
        return None
    live_ids = [result.market_id for result in results if result.status == "ok"]
    text = template_file.read_text(encoding="utf-8")
    text = text.replace("{{generated_at}}", now.isoformat())
    text = text.replace(
        "{{live_book_markets}}", ", ".join(live_ids) if live_ids else "NONE — do not price orders"
    )
    out = output_path or default_session_starter_path()
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(text, encoding="utf-8")
    return out


def run_fetch_books(
    market_ids: list[str] | None = None,
    depth: int = BOOK_DEPTH,
    json_path: Path | None = None,
    md_path: Path | None = None,
    token_map_path: Path | None = None,
    http: ReadOnlyHttpClient | None = None,
    sleep: SleepFn = time_module.sleep,
    now: datetime | None = None,
) -> tuple[list[MarketBooks], list[Path]]:
    """Full pipeline: fetch every flagged market's books and write all artifacts."""
    if now is None:
        now = datetime.now(get_timezone())
    results = fetch_all_books(
        market_ids=market_ids,
        token_map_path=token_map_path,
        http=http,
        sleep=sleep,
        now_fn=lambda: datetime.now(get_timezone()),
        depth=depth,
    )
    written = [
        write_books_json(results, json_path or default_books_json_path(), now),
        write_books_markdown(results, md_path or default_books_md_path(), now),
    ]
    starter = write_session_starter(results, now)
    if starter is not None:
        written.append(starter)
    return results, written
