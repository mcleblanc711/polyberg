from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from polyberg.books import filter_books_markdown
from polyberg.config import get_catalyst_window_hours, get_max_context_age_hours
from polyberg.lifecycle import MarketTypeFilter, packet_market_ids
from polyberg.models import (
    Market,
    MarketRegistry,
    MarketSnapshot,
    OpenOrders,
    Order,
    Portfolio,
)
from polyberg.packet_builder.catalysts import filter_catalysts, parse_catalysts
from polyberg.packet_builder.collect_state import PacketState, collect_packet_state

# Constraint keys that must hold for every research session, regardless of what
# the local live_state.yaml happens to contain. These are surfaced verbatim in
# both packets so neither model can drift toward market orders or automation.
SAFETY_CONSTRAINT_KEYS = ("no_market_orders", "use_sell_ladders", "avoid_99c_dispute_tax")


@dataclass
class CanonicalPacket:
    """Model-agnostic, fully structured packet state.

    Both the GPT and Claude renderers consume this object and nothing else, so
    the factual layer is guaranteed identical between exports. Only instruction
    framing and layout differ downstream.
    """

    packet_generated_at: str
    source_timestamps: dict[str, str | None]
    freshness_warnings: list[str]
    missing_info: list[str]
    # blocking_warnings must be resolved before any trade recommendation.
    # Each entry names the specific position and the failure reason.
    blocking_warnings: list[str]
    constraints: dict[str, object]
    portfolio: dict[str, object]
    exposure_summary: list[dict[str, object]]
    # True when thesis_buckets were all empty and rule_key was used as fallback.
    exposure_is_fallback: bool
    concentration_warnings: list[str]
    open_orders: dict[str, object]
    market_registry: list[dict[str, object]]
    market_snapshot: list[dict[str, object]] | None
    catalysts: dict[str, list[str]]
    trader_notes: list[str]
    unresolved_missing_information: list[str]
    # Per-market live-data coverage over the active set: a market is priceable iff
    # it has an order book present with status ok and a fresh fetched_at. Books
    # carry provenance — they ARE the live data; there is no separate snapshot gate.
    priceable_markets: list[str] = field(default_factory=list)
    unpriceable_markets: list[str] = field(default_factory=list)
    raw_notes: list[str] = field(default_factory=list)
    # Live order book section from `polyberg fetch-books` (None when not run):
    # generated_at, markets_with_live_books, unavailable_markets,
    # fetched_at_by_market, and the packet-ready markdown body.
    order_books: dict[str, object] | None = None

    def to_dict(self) -> dict[str, object]:
        return {
            "packet_generated_at": self.packet_generated_at,
            "source_timestamps": self.source_timestamps,
            "freshness_warnings": self.freshness_warnings,
            "missing_info": self.missing_info,
            "blocking_warnings": self.blocking_warnings,
            "constraints": self.constraints,
            "portfolio": self.portfolio,
            "exposure_summary": self.exposure_summary,
            "exposure_is_fallback": self.exposure_is_fallback,
            "concentration_warnings": self.concentration_warnings,
            "open_orders": self.open_orders,
            "market_registry": self.market_registry,
            "market_snapshot": self.market_snapshot,
            "catalysts": self.catalysts,
            "trader_notes": self.trader_notes,
            "unresolved_missing_information": self.unresolved_missing_information,
            "priceable_markets": self.priceable_markets,
            "unpriceable_markets": self.unpriceable_markets,
            "order_books": self.order_books,
        }

    def compact_state(self) -> dict[str, object]:
        """A trimmed JSON-safe view for the machine-readable tail of a packet.

        Carries the facts a model needs to reason about positions and gates
        without the prose; deliberately omits long catalyst text.
        """
        return {
            "packet_generated_at": self.packet_generated_at,
            "source_timestamps": self.source_timestamps,
            "constraints": self.constraints,
            "freshness_warnings": self.freshness_warnings,
            "missing_info": self.missing_info,
            "blocking_warnings": self.blocking_warnings,
            "portfolio": {
                "as_of": self.portfolio["as_of"],
                "portfolio_value": self.portfolio["portfolio_value"],
                "cash_available": self.portfolio["cash_available"],
                "positions": [
                    {
                        "market_id": p["market_id"],
                        "side": p["side"],
                        "band_label": p.get("band_label"),
                        "shares": p["shares"],
                        "avg_price": p["avg_price"],
                        "mark_price": p["mark_price"],
                        "current_value": p["current_value"],
                        "thesis_bucket": p["thesis_bucket"],
                    }
                    for p in self.portfolio["positions"]  # type: ignore[union-attr]
                ],
            },
            "exposure_summary": self.exposure_summary,
            "exposure_is_fallback": self.exposure_is_fallback,
            "concentration_warnings": self.concentration_warnings,
            "open_orders": {
                "as_of": self.open_orders["as_of"],
                "buys": self.open_orders["buys"],
                "sells": self.open_orders["sells"],
            },
            "priceable_markets": self.priceable_markets,
            "unpriceable_markets": self.unpriceable_markets,
        }

    def compact_json(self) -> str:
        return json.dumps(self.compact_state(), indent=2, sort_keys=False)


