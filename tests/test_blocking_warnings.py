"""Spec test cases (a), (b), (c): band resolution, blocking warnings, empty thesis_bucket.

All API calls are mocked — no network access.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from polyberg.account_normalizer import normalize_data_api_positions
from polyberg.models import (
    LiveState,
    MarketRegistry,
    OpenOrders,
    Portfolio,
)
from polyberg.packet_builder.collect_state import PacketState
from polyberg.packet_builder.normalize_packet_state import build_canonical_packet

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_NOW = datetime(2026, 6, 9, 12, 0, tzinfo=UTC)


def _stub_market(
    market_id: str,
    condition_id: str = "0xabc",
    thesis_bucket: str = "test_bucket",
    rule_key: str = "test_rule",
    band_label: str | None = None,
    band_low: float | None = None,
    band_high: float | None = None,
    bounds_inclusive: bool | None = None,
    band_verified: bool = True,
) -> dict:
    d = {
        "market_id": market_id,
        "name": market_id,
        "polymarket_url": "https://example.invalid",
        "category": "test",
        "rule_key": rule_key,
        "oracle_type": "pure_data",
        "preferred_side": "YES",
        "risk_flags": [],
        "resolution_date": "2027-01-01",
        "notes": "",
        "condition_id": condition_id,
        "thesis_bucket": thesis_bucket,
        "band_verified": band_verified,
    }
    if band_label is not None:
        d["band_label"] = band_label
    if band_low is not None:
        d["band_low"] = band_low
    if band_high is not None:
        d["band_high"] = band_high
    if bounds_inclusive is not None:
        d["bounds_inclusive"] = bounds_inclusive
    return d


def _stub_position(
    market_id: str,
    thesis_bucket: str = "test_bucket",
    band_label: str | None = None,
) -> dict:
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
        "band_label": band_label,
    }


def _make_packet_state(
    positions: list[dict],
    markets: list[dict],
    *,
    now: datetime = _NOW,
) -> PacketState:
    registry = MarketRegistry.model_validate({"markets": markets})
    portfolio = Portfolio.model_validate(
        {
            "as_of": now.isoformat(),
            "portfolio_value": sum(p["current_value"] for p in positions) + 10.0,
            "cash_available": 10.0,
            "positions": positions,
        }
    )
    open_orders = OpenOrders.model_validate(
        {"as_of": now.isoformat(), "buy_orders": [], "sell_orders": []}
    )
    live_state = LiveState.model_validate(
        {
            "as_of": now.isoformat(),
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
        catalysts_markdown="",
    )


# ---------------------------------------------------------------------------
# (a) Bracketed market position resolves to correct band via normalizer
# ---------------------------------------------------------------------------


def test_a_bracketed_position_resolves_band_from_data_api() -> None:
    """data-api outcome '10-20' populates band_label + parsed bounds."""
    raw_positions = [
        {
            "conditionId": "0xcond_band",
            "asset": "0xtoken_yes",
            "size": 100.0,
            "avgPrice": 0.54,
            "curPrice": 0.60,
            "currentValue": 60.0,
            "cashPnl": 6.0,
            "outcome": "10-20",
            "title": "Avg ships end of June — 10-20 band",
        }
    ]
    registry = MarketRegistry.model_validate(
        {
            "markets": [
                _stub_market("ships_10_20", condition_id="0xcond_band"),
            ]
        }
    )
    portfolio, skipped = normalize_data_api_positions(
        raw_positions, registry, cash_available=10.0, now=_NOW
    )
    assert skipped == []
    assert len(portfolio.positions) == 1
    pos = portfolio.positions[0]
    assert pos.band_label == "10-20"
    assert pos.band_low == pytest.approx(10.0)
    assert pos.band_high == pytest.approx(20.0)
    assert pos.bounds_inclusive is True
    # Side is still YES — the YES token for the 10-20 band
    assert pos.side == "YES"


def test_a_binary_position_has_no_band_fields() -> None:
    """Standard Yes/No outcome → band_label and bounds stay None."""
    raw_positions = [
        {
            "conditionId": "0xcond_binary",
            "asset": "0xtoken",
            "size": 50.0,
            "avgPrice": 0.4,
            "curPrice": 0.5,
            "currentValue": 25.0,
            "cashPnl": 5.0,
            "outcome": "No",
            "title": "Binary market",
        }
    ]
    registry = MarketRegistry.model_validate(
        {"markets": [_stub_market("binary_m", condition_id="0xcond_binary")]}
    )
    portfolio, _ = normalize_data_api_positions(
        raw_positions, registry, cash_available=0.0, now=_NOW
    )
    pos = portfolio.positions[0]
    assert pos.band_label is None
    assert pos.band_low is None
    assert pos.band_high is None
    assert pos.bounds_inclusive is None
    assert pos.side == "NO"


def test_a_band_with_under_pattern() -> None:
    """'Under 10' outcome → exclusive upper bound, no lower bound."""
    raw_positions = [
        {
            "conditionId": "0xcond_under",
            "asset": "0xtoken",
            "size": 20.0,
            "avgPrice": 0.3,
            "curPrice": 0.35,
            "currentValue": 7.0,
            "cashPnl": 1.0,
            "outcome": "Under 10",
            "title": "Ships — under 10 band",
        }
    ]
    registry = MarketRegistry.model_validate(
        {"markets": [_stub_market("ships_under_10", condition_id="0xcond_under")]}
    )
    portfolio, _ = normalize_data_api_positions(
        raw_positions, registry, cash_available=0.0, now=_NOW
    )
    pos = portfolio.positions[0]
    assert pos.band_label == "Under 10"
    assert pos.band_low is None
    assert pos.band_high == pytest.approx(10.0)
    assert pos.bounds_inclusive is False


# ---------------------------------------------------------------------------
# (b) Unresolvable token → blocking warning
# ---------------------------------------------------------------------------


def test_b_missing_band_label_on_banded_market_produces_blocking_warning() -> None:
    """A position with no band_label on a market that has one in the registry
    must appear in blocking_warnings."""
    markets = [
        _stub_market(
            "ships_10_20",
            band_label="10-20",
            band_low=10.0,
            band_high=20.0,
            bounds_inclusive=True,
        )
    ]
    positions = [_stub_position("ships_10_20", band_label=None)]  # no band set
    state = _make_packet_state(positions, markets)
    cp = build_canonical_packet(state=state)

    assert any("BAND UNRESOLVED" in w and "ships_10_20" in w for w in cp.blocking_warnings)


def test_b_position_with_correct_band_label_produces_no_band_warning() -> None:
    """If the position already has a band_label, no BAND UNRESOLVED warning fires."""
    markets = [
        _stub_market(
            "ships_10_20",
            band_label="10-20",
            band_low=10.0,
            band_high=20.0,
            bounds_inclusive=True,
        )
    ]
    # Position carries the band label — no warning expected
    positions = [_stub_position("ships_10_20", band_label="10-20")]
    state = _make_packet_state(positions, markets)
    cp = build_canonical_packet(state=state)

    assert not any("BAND UNRESOLVED" in w and "ships_10_20" in w for w in cp.blocking_warnings)


# ---------------------------------------------------------------------------
# (c) Empty thesis_bucket → INFO, not a blocker (exposure falls back to rule_key)
# ---------------------------------------------------------------------------


def test_c_empty_thesis_bucket_is_info_not_blocking() -> None:
    """Empty thesis_bucket is surfaced as INFO (missing_info), not a blocker —
    exposure auto-falls-back to grouping by rule_key, so it self-resolves."""
    markets = [_stub_market("m_no_thesis", thesis_bucket="")]
    positions = [_stub_position("m_no_thesis", thesis_bucket="")]
    state = _make_packet_state(positions, markets)
    cp = build_canonical_packet(state=state)

    assert not any("THESIS BUCKET EMPTY" in w for w in cp.blocking_warnings)
    assert any(
        "m_no_thesis" in item and "thesis_bucket empty" in item for item in cp.missing_info
    )


def test_c_non_empty_thesis_bucket_has_no_thesis_warning() -> None:
    markets = [_stub_market("m_with_thesis", thesis_bucket="Iran conflict")]
    positions = [_stub_position("m_with_thesis", thesis_bucket="Iran conflict")]
    state = _make_packet_state(positions, markets)
    cp = build_canonical_packet(state=state)

    assert not any("THESIS BUCKET EMPTY" in w for w in cp.blocking_warnings)


def test_c_exposure_fallback_when_all_thesis_buckets_empty() -> None:
    """All-empty thesis_bucket → exposure grouped by rule_key with fallback flag."""
    markets = [
        _stub_market("m1", thesis_bucket="", rule_key="rule_a"),
        _stub_market("m2", thesis_bucket="", rule_key="rule_b", condition_id="0xdef"),
    ]
    positions = [
        _stub_position("m1", thesis_bucket=""),
        _stub_position("m2", thesis_bucket=""),
    ]
    state = _make_packet_state(positions, markets)
    cp = build_canonical_packet(state=state)

    assert cp.exposure_is_fallback is True
    bucket_labels = {row["thesis_bucket"] for row in cp.exposure_summary}
    assert any("[rule_key]" in label for label in bucket_labels)


def test_c_exposure_not_fallback_when_some_buckets_filled() -> None:
    markets = [
        _stub_market("m_filled", thesis_bucket="Iran conflict"),
        _stub_market("m_empty", thesis_bucket="", condition_id="0xdef2"),
    ]
    positions = [
        _stub_position("m_filled", thesis_bucket="Iran conflict"),
        _stub_position("m_empty", thesis_bucket=""),
    ]
    state = _make_packet_state(positions, markets)
    cp = build_canonical_packet(state=state)

    assert cp.exposure_is_fallback is False


# ---------------------------------------------------------------------------
# BLOCKING WARNINGS section appears in rendered packets
# ---------------------------------------------------------------------------


def test_blocking_warnings_appear_in_both_renderers() -> None:
    from polyberg.packet_builder.renderers.claude_packet_renderer import render_claude_packet
    from polyberg.packet_builder.renderers.gpt_packet_renderer import render_gpt_packet

    # BAND UNRESOLVED is a real blocker (empty thesis_bucket is only INFO now).
    markets = [
        _stub_market(
            "ships_10_20", band_label="10-20", band_low=10.0, band_high=20.0,
            bounds_inclusive=True,
        )
    ]
    positions = [_stub_position("ships_10_20", band_label=None)]
    state = _make_packet_state(positions, markets)
    cp = build_canonical_packet(state=state)

    assert cp.blocking_warnings  # sanity
    for packet in (render_claude_packet(cp), render_gpt_packet(cp)):
        assert "BLOCKING WARNINGS" in packet
        assert "ships_10_20" in packet


def test_no_blocking_warnings_section_when_clean() -> None:
    """If there are no blocking warnings, the section must NOT appear."""
    from polyberg.packet_builder.renderers.claude_packet_renderer import render_claude_packet

    markets = [_stub_market("m_ok", thesis_bucket="Iran conflict")]
    positions = [_stub_position("m_ok", thesis_bucket="Iran conflict")]
    state = _make_packet_state(positions, markets)
    cp = build_canonical_packet(state=state)

    assert cp.blocking_warnings == []
    packet = render_claude_packet(cp)
    assert "BLOCKING WARNINGS" not in packet
