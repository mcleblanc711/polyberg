from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from polyberg.account_normalizer import (
    NormalizerError,
    normalize_clob_open_orders,
    normalize_data_api_positions,
    promote_balance,
    promote_clob_open_orders,
    promote_data_api_positions,
    read_usdc_balance,
)
from polyberg.loaders import load_market_registry, load_open_orders, load_portfolio
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
        now=datetime(2026, 5, 11, tzinfo=UTC),
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
        now=datetime(2026, 5, 11, tzinfo=UTC),
    )
    assert written_path == output
    assert skipped == []

    loaded = load_portfolio(output)
    assert loaded.cash_available == pytest.approx(75.0)
    fix_0 = next(p for p in loaded.positions if p.market_id == "fix_market_0")
    assert fix_0.thesis_bucket == "core_hormuz"
    # The newly-imported market_name should overwrite the stale one
    assert fix_0.market_name != "stale-name"


def test_read_usdc_balance_returns_float_from_well_formed_artifact(tmp_path: Path) -> None:
    path = tmp_path / "usdc_balance.json"
    path.write_text(
        json.dumps({"balance_usdc": "123.456789", "source": "polymarket_clob_balance_allowance"}),
        encoding="utf-8",
    )
    assert read_usdc_balance(path) == pytest.approx(123.456789)


def test_read_usdc_balance_returns_none_for_missing_file(tmp_path: Path) -> None:
    assert read_usdc_balance(tmp_path / "absent.json") is None


def test_read_usdc_balance_returns_none_for_invalid_json(tmp_path: Path) -> None:
    path = tmp_path / "usdc_balance.json"
    path.write_text("{not json", encoding="utf-8")
    assert read_usdc_balance(path) is None


def test_read_usdc_balance_returns_none_for_missing_field(tmp_path: Path) -> None:
    path = tmp_path / "usdc_balance.json"
    path.write_text(json.dumps({"source": "polymarket_clob_balance_allowance"}), encoding="utf-8")
    assert read_usdc_balance(path) is None


def test_read_usdc_balance_returns_none_for_non_numeric_field(tmp_path: Path) -> None:
    path = tmp_path / "usdc_balance.json"
    path.write_text(json.dumps({"balance_usdc": "abc"}), encoding="utf-8")
    assert read_usdc_balance(path) is None


def _write_existing_portfolio(path: Path, cash: float) -> None:
    path.write_text(
        "\n".join(
            [
                "as_of: 2026-04-01T00:00:00+00:00",
                "portfolio_value: 100.0",
                f"cash_available: {cash}",
                "positions:",
                "  - market_id: hormuz_normal_may15",
                "    market_name: Hormuz normal",
                '    side: "NO"',
                "    avg_price: 0.5",
                "    mark_price: 0.5",
                "    shares: 2.0",
                "    current_value: 1.0",
                "    pnl: 0",
                "    thesis_bucket: core_hormuz",
            ]
        )
        + "\n",
        encoding="utf-8",
    )


def test_promote_balance_updates_cash_and_preserves_positions(tmp_path: Path) -> None:
    balance = tmp_path / "usdc_balance.json"
    balance.write_text(json.dumps({"balance_usdc": "42.5"}), encoding="utf-8")
    portfolio_path = tmp_path / "portfolio_current.yaml"
    _write_existing_portfolio(portfolio_path, cash=10.0)

    updated, previous_cash = promote_balance(
        balance, portfolio_path, now=datetime(2026, 5, 15, tzinfo=UTC)
    )

    assert previous_cash == pytest.approx(10.0)
    assert updated.cash_available == pytest.approx(42.5)
    # portfolio_value = positions current_value (1.0) + new cash (42.5)
    assert updated.portfolio_value == pytest.approx(43.5)
    # Positions and thesis_bucket survive untouched.
    assert len(updated.positions) == 1
    assert updated.positions[0].market_id == "hormuz_normal_may15"
    assert updated.positions[0].thesis_bucket == "core_hormuz"


def test_promote_balance_raises_when_canonical_missing(tmp_path: Path) -> None:
    balance = tmp_path / "usdc_balance.json"
    balance.write_text(json.dumps({"balance_usdc": "10"}), encoding="utf-8")
    missing = tmp_path / "portfolio_current.yaml"  # not created

    with pytest.raises(NormalizerError, match="Run Positions PROMOTE first"):
        promote_balance(balance, missing)


def test_promote_balance_raises_when_balance_artifact_missing(tmp_path: Path) -> None:
    portfolio_path = tmp_path / "portfolio_current.yaml"
    _write_existing_portfolio(portfolio_path, cash=10.0)

    with pytest.raises(NormalizerError, match="import-clob-balance"):
        promote_balance(tmp_path / "absent.json", portfolio_path)


