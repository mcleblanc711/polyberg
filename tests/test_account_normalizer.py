from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from polyberg.account_normalizer import (
    NormalizerError,
    normalize_data_api_positions,
    promote_data_api_positions,
)
from polyberg.loaders import load_market_registry, load_portfolio
from polyberg.models import MarketRegistry

FIXTURE = Path(__file__).parent / "fixtures" / "account_import" / "positions_data_api.json"


def _registry_for_fixture(tmp_path: Path) -> tuple[Path, MarketRegistry]:
    """Build a tiny registry whose condition_ids match the fixture positions."""
    raw = json.loads(FIXTURE.read_text(encoding="utf-8"))
    yaml_lines = ["markets:"]
    for i, position in enumerate(raw):
        market_id = f"fix_market_{i}"
        yaml_lines.extend(
            [
                f"  - market_id: {market_id}",
                f"    name: \"{position['title']}\"",
                "    polymarket_url: https://example.invalid",
                "    category: test",
                "    rule_key: test",
                "    oracle_type: pure_data",
                '    preferred_side: "YES"',
                "    risk_flags: []",
                "    resolution_date: 2027-01-01",
                '    notes: ""',
                f"    condition_id: \"{position['conditionId']}\"",
                f"    yes_token_id: \"{position['asset']}\"",
            ]
        )
    path = tmp_path / "registry.yaml"
    path.write_text("\n".join(yaml_lines) + "\n", encoding="utf-8")
    return path, load_market_registry(path)


def test_normalize_real_fixture_maps_every_position(tmp_path: Path) -> None:
    _, registry = _registry_for_fixture(tmp_path)
    raw_positions = json.loads(FIXTURE.read_text(encoding="utf-8"))
    portfolio, skipped = normalize_data_api_positions(
        raw_positions,
        registry,
        cash_available=100.0,
        now=datetime(2026, 5, 11, tzinfo=timezone.utc),
    )
    assert skipped == []
    assert len(portfolio.positions) == len(raw_positions)
    expected_value = sum(round(float(p.get("currentValue", 0)), 2) for p in raw_positions)
    assert portfolio.portfolio_value == pytest.approx(expected_value + 100.0, abs=0.01)
    sides = {p.side for p in portfolio.positions}
    assert sides <= {"YES", "NO"}


def test_normalize_skips_positions_not_in_registry(tmp_path: Path) -> None:
    registry_path = tmp_path / "registry.yaml"
    registry_path.write_text(
        "\n".join(
            [
                "markets:",
                "  - market_id: only_one",
                "    name: Only Market",
                "    polymarket_url: https://example.invalid",
                "    category: test",
                "    rule_key: test",
                "    oracle_type: pure_data",
                '    preferred_side: "YES"',
                "    risk_flags: []",
                "    resolution_date: 2027-01-01",
                '    notes: ""',
                '    condition_id: "0xabsent"',
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    registry = load_market_registry(registry_path)
    raw_positions = json.loads(FIXTURE.read_text(encoding="utf-8"))
    portfolio, skipped = normalize_data_api_positions(
        raw_positions, registry, cash_available=0.0
    )
    assert portfolio.positions == []
    assert len(skipped) == len(raw_positions)
    assert all(s["reason"] == "conditionId not in registry" for s in skipped)


def test_normalize_rejects_non_list_payload() -> None:
    registry = load_market_registry()  # use real registry; payload is bad anyway
    with pytest.raises(NormalizerError, match="list"):
        normalize_data_api_positions({"oops": "not a list"}, registry, cash_available=0)  # type: ignore[arg-type]


def test_normalize_outcome_mapping() -> None:
    # Build a payload with each outcome variant
    payload = [
        {
            "conditionId": "0xa",
            "size": 1,
            "avgPrice": 0.5,
            "curPrice": 0.5,
            "currentValue": 0.5,
            "cashPnl": 0,
            "outcome": "Yes",
            "title": "yes-market",
        },
        {
            "conditionId": "0xb",
            "size": 1,
            "avgPrice": 0.5,
            "curPrice": 0.5,
            "currentValue": 0.5,
            "cashPnl": 0,
            "outcome": "No",
            "title": "no-market",
        },
        {
            "conditionId": "0xc",
            "size": 1,
            "avgPrice": 0.5,
            "curPrice": 0.5,
            "currentValue": 0.5,
            "cashPnl": 0,
            "outcome": "Up",
            "title": "up-market",
        },
        {
            "conditionId": "0xd",
            "size": 1,
            "avgPrice": 0.5,
            "curPrice": 0.5,
            "currentValue": 0.5,
            "cashPnl": 0,
            "outcome": "Down",
            "title": "down-market",
        },
    ]
    registry = MarketRegistry.model_validate(
        {
            "markets": [
                _stub_market("m_yes", "0xa"),
                _stub_market("m_no", "0xb"),
                _stub_market("m_up", "0xc"),
                _stub_market("m_down", "0xd"),
            ]
        }
    )
    portfolio, skipped = normalize_data_api_positions(payload, registry, cash_available=0)
    assert skipped == []
    sides = {p.market_id: p.side for p in portfolio.positions}
    assert sides == {"m_yes": "YES", "m_no": "NO", "m_up": "YES", "m_down": "NO"}


def test_promote_writes_canonical_yaml_and_preserves_thesis_bucket(tmp_path: Path) -> None:
    registry_path, _ = _registry_for_fixture(tmp_path)

    # Existing portfolio with a thesis_bucket label on one market we'll re-import.
    existing = tmp_path / "portfolio_current.yaml"
    existing.write_text(
        "\n".join(
            [
                "as_of: 2026-04-01T00:00:00+00:00",
                "portfolio_value: 200.0",
                "cash_available: 50.0",
                "positions:",
                "  - market_id: fix_market_0",
                "    market_name: stale-name",
                '    side: "YES"',
                "    avg_price: 0.5",
                "    mark_price: 0.5",
                "    shares: 1.0",
                "    current_value: 0.5",
                "    pnl: 0",
                "    thesis_bucket: core_hormuz",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    output = tmp_path / "promoted.yaml"
    written_path, skipped = promote_data_api_positions(
        raw_path=FIXTURE,
        output_path=output,
        cash_available=75.0,
        registry_path=registry_path,
        portfolio_path_for_thesis=existing,
        now=datetime(2026, 5, 11, tzinfo=timezone.utc),
    )
    assert written_path == output
    assert skipped == []

    loaded = load_portfolio(output)
    assert loaded.cash_available == pytest.approx(75.0)
    fix_0 = next(p for p in loaded.positions if p.market_id == "fix_market_0")
    assert fix_0.thesis_bucket == "core_hormuz"
    # The newly-imported market_name should overwrite the stale one
    assert fix_0.market_name != "stale-name"


def _stub_market(market_id: str, condition_id: str) -> dict:
    return {
        "market_id": market_id,
        "name": market_id,
        "polymarket_url": "https://example.invalid",
        "category": "test",
        "rule_key": "test",
        "oracle_type": "pure_data",
        "preferred_side": "YES",
        "risk_flags": [],
        "resolution_date": "2027-01-01",
        "notes": "",
        "condition_id": condition_id,
    }