def build_canonical_packet(
    now: datetime | None = None,
    context_dir: Path | None = None,
    snapshot_path: Path | None = None,
    state: PacketState | None = None,
    *,
    include_resolved: bool = False,
    catalyst_window_hours: float | None = None,
    books_for: str = "active",
    type_filter: MarketTypeFilter | None = None,
) -> CanonicalPacket:
    if state is None:
        state = collect_packet_state(
            now=now, context_dir=context_dir, snapshot_path=snapshot_path
        )
    if catalyst_window_hours is None:
        catalyst_window_hours = get_catalyst_window_hours()

    # The active set drives every trim: which markets render, which books show,
    # which catalysts are in scope, and which markets we evaluate for pricing.
    active_ids = packet_market_ids(
        state.registry,
        state.portfolio,
        include_resolved=include_resolved,
        type_filter=type_filter,
    )
    # Books render for the active set unless the caller asked for all.
    book_ids = (
        {market_id for market_id in _book_entries(state)}
        if books_for == "all"
        else active_ids
    )

    freshness_warnings = _compute_freshness_warnings(state)
    freshness_warnings.extend(_book_freshness_warnings(state, book_ids))
    registry_by_id = {m.market_id: m for m in state.registry.markets}
    exposure_summary, exposure_is_fallback, concentration_warnings = _build_exposure(
        state.portfolio, registry_by_id
    )
    blocking_warnings = _build_blocking_warnings(state.portfolio, registry_by_id)
    priceable, unpriceable = _build_priceability(state, active_ids)
    missing_info = _build_missing_info(state, unpriceable)
    parsed = filter_catalysts(
        parse_catalysts(state.catalysts_markdown),
        now=state.now,
        window_hours=catalyst_window_hours,
        active_ids=active_ids,
    )

    return CanonicalPacket(
        packet_generated_at=state.now.isoformat(),
        source_timestamps={
            "portfolio_current": state.portfolio.as_of.isoformat(),
            "open_orders": state.open_orders.as_of.isoformat(),
            "market_snapshot": state.snapshot.as_of.isoformat() if state.snapshot else None,
            # recent_catalysts.md carries no machine timestamp; entries are
            # individually dated in their text.
            "catalysts": None,
            "order_books": (
                str(state.order_books.get("generated_at"))
                if state.order_books and state.order_books.get("generated_at")
                else None
            ),
        },
        freshness_warnings=freshness_warnings,
        missing_info=missing_info,
        blocking_warnings=blocking_warnings,
        constraints=_build_constraints(state),
        portfolio=_build_portfolio(state.portfolio),
        exposure_summary=exposure_summary,
        exposure_is_fallback=exposure_is_fallback,
        concentration_warnings=concentration_warnings,
        open_orders=_build_open_orders(state.open_orders),
        market_registry=_build_registry(state.registry, active_ids),
        market_snapshot=_build_snapshot(state.snapshot),
        catalysts={
            "credible_reporting_watch": parsed.credible_reporting_watch,
            "noisy_social_media_watch": parsed.noisy_social_media_watch,
        },
        trader_notes=parsed.trader_notes,
        unresolved_missing_information=parsed.unresolved_missing_information,
        priceable_markets=priceable,
        unpriceable_markets=[market_id for market_id, _ in unpriceable],
        raw_notes=list(state.live_state.notes),
        order_books=_build_order_books(state, book_ids),
    )


