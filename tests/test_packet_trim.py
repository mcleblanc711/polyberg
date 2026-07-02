"""Tests for the packet-trim + gate cleanup: lifecycle filtering, active-set
books, catalyst windowing/scoping/dedup, per-market priceability, ingest-time
freshness, and thesis_bucket severity.

All hermetic — PacketState is built inline, no network or repo context.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

from polyberg.lifecycle import MarketTypeFilter, packet_market_ids, suggest_lifecycle
from polyberg.models import (
    LiveState,
    MarketRegistry,
    OpenOrders,
    Portfolio,
)
from polyberg.packet_builder.catalysts import filter_catalysts, parse_catalysts
from polyberg.packet_builder.collect_state import PacketState
from polyberg.packet_builder.normalize_packet_state import build_canonical_packet

_NOW = datetime(2026, 6, 22, 12, 0, tzinfo=UTC)


# --- builders --------------------------------------------------------------


def _market(market_id: str, *, lifecycle: str = "active", fetch_orderbook: bool = True) -> dict:
    return {
        "market_id": market_id,
        "name": market_id,
        "polymarket_url": "https://example.invalid",
        "category": "test",
        "rule_key": "rule_" + market_id,
        "oracle_type": "pure_data",
        "preferred_side": "YES",
        "risk_flags": [],
        "resolution_date": "2026-06-30",
        "lifecycle": lifecycle,
        "notes": "",
        "thesis_bucket": "Iran conflict",
        "yes_token_id": "1",
        "no_token_id": "2",
        "data_collection": {"fetch_orderbook": fetch_orderbook},
    }


def _position(market_id: str, thesis_bucket: str = "Iran conflict") -> dict:
    return {
        "market_id": market_id,
        "market_name": market_id,
        "side": "YES",
        "avg_price": 0.5,
        "mark_price": 0.5,
        "shares": 10.0,
        "current_value": 5.0,
        "pnl": 0.0,
        "thesis_bucket": thesis_bucket,
    }


def _state(
    *,
    markets: list[dict],
    positions: list[dict],
    catalysts_markdown: str = "",
    order_books: dict | None = None,
    order_books_markdown: str | None = None,
    now: datetime = _NOW,
    as_of: datetime | None = None,
) -> PacketState:
    as_of = as_of or now
    registry = MarketRegistry.model_validate({"markets": markets})
    portfolio = Portfolio.model_validate(
        {
            "as_of": as_of.isoformat(),
            "portfolio_value": sum(p["current_value"] for p in positions) + 10.0,
            "cash_available": 10.0,
            "positions": positions,
        }
    )
    open_orders = OpenOrders.model_validate(
        {"as_of": as_of.isoformat(), "buy_orders": [], "sell_orders": []}
    )
    live_state = LiveState.model_validate(
        {
            "as_of": as_of.isoformat(),
            "mode": "research_only",
            "account_snapshot": {"portfolio_value": 15.0, "cash_available": 10.0},
            "active_thesis": [],
            "constraints": {
                "no_market_orders": True,
                "use_sell_ladders": True,
                "avoid_99c_dispute_tax": True,
            },
            "watchlist": [],
            "notes": [],
        }
    )
    return PacketState(
        now=now,
        registry=registry,
        live_state=live_state,
        portfolio=portfolio,
        open_orders=open_orders,
        snapshot=None,
        catalysts_markdown=catalysts_markdown,
        order_books=order_books,
        order_books_markdown=order_books_markdown,
    )


# --- lifecycle -------------------------------------------------------------


def test_suggest_lifecycle_active_vs_resolving_never_resolved() -> None:
    today = date(2026, 6, 22)
    assert suggest_lifecycle(date(2026, 6, 30), today) == "active"
    assert suggest_lifecycle(date(2026, 6, 22), today) == "active"  # today still open
    assert suggest_lifecycle(date(2026, 6, 21), today) == "resolving"
    # A long-past date still only suggests resolving — never resolved/archived.
    assert suggest_lifecycle(date(2026, 1, 1), today) == "resolving"


def test_packet_market_ids_active_set_and_held() -> None:
    markets = [
        _market("m_active", lifecycle="active"),
        _market("m_resolving", lifecycle="resolving"),
        _market("m_resolved", lifecycle="resolved"),
        _market("m_archived", lifecycle="archived"),
        _market("m_held_resolved", lifecycle="resolved"),
    ]
    registry = MarketRegistry.model_validate({"markets": markets})
    portfolio = Portfolio.model_validate(
        {
            "as_of": _NOW.isoformat(),
            "portfolio_value": 20.0,
            "cash_available": 10.0,
            "positions": [_position("m_held_resolved")],
        }
    )

    default = packet_market_ids(registry, portfolio, include_resolved=False)
    assert default == {"m_active", "m_resolving", "m_held_resolved"}

    full = packet_market_ids(registry, portfolio, include_resolved=True)
    assert full == {m["market_id"] for m in markets}


# --- registry filtering ----------------------------------------------------


def test_registry_renders_active_and_resolving_only_by_default() -> None:
    markets = [
        _market("m_active", lifecycle="active"),
        _market("m_resolving", lifecycle="resolving"),
        _market("m_resolved", lifecycle="resolved"),
    ]
    state = _state(markets=markets, positions=[_position("m_active")])

    cp = build_canonical_packet(state=state)
    ids = {row["market_id"] for row in cp.market_registry}
    assert ids == {"m_active", "m_resolving"}
    # lifecycle is rendered per row
    assert all("lifecycle" in row for row in cp.market_registry)

    cp_all = build_canonical_packet(state=state, include_resolved=True)
    ids_all = {row["market_id"] for row in cp_all.market_registry}
    assert ids_all == {"m_active", "m_resolving", "m_resolved"}


# --- market-type filter ----------------------------------------------------


def test_packet_market_ids_type_filter_keeps_held() -> None:
    markets = [
        _market("m_hormuz", lifecycle="active"),
        _market("m_diplo", lifecycle="active"),
    ]
    markets[0]["category"] = "hormuz_transit_count"
    markets[1]["category"] = "iran_us_diplomacy"
    registry = MarketRegistry.model_validate({"markets": markets})
    portfolio = Portfolio.model_validate(
        {
            "as_of": _NOW.isoformat(),
            "portfolio_value": 20.0,
            "cash_available": 10.0,
            # Held in the OTHER category — must survive the filter.
            "positions": [_position("m_diplo")],
        }
    )
    flt = MarketTypeFilter(category="hormuz_transit_count")
    ids = packet_market_ids(registry, portfolio, type_filter=flt)
    # The matching market plus the held (non-matching) one.
    assert ids == {"m_hormuz", "m_diplo"}

    # An inactive (None) filter is a no-op.
    assert packet_market_ids(registry, portfolio) == {"m_hormuz", "m_diplo"}


def test_build_canonical_packet_type_filter_narrows_registry() -> None:
    markets = [
        _market("m_hormuz", lifecycle="active"),
        _market("m_diplo", lifecycle="active"),
    ]
    markets[0]["category"] = "hormuz_transit_count"
    markets[1]["category"] = "iran_us_diplomacy"
    # No positions held, so the filter alone decides the registry table.
    state = _state(markets=markets, positions=[])
    cp = build_canonical_packet(
        state=state, type_filter=MarketTypeFilter(category="hormuz_transit_count")
    )
    ids = {row["market_id"] for row in cp.market_registry}
    assert ids == {"m_hormuz"}


def test_type_filter_is_active() -> None:
    assert not MarketTypeFilter().is_active
    assert MarketTypeFilter(category="x").is_active
    assert MarketTypeFilter(rule_key="r").is_active


# --- catalyst windowing + scoping + dedup ----------------------------------


def _catalysts_md() -> str:
    return (
        "## Credible Reporting Watch\n"
        "- [2026-06-21 12:00Z] **m_active** recent + active\n"
        "- [2026-06-01 12:00Z] **m_active** old (outside window)\n"
        "- [2026-06-22 06:00Z] **m_resolved** recent but inactive market\n"
        "- [2026-06-22 06:00Z] untagged recent entry\n"
        "- [2026-06-21 18:00Z] **m_active** recent + active\n"  # dup text, diff stamp
        "\n"
        "## Trader Interpretation Notes\n"
        "- a trader hypothesis with no timestamp\n"
    )


def test_catalysts_windowed_scoped_and_deduped() -> None:
    markets = [
        _market("m_active", lifecycle="active"),
        _market("m_resolved", lifecycle="resolved"),
    ]
    state = _state(
        markets=markets,
        positions=[_position("m_active")],
        catalysts_markdown=_catalysts_md(),
    )
    cp = build_canonical_packet(state=state)

    credible = cp.catalysts["credible_reporting_watch"]
    # Only the in-window, active-tagged entry survives; the old, the
    # inactive-market, and the untagged ones are dropped; the duplicate text
    # collapses to one.
    assert len(credible) == 1
    assert "recent + active" in credible[0]
    # Trader notes pass through unwindowed.
    assert cp.trader_notes == ["a trader hypothesis with no timestamp"]


def test_catalyst_window_flag_is_respected() -> None:
    markets = [_market("m_active", lifecycle="active")]
    # Entry ingested 30h before now: inside 48h, outside a 12h window.
    md = (
        "## Credible Reporting Watch\n"
        "- [2026-06-21 06:00Z] **m_active** thirty hours ago\n"
    )
    state = _state(markets=markets, positions=[_position("m_active")], catalysts_markdown=md)

    assert build_canonical_packet(state=state).catalysts["credible_reporting_watch"]
    cp_tight = build_canonical_packet(state=state, catalyst_window_hours=12)
    assert cp_tight.catalysts["credible_reporting_watch"] == []


def test_filter_catalysts_unit_keeps_only_fresh_active() -> None:
    parsed = parse_catalysts(_catalysts_md())
    out = filter_catalysts(
        parsed, now=_NOW, window_hours=48, active_ids={"m_active"}
    )
    assert len(out.credible_reporting_watch) == 1


# --- per-market priceability + no snapshot gate ----------------------------


def _books(now: datetime) -> tuple[dict, str]:
    stale = (now - timedelta(hours=40)).isoformat()
    order_books = {
        "generated_at": now.isoformat(),
        "markets": {
            "m_fresh": {"status": "ok", "fetched_at": now.isoformat()},
            "m_stale": {"status": "ok", "fetched_at": stale},
            "m_404": {"status": "unavailable", "fetched_at": now.isoformat(), "error": "404"},
        },
    }
    md = (
        "## Live Order Books\n"
        f"### m_fresh — NO book · fetched_at {now.isoformat()}\n- ok\n"
        f"### m_stale — NO book · fetched_at {stale}\n- ok\n"
        "### m_404 — BOOK UNAVAILABLE — do not price orders\n- error\n"
    )
    return order_books, md


def test_per_market_priceability_and_no_snapshot_gate() -> None:
    markets = [
        _market("m_fresh"),
        _market("m_stale"),
        _market("m_404"),
        _market("m_nobook"),
    ]
    order_books, md = _books(_NOW)
    state = _state(
        markets=markets,
        positions=[_position("m_fresh")],
        order_books=order_books,
        order_books_markdown=md,
    )
    cp = build_canonical_packet(state=state)

    assert cp.priceable_markets == ["m_fresh"]
    assert set(cp.unpriceable_markets) == {"m_stale", "m_404", "m_nobook"}

    joined = "\n".join(cp.missing_info)
    assert "m_404: not priceable — BOOK UNAVAILABLE" in joined
    assert "m_nobook: not priceable — no live book" in joined
    assert "m_stale: not priceable — stale book" in joined
    # The old global snapshot gate is gone.
    assert "missing market snapshot" not in joined


def test_book_unavailable_404_stays_not_priceable() -> None:
    markets = [_market("m_404")]
    order_books = {
        "generated_at": _NOW.isoformat(),
        "markets": {"m_404": {"status": "unavailable", "fetched_at": _NOW.isoformat()}},
    }
    state = _state(
        markets=markets,
        positions=[_position("m_404")],
        order_books=order_books,
        order_books_markdown="## Live Order Books\n### m_404 — BOOK UNAVAILABLE\n",
    )
    cp = build_canonical_packet(state=state)
    assert cp.priceable_markets == []
    assert cp.unpriceable_markets == ["m_404"]


# --- ingest-time freshness -------------------------------------------------


def test_freshness_ignores_old_catalyst_content() -> None:
    markets = [_market("m_active")]
    # Context files fetched right now; catalyst text dated weeks ago.
    md = (
        "## Credible Reporting Watch\n"
        "- [2026-05-01 12:00Z] **m_active** an event from weeks ago\n"
    )
    state = _state(markets=markets, positions=[_position("m_active")], catalysts_markdown=md)
    cp = build_canonical_packet(state=state)
    assert not any("older than" in w for w in cp.freshness_warnings)


def test_freshness_fires_on_stale_ingest_time() -> None:
    markets = [_market("m_active")]
    old = _NOW - timedelta(hours=40)
    state = _state(markets=markets, positions=[_position("m_active")], as_of=old)
    cp = build_canonical_packet(state=state)
    assert any("older than" in w for w in cp.freshness_warnings)


# --- thesis_bucket severity ------------------------------------------------


def test_empty_thesis_bucket_is_info_not_blocker() -> None:
    markets = [_market("m_active")]
    state = _state(
        markets=markets,
        positions=[_position("m_active", thesis_bucket="")],
    )
    cp = build_canonical_packet(state=state)
    assert not any("THESIS BUCKET EMPTY" in w for w in cp.blocking_warnings)
    assert any("thesis_bucket empty" in item for item in cp.missing_info)
