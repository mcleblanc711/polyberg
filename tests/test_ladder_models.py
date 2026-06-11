"""Tests for ladder/models.py — schema, validators, and load_target_ladders()."""
from __future__ import annotations

import pytest
import yaml
from pydantic import ValidationError

from polyberg.ladder.models import (
    Rung,
    TargetLadders,
    load_target_ladders,
)
from polyberg.loaders import LoaderError
from polyberg.models import MarketRegistry

# ── helpers ──────────────────────────────────────────────────────────────────

def _write_yaml(tmp_path, name, data):
    p = tmp_path / name
    p.write_text(yaml.dump(data), encoding="utf-8")
    return p


def _minimal_ladder_data():
    return {
        "market_id": "test_market",
        "outcome": "YES",
        "action": "BUY",
        "rungs": [{"price": 0.5, "shares": 100}],
    }


def _minimal_targets(ladders=None):
    return {
        "schema_version": "1",
        "matching": {"price_tolerance": 0.0005, "shares_tolerance": 1.0},
        "ladders": ladders or [],
    }


def _minimal_registry(market_id="test_market"):
    return MarketRegistry.model_validate({
        "markets": [{
            "market_id": market_id,
            "name": "Test Market",
            "polymarket_url": "https://polymarket.com/event/test",
            "category": "test",
            "thesis_bucket": "",
            "rule_key": "test",
            "oracle_type": "test",
            "preferred_side": "YES",
            "resolution_date": "2026-12-31",
            "notes": "",
            "yes_token_id": "111",
            "no_token_id": "222",
        }]
    })


# ── parse ok ──────────────────────────────────────────────────────────────────

def test_parse_full_ladder():
    data = _minimal_targets([{
        "market_id": "abc_market",
        "outcome": "NO",
        "action": "SELL",
        "rungs": [
            {"price": 0.90, "shares": 150},
            {"price": 0.94, "shares": 100},
        ],
        "tags": {"purpose": "cash_rebuild"},
    }])
    t = TargetLadders.model_validate(data)
    assert len(t.ladders) == 1
    ladder = t.ladders[0]
    assert ladder.market_id == "abc_market"
    assert ladder.outcome == "NO"
    assert ladder.action == "SELL"
    assert len(ladder.rungs) == 2
    assert ladder.tags is not None
    assert ladder.tags.purpose == "cash_rebuild"


def test_parse_ladder_without_tags():
    data = _minimal_targets([_minimal_ladder_data()])
    t = TargetLadders.model_validate(data)
    assert t.ladders[0].tags is None


def test_matching_defaults_when_absent():
    data = {"schema_version": "1", "ladders": []}
    t = TargetLadders.model_validate(data)
    assert t.matching.price_tolerance == 0.0005
    assert t.matching.shares_tolerance == 1.0


# ── limit-only structural pin ─────────────────────────────────────────────────

def test_order_type_market_rejected():
    """order_type in a rung is rejected by extra=forbid — market orders unrepresentable."""
    data = _minimal_targets([{
        **_minimal_ladder_data(),
        "rungs": [{"price": 0.5, "shares": 100, "order_type": "market"}],
    }])
    with pytest.raises(ValidationError):
        TargetLadders.model_validate(data)


def test_order_type_limit_also_rejected():
    """Even order_type=limit is an extra field and is rejected."""
    data = _minimal_targets([{
        **_minimal_ladder_data(),
        "rungs": [{"price": 0.5, "shares": 100, "order_type": "limit"}],
    }])
    with pytest.raises(ValidationError):
        TargetLadders.model_validate(data)


# ── price / shares bounds ─────────────────────────────────────────────────────

def test_rung_price_zero_rejected():
    with pytest.raises(ValidationError):
        Rung.model_validate({"price": 0.0, "shares": 100})


def test_rung_price_one_rejected():
    with pytest.raises(ValidationError):
        Rung.model_validate({"price": 1.0, "shares": 100})


def test_rung_price_boundary_valid():
    r = Rung.model_validate({"price": 0.001, "shares": 1})
    assert r.price == 0.001


def test_rung_shares_zero_rejected():
    with pytest.raises(ValidationError):
        Rung.model_validate({"price": 0.5, "shares": 0})


def test_rung_shares_negative_rejected():
    with pytest.raises(ValidationError):
        Rung.model_validate({"price": 0.5, "shares": -1})


# ── duplicate rung prices ─────────────────────────────────────────────────────

def test_duplicate_rung_prices_rejected():
    data = _minimal_targets([{
        **_minimal_ladder_data(),
        "rungs": [
            {"price": 0.5, "shares": 100},
            {"price": 0.5, "shares": 200},
        ],
    }])
    with pytest.raises(ValidationError, match="duplicate rung prices"):
        TargetLadders.model_validate(data)


def test_unique_rung_prices_ok():
    data = _minimal_targets([{
        **_minimal_ladder_data(),
        "rungs": [
            {"price": 0.5, "shares": 100},
            {"price": 0.6, "shares": 200},
        ],
    }])
    t = TargetLadders.model_validate(data)
    assert len(t.ladders[0].rungs) == 2


# ── unknown market_id in load_target_ladders ─────────────────────────────────

def test_unknown_market_id_fails(tmp_path):
    p = _write_yaml(tmp_path, "target_ladders.yaml", _minimal_targets([
        {**_minimal_ladder_data(), "market_id": "no_such_market"},
    ]))
    registry = _minimal_registry("different_market")
    with pytest.raises(LoaderError, match="unknown market_id"):
        load_target_ladders(p, registry)


def test_missing_token_id_fails(tmp_path):
    p = _write_yaml(tmp_path, "target_ladders.yaml", _minimal_targets([
        _minimal_ladder_data(),  # outcome=YES
    ]))
    registry = MarketRegistry.model_validate({
        "markets": [{
            "market_id": "test_market",
            "name": "Test",
            "polymarket_url": "https://polymarket.com/event/test",
            "category": "test",
            "thesis_bucket": "",
            "rule_key": "test",
            "oracle_type": "test",
            "preferred_side": "YES",
            "resolution_date": "2026-12-31",
            "notes": "",
            "yes_token_id": None,  # missing
            "no_token_id": "222",
        }]
    })
    with pytest.raises(LoaderError, match="yes_token_id"):
        load_target_ladders(p, registry)


def test_valid_targets_no_error(tmp_path):
    p = _write_yaml(tmp_path, "target_ladders.yaml", _minimal_targets([
        _minimal_ladder_data(),
    ]))
    t = load_target_ladders(p, _minimal_registry())
    assert len(t.ladders) == 1


# ── local overlay ─────────────────────────────────────────────────────────────

def test_local_overlay_preferred(tmp_path):
    """live/target_ladders.local.yaml wins over live/target_ladders.yaml."""
    base = _write_yaml(tmp_path, "target_ladders.yaml", _minimal_targets([]))
    local_data = _minimal_targets([_minimal_ladder_data()])
    _write_yaml(tmp_path, "target_ladders.local.yaml", local_data)
    t = load_target_ladders(base, _minimal_registry())
    assert len(t.ladders) == 1


def test_no_local_overlay_uses_base(tmp_path):
    base = _write_yaml(tmp_path, "target_ladders.yaml", _minimal_targets([]))
    t = load_target_ladders(base, _minimal_registry())
    assert t.ladders == []
