"""Tests for ladder/validate.py — hard validators and warnings."""
from __future__ import annotations

from decimal import Decimal

import pytest

from polyberg.ladder.models import Ladder, Rung, Tags, TargetLadders
from polyberg.ladder.validate import LadderValidationError, validate_targets
from polyberg.models import MarketRegistry

# ── helpers ───────────────────────────────────────────────────────────────────

def _ladder(market_id, outcome, action, rungs, purpose=None):
    tags = Tags(purpose=purpose) if purpose else None
    return Ladder(
        market_id=market_id,
        outcome=outcome,
        action=action,
        rungs=[Rung(price=p, shares=s) for p, s in rungs],
        tags=tags,
    )


def _targets(*ladders):
    return TargetLadders(ladders=list(ladders))


def _registry(markets=None):
    if markets is None:
        markets = [_market("mkt_a"), _market("mkt_b")]
    return MarketRegistry.model_validate({"markets": markets})


def _market(market_id, band_verified=True, media_fallback=False):
    return {
        "market_id": market_id,
        "name": market_id,
        "polymarket_url": f"https://polymarket.com/event/{market_id}",
        "category": "test",
        "thesis_bucket": "",
        "rule_key": "test",
        "oracle_type": "test",
        "preferred_side": "YES",
        "resolution_date": "2026-12-31",
        "notes": "",
        "yes_token_id": "111",
        "no_token_id": "222",
        "band_verified": band_verified,
        "rule_risk": {
            "oracle_type": "test",
            "ambiguity": "low",
            "media_fallback": media_fallback,
            "official_statement_required": False,
            "dispute_risk": "low",
        } if media_fallback else None,
    }


# ── [sell-cap] ────────────────────────────────────────────────────────────────

def test_sell_cap_fails_above_096():
    targets = _targets(_ladder("mkt_a", "NO", "SELL", [(0.961, 100)]))
    with pytest.raises(LadderValidationError) as exc_info:
        validate_targets(targets, _registry(), Decimal("1000"), False)
    assert "[sell-cap]" in exc_info.value.messages[0]
    assert "0.961" in exc_info.value.messages[0]


def test_sell_cap_passes_at_exactly_096():
    targets = _targets(_ladder("mkt_a", "NO", "SELL", [(0.96, 100)]))
    warnings = validate_targets(targets, _registry(), Decimal("1000"), False)
    assert not any("[sell-cap]" in w for w in warnings)


def test_sell_cap_passes_below_096():
    targets = _targets(_ladder("mkt_a", "NO", "SELL", [(0.90, 100)]))
    warnings = validate_targets(targets, _registry(), Decimal("1000"), False)
    assert not any("[sell-cap]" in w for w in warnings)


# ── [cash-collision] ──────────────────────────────────────────────────────────

def test_cash_collision_cross_market_warns():
    # mkt_a: 0.5 × 100 = 50; mkt_b: 0.6 × 200 = 120; total = 170 > 100
    targets = _targets(
        _ladder("mkt_a", "YES", "BUY", [(0.5, 100)]),
        _ladder("mkt_b", "YES", "BUY", [(0.6, 200)]),
    )
    warnings = validate_targets(targets, _registry(), Decimal("100"), False)
    msg = next(w for w in warnings if "[cash-collision]" in w)
    assert "$170.00" in msg
    assert "$100.00" in msg
    assert "overage: $70.00" in msg


def test_cash_collision_equal_cash_passes():
    # 0.5 × 100 = 50 == 50
    targets = _targets(_ladder("mkt_a", "YES", "BUY", [(0.5, 100)]))
    warnings = validate_targets(targets, _registry(), Decimal("50"), False)
    assert not any("[cash-collision]" in w for w in warnings)


def test_cash_collision_within_cash_passes():
    targets = _targets(_ladder("mkt_a", "YES", "BUY", [(0.5, 100)]))
    warnings = validate_targets(targets, _registry(), Decimal("60"), False)
    assert not any("[cash-collision]" in w for w in warnings)


# ── [dirty-oracle] warnings ───────────────────────────────────────────────────

def test_dirty_oracle_band_verified_false():
    registry = _registry([_market("mkt_a", band_verified=False)])
    targets = _targets(_ladder("mkt_a", "YES", "BUY", [(0.5, 10)]))
    warnings = validate_targets(targets, registry, Decimal("1000"), False)
    assert any("[dirty-oracle]" in w and "band_verified=false" in w for w in warnings)


def test_dirty_oracle_media_fallback_true():
    registry = _registry([_market("mkt_a", media_fallback=True)])
    targets = _targets(_ladder("mkt_a", "YES", "BUY", [(0.5, 10)]))
    warnings = validate_targets(targets, registry, Decimal("1000"), False)
    assert any("[dirty-oracle]" in w and "media_fallback=true" in w for w in warnings)


def test_dirty_oracle_sell_ladder_no_warning():
    """Dirty-oracle check only applies to BUY ladders."""
    registry = _registry([_market("mkt_a", band_verified=False)])
    targets = _targets(_ladder("mkt_a", "YES", "SELL", [(0.5, 10)]))
    warnings = validate_targets(targets, registry, Decimal("1000"), False)
    assert not any("[dirty-oracle]" in w for w in warnings)


def test_dirty_oracle_clean_market_no_warning():
    registry = _registry([_market("mkt_a", band_verified=True, media_fallback=False)])
    targets = _targets(_ladder("mkt_a", "YES", "BUY", [(0.5, 10)]))
    warnings = validate_targets(targets, registry, Decimal("1000"), False)
    assert not any("[dirty-oracle]" in w for w in warnings)


# ── [stale-cash] warning ──────────────────────────────────────────────────────

def test_stale_cash_warns_when_from_portfolio():
    targets = _targets()
    warnings = validate_targets(targets, _registry(), Decimal("100"), cash_is_stale=True)
    assert any("[stale-cash]" in w for w in warnings)


def test_stale_cash_no_warning_when_live():
    targets = _targets()
    warnings = validate_targets(targets, _registry(), Decimal("100"), cash_is_stale=False)
    assert not any("[stale-cash]" in w for w in warnings)


# ── multiple hard fails reported together ─────────────────────────────────────

def test_multiple_hard_fails_collected():
    """All sell-cap violations should surface in a single exception."""
    targets = _targets(
        _ladder("mkt_a", "NO", "SELL", [(0.97, 100)]),  # sell-cap fail
        _ladder("mkt_b", "NO", "SELL", [(0.99, 100)]),  # sell-cap fail
    )
    with pytest.raises(LadderValidationError) as exc_info:
        validate_targets(targets, _registry(), Decimal("10"), False)
    msgs = exc_info.value.messages
    assert len(msgs) == 2
    assert all("[sell-cap]" in m for m in msgs)
