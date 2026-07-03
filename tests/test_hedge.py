from __future__ import annotations

import pytest

from polyberg.hedge import (
    RESIDUAL_KEY,
    HedgeError,
    HedgeLeg,
    build_hedge_groups,
    compute_group,
    parse_leg_spec,
)
from polyberg.models import MarketRegistry, Portfolio


def _leg(market_id, side, price, shares, source="held"):
    return HedgeLeg(market_id, market_id, side, price, shares, source)


# --- leg spec parsing ------------------------------------------------------


def test_parse_leg_spec_ok() -> None:
    assert parse_leg_spec("band_a:NO:0.82:100") == ("band_a", "NO", 0.82, 100.0)
    assert parse_leg_spec("band_a:yes:0.1:5")[1] == "YES"


@pytest.mark.parametrize("spec", ["a:NO:0.5", "a:MAYBE:0.5:1", "a:NO:1.5:1", "a:NO:x:1"])
def test_parse_leg_spec_rejects_bad(spec: str) -> None:
    with pytest.raises(HedgeError):
        parse_leg_spec(spec)


# --- payoff math -----------------------------------------------------------


def test_yes_leg_pays_only_when_its_band_wins() -> None:
    legs = [_leg("a", "YES", 0.20, 100)]
    group = compute_group(
        "g", "G", legs, winners=[("a", "a"), ("b", "b")], residual_feasible=False,
        exclusivity_verified=True,
    )
    by_key = {s.key: s for s in group.scenarios}
    # a wins: payout 100 - cost 20 = +80
    assert by_key["a"].net == pytest.approx(80.0)
    # b wins: YES on a loses → -20
    assert by_key["b"].net == pytest.approx(-20.0)
    assert by_key["a"].return_pct == pytest.approx(400.0)


def test_no_leg_pays_when_other_band_wins() -> None:
    legs = [_leg("a", "NO", 0.80, 100)]
    group = compute_group(
        "g", "G", legs, winners=[("a", "a"), ("b", "b")], residual_feasible=False,
        exclusivity_verified=True,
    )
    by_key = {s.key: s for s in group.scenarios}
    # a wins: NO on a loses → -80. b wins: NO on a pays 100 - 80 = +20.
    assert by_key["a"].net == pytest.approx(-80.0)
    assert by_key["b"].net == pytest.approx(20.0)


def test_locked_profit_across_full_family() -> None:
    # Buy NO on both bands of a complete 2-band neg-risk family, cheap enough that
    # whichever wins, the other NO leg more than covers it.
    legs = [_leg("a", "NO", 0.40, 100), _leg("b", "NO", 0.40, 100)]
    group = compute_group(
        "g", "G", legs, winners=[("a", "a"), ("b", "b")], residual_feasible=False,
        exclusivity_verified=True,
    )
    # a wins: NO_a -40 loses, NO_b +60 → +20. Symmetric for b. Guaranteed +20.
    assert group.guaranteed_min == pytest.approx(20.0)
    assert group.locked_profit is True
    # residual excluded because the family is complete.
    residual = next(s for s in group.scenarios if s.key == RESIDUAL_KEY)
    assert residual.feasible is False


def test_residual_feasible_when_family_incomplete() -> None:
    legs = [_leg("a", "NO", 0.40, 100)]
    group = compute_group(
        "g", "G", legs, winners=[("a", "a")], residual_feasible=True,
        exclusivity_verified=True,
    )
    residual = next(s for s in group.scenarios if s.key == RESIDUAL_KEY)
    assert residual.feasible is True
    # residual = some other band wins → NO_a pays 100 - 40 = +60
    assert residual.net == pytest.approx(60.0)


# --- grouping --------------------------------------------------------------


def _registry(markets: list[dict]) -> MarketRegistry:
    base = {
        "name": "x",
        "polymarket_url": "https://example.invalid",
        "category": "c",
        "rule_key": "k",
        "oracle_type": "UMA",
        "preferred_side": "NO",
        "resolution_date": "2026-12-31",
        "notes": "",
    }
    return MarketRegistry.model_validate({"markets": [{**base, **m} for m in markets]})


def _portfolio(positions: list[dict]) -> Portfolio:
    base = {
        "market_name": "x",
        "avg_price": 0.5,
        "mark_price": 0.5,
        "shares": 100.0,
        "current_value": 50.0,
        "pnl": 0.0,
        "thesis_bucket": "",
    }
    return Portfolio.model_validate(
        {
            "as_of": "2026-06-22T12:00:00+00:00",
            "portfolio_value": 1000.0,
            "cash_available": 100.0,
            "positions": [{**base, **p} for p in positions],
        }
    )


def test_build_groups_by_event_slug_with_whatif() -> None:
    band = {"event_slug": "ships", "neg_risk": True}
    registry = _registry(
        [
            {"market_id": "b_lt25", "name": "Ships — <25", **band},
            {"market_id": "b_2549", "name": "Ships — 25-49", **band},
        ]
    )
    portfolio = _portfolio([{"market_id": "b_lt25", "side": "NO", "avg_price": 0.4}])
    groups = build_hedge_groups(
        registry, portfolio, what_if_specs=["b_2549:NO:0.4:100"]
    )
    assert len(groups) == 1
    g = groups[0]
    assert g.exclusivity_verified is True
    assert g.name == "Ships"
    assert {leg.market_id for leg in g.legs} == {"b_lt25", "b_2549"}
    # Complete 2-band family → residual infeasible.
    residual = next(s for s in g.scenarios if s.key == RESIDUAL_KEY)
    assert residual.feasible is False


def test_unverified_family_flagged() -> None:
    band = {"event_slug": "peace", "neg_risk": False}
    registry = _registry(
        [
            {"market_id": "p_apr", "name": "Peace — by Apr", **band},
            {"market_id": "p_may", "name": "Peace — by May", **band},
        ]
    )
    portfolio = _portfolio(
        [
            {"market_id": "p_apr", "side": "NO", "avg_price": 0.5},
            {"market_id": "p_may", "side": "NO", "avg_price": 0.6},
        ]
    )
    groups = build_hedge_groups(registry, portfolio)
    assert len(groups) == 1
    g = groups[0]
    assert g.exclusivity_verified is False
    assert any("unverified" in n.lower() for n in g.notes)
    # Not recorded neg-risk → residual stays feasible (can't assume partition).
    residual = next(s for s in g.scenarios if s.key == RESIDUAL_KEY)
    assert residual.feasible is True


def test_singletons_dropped_unless_event_filter() -> None:
    registry = _registry(
        [{"market_id": "solo", "name": "Solo", "event_slug": "ships", "neg_risk": True}]
    )
    portfolio = _portfolio([{"market_id": "solo", "side": "YES", "avg_price": 0.3}])
    assert build_hedge_groups(registry, portfolio) == []
    forced = build_hedge_groups(registry, portfolio, event="ships")
    assert len(forced) == 1