def _compute_freshness_warnings(state: PacketState) -> list[str]:
    max_age = get_max_context_age_hours()
    # Freshness is an INGEST-time check: it keys only on the as_of of locally
    # fetched context files (live_state/portfolio/open_orders). It deliberately
    # never reads the event dates inside catalyst content — a weeks-old headline
    # ingested minutes ago is fresh. Order-book freshness is handled per-book.
    timestamps = [
        state.live_state.as_of,
        state.portfolio.as_of,
        state.open_orders.as_of,
    ]
    oldest = min(timestamps)
    age_hours = (state.now - oldest.astimezone(state.now.tzinfo)).total_seconds() / 3600
    distinct = {ts.isoformat() for ts in timestamps}

    warnings: list[str] = []
    if len(distinct) > 1:
        warnings.append("context files do not share the same as_of timestamp")
    if age_hours > max_age:
        warnings.append(f"oldest context is older than {max_age:g} hours")
    if age_hours < 0:
        warnings.append("one or more context timestamps are in the future")
    return warnings


def _book_entries(state: PacketState) -> dict[str, dict]:
    if not state.order_books:
        return {}
    markets = state.order_books.get("markets")
    if not isinstance(markets, dict):
        return {}
    return {
        market_id: entry for market_id, entry in markets.items() if isinstance(entry, dict)
    }


def _book_freshness_warnings(state: PacketState, book_ids: set[str]) -> list[str]:
    """Per-book staleness: each market carries its own fetched_at timestamp."""
    max_age = get_max_context_age_hours()
    warnings: list[str] = []
    for market_id, entry in sorted(_book_entries(state).items()):
        if market_id not in book_ids:
            continue
        raw = entry.get("fetched_at")
        try:
            fetched_at = datetime.fromisoformat(str(raw))
        except (TypeError, ValueError):
            warnings.append(f"order book for {market_id} has no parseable fetched_at")
            continue
        age_hours = (state.now - fetched_at.astimezone(state.now.tzinfo)).total_seconds() / 3600
        if age_hours > max_age:
            warnings.append(
                f"order book for {market_id} is older than {max_age:g} hours"
            )
    return warnings


def _build_order_books(state: PacketState, book_ids: set[str]) -> dict[str, object] | None:
    if state.order_books is None and state.order_books_markdown is None:
        return None
    # Only render books for markets in scope (active set, or all when --books-for
    # all). A stale artifact may still carry markets that have since left the set.
    entries = {
        market_id: entry
        for market_id, entry in _book_entries(state).items()
        if market_id in book_ids
    }
    live = sorted(
        market_id for market_id, entry in entries.items() if entry.get("status") == "ok"
    )
    unavailable = sorted(
        market_id for market_id, entry in entries.items() if entry.get("status") != "ok"
    )
    markdown = state.order_books_markdown or ""
    # The artifact carries its own "## Live Order Books" header; strip it so
    # each renderer can place the body under its own section heading.
    lines = markdown.strip().splitlines()
    if lines and lines[0].strip() == "## Live Order Books":
        markdown = "\n".join(lines[1:]).strip()
    markdown = filter_books_markdown(markdown, book_ids)
    return {
        "generated_at": state.order_books.get("generated_at") if state.order_books else None,
        "markets_with_live_books": live,
        "unavailable_markets": unavailable,
        "fetched_at_by_market": {
            market_id: entry.get("fetched_at") for market_id, entry in sorted(entries.items())
        },
        "markdown": markdown,
    }


def _build_constraints(state: PacketState) -> dict[str, object]:
    constraints = state.live_state.constraints
    return {
        "mode": "research_only",
        "no_market_orders": constraints.get("no_market_orders", True) is True,
        "use_sell_ladders": constraints.get("use_sell_ladders", True) is True,
        "avoid_99c_dispute_tax": constraints.get("avoid_99c_dispute_tax", True) is True,
        "automated_execution": False,
        "human_review_required": True,
    }


def _build_portfolio(portfolio: Portfolio) -> dict[str, object]:
    return {
        "as_of": portfolio.as_of.isoformat(),
        "portfolio_value": round(portfolio.portfolio_value, 2),
        "cash_available": round(portfolio.cash_available, 2),
        "positions": [
            {
                "market_id": p.market_id,
                "market_name": p.market_name,
                "side": p.side,
                "band_label": p.band_label,
                "avg_price": p.avg_price,
                "mark_price": p.mark_price,
                "shares": p.shares,
                "current_value": round(p.current_value, 2),
                "pnl": round(p.pnl, 2),
                "thesis_bucket": p.thesis_bucket,
            }
            for p in portfolio.positions
        ],
    }