def _clob_order(
    *,
    order_id: str,
    market: str,
    side: str,
    outcome: str,
    price: str,
    original_size: str,
    size_matched: str = "0",
) -> dict:
    return {
        "id": order_id,
        "status": "LIVE",
        "market": market,
        "asset_id": "0xtoken",
        "side": side,
        "outcome": outcome,
        "price": price,
        "original_size": original_size,
        "size_matched": size_matched,
        "order_type": "GTC",
        "maker_address": "0xmaker",
        "owner": "0xowner",
        "expiration": "0",
        "associate_trades": [],
        "created_at": "2026-05-11T00:00:00Z",
    }


def test_normalize_clob_orders_splits_buys_and_sells(tmp_path: Path) -> None:
    registry = MarketRegistry.model_validate(
        {
            "markets": [
                _stub_market("m_a", "0xaaa"),
                _stub_market("m_b", "0xbbb"),
            ]
        }
    )
    payload = [
        _clob_order(
            order_id="ord-1",
            market="0xaaa",
            side="BUY",
            outcome="Yes",
            price="0.45",
            original_size="100",
        ),
        _clob_order(
            order_id="ord-2",
            market="0xbbb",
            side="SELL",
            outcome="No",
            price="0.72",
            original_size="50",
            size_matched="10",
        ),
    ]
    open_orders, skipped = normalize_clob_open_orders(
        payload, registry, now=datetime(2026, 5, 11, tzinfo=UTC)
    )

    assert skipped == []
    assert len(open_orders.buy_orders) == 1
    assert open_orders.buy_orders[0].market_id == "m_a"
    assert open_orders.buy_orders[0].side == "YES"
    assert open_orders.buy_orders[0].price == pytest.approx(0.45)
    assert open_orders.buy_orders[0].shares == pytest.approx(100.0)

    assert len(open_orders.sell_orders) == 1
    sell = open_orders.sell_orders[0]
    assert sell.market_id == "m_b"
    assert sell.side == "NO"
    assert sell.shares == pytest.approx(40.0)  # 50 - 10 matched


def test_normalize_clob_orders_skips_unknown_market_and_filled(tmp_path: Path) -> None:
    registry = MarketRegistry.model_validate(
        {"markets": [_stub_market("m_a", "0xaaa")]}
    )
    payload = [
        _clob_order(
            order_id="ord-unknown",
            market="0xnotinregistry",
            side="BUY",
            outcome="Yes",
            price="0.1",
            original_size="10",
        ),
        _clob_order(
            order_id="ord-filled",
            market="0xaaa",
            side="BUY",
            outcome="Yes",
            price="0.5",
            original_size="5",
            size_matched="5",
        ),
        _clob_order(
            order_id="ord-bad-direction",
            market="0xaaa",
            side="WEIRD",
            outcome="Yes",
            price="0.5",
            original_size="1",
        ),
    ]
    open_orders, skipped = normalize_clob_open_orders(payload, registry)

    assert open_orders.buy_orders == []
    assert open_orders.sell_orders == []
    reasons = {s["reason"] for s in skipped}
    assert "conditionId not in registry" in reasons
    assert "fully filled (remaining=0)" in reasons
    assert any("unknown trade direction" in r for r in reasons)


def test_promote_clob_open_orders_writes_canonical_yaml(tmp_path: Path) -> None:
    registry_path = tmp_path / "registry.yaml"
    registry_path.write_text(
        "\n".join(
            [
                "markets:",
                "  - market_id: m_a",
                "    name: Market A",
                "    polymarket_url: https://example.invalid",
                "    category: test",
                "    rule_key: test",
                "    oracle_type: pure_data",
                '    preferred_side: "YES"',
                "    risk_flags: []",
                "    resolution_date: 2027-01-01",
                '    notes: ""',
                '    condition_id: "0xaaa"',
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    raw_file = tmp_path / "open_orders_clob.json"
    raw_file.write_text(
        json.dumps(
            {
                "as_of": "2026-05-11T00:00:00+00:00",
                "source": "polymarket_clob_open_orders",
                "wallet_address": "0x1111111111111111111111111111111111111111",
                "payload": [
                    _clob_order(
                        order_id="ord-1",
                        market="0xaaa",
                        side="BUY",
                        outcome="Yes",
                        price="0.3",
                        original_size="20",
                    )
                ],
            }
        ),
        encoding="utf-8",
    )
    output = tmp_path / "open_orders.yaml"

    written, skipped = promote_clob_open_orders(
        raw_path=raw_file,
        output_path=output,
        registry_path=registry_path,
        now=datetime(2026, 5, 11, tzinfo=UTC),
    )

    assert written == output
    assert skipped == []
    loaded = load_open_orders(output)
    assert len(loaded.buy_orders) == 1
    assert loaded.buy_orders[0].market_id == "m_a"
    assert loaded.buy_orders[0].price == pytest.approx(0.3)


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