def _build_exposure(
    portfolio: Portfolio,
    registry_by_id: dict[str, Market],
) -> tuple[list[dict[str, object]], bool, list[str]]:
    """Build exposure summary grouped by thesis_bucket.

    Falls back to rule_key grouping when all positions have empty thesis_bucket.
    Returns (summary_rows, is_fallback, concentration_warnings).
    """
    total = portfolio.portfolio_value
    warnings: list[str] = []
    for position in portfolio.positions:
        if total > 0 and position.current_value / total > 0.35:
            warnings.append(
                f"single position {position.market_id} exceeds 35% of portfolio value"
            )
    if total > 0 and portfolio.cash_available / total < 0.05:
        warnings.append("cash is below 5% of portfolio value")

    all_empty = all(not p.thesis_bucket for p in portfolio.positions)
    use_fallback = all_empty and bool(portfolio.positions)

    bucket_values: dict[str, float] = {}
    bucket_counts: dict[str, int] = {}
    for position in portfolio.positions:
        if use_fallback:
            market = registry_by_id.get(position.market_id)
            rk = market.rule_key if market and market.rule_key else "(unknown)"
            key = f"[rule_key] {rk}"
        else:
            key = position.thesis_bucket
        bucket_values[key] = bucket_values.get(key, 0) + position.current_value
        bucket_counts[key] = bucket_counts.get(key, 0) + 1

    summary: list[dict[str, object]] = []
    for bucket in sorted(bucket_values):
        value = bucket_values[bucket]
        percent = (value / total * 100) if total else 0.0
        if percent > 40:
            label = "rule_key" if use_fallback else "thesis bucket"
            warnings.append(f"{label} {bucket} exceeds 40% of portfolio value")
        summary.append(
            {
                "thesis_bucket": bucket,
                "current_value": round(value, 2),
                "percent_of_portfolio": round(percent, 1),
                "position_count": bucket_counts[bucket],
            }
        )
    return summary, use_fallback, warnings


def _build_blocking_warnings(
    portfolio: Portfolio,
    registry_by_id: dict[str, Market],
) -> list[str]:
    """Enumerate gate failures that must be resolved before recommendations.

    One failure kind is checked:
    - BAND UNRESOLVED: position is on a banded market (registry has band_label
      set) but the position itself carries no band_label.

    Empty thesis_bucket is NOT a blocker — exposure auto-falls-back to grouping
    by rule_key, so the condition self-resolves. It is surfaced as INFO in
    missing_info instead (see _build_missing_info).
    """
    warnings: list[str] = []
    for position in portfolio.positions:
        market = registry_by_id.get(position.market_id)
        if market is not None and market.band_label is not None and not position.band_label:
            warnings.append(
                f"BAND UNRESOLVED: {position.market_id} — registry expects band label "
                f"{market.band_label!r} but position carries none; re-ingest from data-api "
                f"or CLOB to populate band_label"
            )
    return sorted(set(warnings))


def _build_priceability(
    state: PacketState, active_ids: set[str]
) -> tuple[list[str], list[tuple[str, str]]]:
    """Per-market live-data coverage over the active set.

    A market is priceable iff it has an order book present with status ``ok`` and
    a ``fetched_at`` within the freshness window. Books carry provenance — they
    ARE the live data, so there is no separate snapshot gate. We only evaluate
    markets we'd actually fetch a book for: those flagged for orderbook
    collection or currently held. Returns (priceable, [(market_id, reason)]).
    """
    max_age = get_max_context_age_hours()
    held = {position.market_id for position in state.portfolio.positions}
    entries = _book_entries(state)
    priceable: list[str] = []
    unpriceable: list[tuple[str, str]] = []
    for market in sorted(state.registry.markets, key=lambda m: m.market_id):
        if market.market_id not in active_ids:
            continue
        wants_book = (
            market.data_collection is not None and market.data_collection.fetch_orderbook
        ) or market.market_id in held
        if not wants_book:
            continue
        entry = entries.get(market.market_id)
        if entry is None:
            unpriceable.append((market.market_id, "no live book"))
            continue
        if entry.get("status") != "ok":
            unpriceable.append((market.market_id, "BOOK UNAVAILABLE"))
            continue
        raw = entry.get("fetched_at")
        try:
            fetched_at = datetime.fromisoformat(str(raw))
        except (TypeError, ValueError):
            unpriceable.append((market.market_id, "book has no parseable fetched_at"))
            continue
        age_hours = (state.now - fetched_at.astimezone(state.now.tzinfo)).total_seconds() / 3600
        if age_hours > max_age or age_hours < 0:
            unpriceable.append((market.market_id, "stale book"))
            continue
        priceable.append(market.market_id)
    return priceable, unpriceable


def _order_to_dict(order: Order) -> dict[str, object]:
    return {
        "market_id": order.market_id,
        "side": order.side,
        "price": order.price,
        "shares": order.shares,
        "order_type": order.order_type,
        "notes": order.notes,
    }


def _build_open_orders(open_orders: OpenOrders) -> dict[str, object]:
    return {
        "as_of": open_orders.as_of.isoformat(),
        "buys": [_order_to_dict(o) for o in open_orders.buy_orders],
        "sells": [_order_to_dict(o) for o in open_orders.sell_orders],
    }


def _build_registry(
    registry: MarketRegistry, active_ids: set[str]
) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    sorted_markets = sorted(
        (m for m in registry.markets if m.market_id in active_ids),
        key=lambda m: (m.thesis_bucket, m.resolution_date),
    )
    for market in sorted_markets:
        rule_risk = "not specified"
        if market.rule_risk is not None:
            rule_risk = (
                f"oracle={market.rule_risk.oracle_type}; "
                f"ambiguity={market.rule_risk.ambiguity}; "
                f"media_fallback={market.rule_risk.media_fallback}; "
                f"official_required={market.rule_risk.official_statement_required}; "
                f"dispute={market.rule_risk.dispute_risk}"
            )
        rows.append(
            {
                "market_id": market.market_id,
                "lifecycle": market.lifecycle,
                "thesis_bucket": market.thesis_bucket or "(unassigned)",
                "name": market.name,
                "preferred_side": market.preferred_side,
                "rule_key": market.rule_key,
                "oracle_type": market.oracle_type,
                "resolution_date": market.resolution_date.isoformat(),
                "rule_risk": rule_risk,
                "risk_flags": list(market.risk_flags),
                "yes_token_id": market.yes_token_id,
                "no_token_id": market.no_token_id,
            }
        )
    return rows


def _build_snapshot(snapshot: MarketSnapshot | None) -> list[dict[str, object]] | None:
    if snapshot is None:
        return None
    return [
        {
            "market_id": m.market_id,
            "yes_price": m.yes_price,
            "no_price": m.no_price,
            "spread": m.spread,
            "orderbook_depth_top": m.orderbook_depth_top,
            "liquidity_warning": m.liquidity_warning,
            "missing_info": list(m.missing_info),
        }
        for m in snapshot.markets
    ]


def _build_missing_info(
    state: PacketState, unpriceable: list[tuple[str, str]]
) -> list[str]:
    missing: list[str] = []
    # Per-market live-data coverage, derived from order books (the live source).
    # A market with no fresh ok book is not priceable; this replaces the old
    # global "missing market snapshot" gate.
    if state.order_books is None:
        missing.append(
            "no live order books (run `polyberg fetch-books`) — "
            "no live book = no order"
        )
    else:
        for market_id, reason in unpriceable:
            missing.append(f"{market_id}: not priceable — {reason}")
    for market in state.registry.markets:
        if not market.yes_token_id:
            missing.append(f"{market.market_id}: missing YES token ID")
        if not market.no_token_id:
            missing.append(f"{market.market_id}: missing NO token ID")
    # Empty thesis_bucket is INFO, not a blocker: exposure already falls back to
    # grouping by rule_key, so the condition auto-resolves.
    for position in state.portfolio.positions:
        if not position.thesis_bucket:
            missing.append(
                f"{position.market_id}: thesis_bucket empty (INFO — exposure grouped "
                f"by rule_key fallback)"
            )

    local_timestamps = {
        state.live_state.as_of.isoformat(),
        state.portfolio.as_of.isoformat(),
        state.open_orders.as_of.isoformat(),
    }
    if len(local_timestamps) > 1:
        missing.append("mismatched as_of timestamps across local context files")

    # Safety constraints that are missing or not strictly True are a gap the
    # model must be told about before recommending anything.
    constraints = state.live_state.constraints
    for key in SAFETY_CONSTRAINT_KEYS:
        if constraints.get(key) is not True:
            missing.append(f"safety constraint {key} is missing or not true")

    return sorted(set(missing))
