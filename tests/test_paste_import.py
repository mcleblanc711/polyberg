from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from polyberg.loaders import load_open_orders, load_portfolio
from polyberg.paste_import import PasteImportError, import_paste


def _registry_yaml(market_ids: list[str]) -> str:
    lines = ["markets:"]
    for mid in market_ids:
        lines.extend(
            [
                f"  - market_id: {mid}",
                f'    name: "{mid} market"',
                "    polymarket_url: https://example.invalid",
                "    category: test",
                "    rule_key: test",
                "    oracle_type: pure_data",
                '    preferred_side: "YES"',
                "    risk_flags: []",
                "    resolution_date: 2027-01-01",
                '    notes: ""',
            ]
        )
    return "\n".join(lines) + "\n"


def _portfolio_doc() -> dict:
    return {
        "as_of": "2026-05-11T00:00:00+00:00",
        "portfolio_value": 200.0,
        "cash_available": 50.0,
        "positions": [
            {
                "market_id": "m_a",
                "market_name": "Market A",
                "side": "YES",
                "avg_price": 0.5,
                "mark_price": 0.6,
                "shares": 10.0,
                "current_value": 6.0,
                "pnl": 1.0,
                "thesis_bucket": "",
            }
        ],
    }


def _orders_doc() -> dict:
    return {
        "as_of": "2026-05-11T00:00:00+00:00",
        "buy_orders": [
            {
                "market_id": "m_a",
                "side": "YES",
                "price": 0.3,
                "shares": 100.0,
                "order_type": "limit",
                "notes": "",
            }
        ],
        "sell_orders": [],
    }


def test_paste_import_portfolio_writes_canonical_yaml(tmp_path: Path) -> None:
    registry_path = tmp_path / "registry.yaml"
    registry_path.write_text(_registry_yaml(["m_a"]), encoding="utf-8")
    output = tmp_path / "portfolio_current.yaml"

    yaml_text = import_paste(
        kind="portfolio",
        raw_text=json.dumps(_portfolio_doc()),
        output_path=output,
        registry_path=registry_path,
    )

    assert output.exists()
    assert "market_id: m_a" in yaml_text
    loaded = load_portfolio(output)
    assert loaded.cash_available == pytest.approx(50.0)
    assert loaded.positions[0].market_id == "m_a"


def test_paste_import_orders_writes_canonical_yaml(tmp_path: Path) -> None:
    registry_path = tmp_path / "registry.yaml"
    registry_path.write_text(_registry_yaml(["m_a"]), encoding="utf-8")
    output = tmp_path / "open_orders.yaml"

    import_paste(
        kind="orders",
        raw_text=json.dumps(_orders_doc()),
        output_path=output,
        registry_path=registry_path,
    )

    loaded = load_open_orders(output)
    assert len(loaded.buy_orders) == 1
    assert loaded.buy_orders[0].market_id == "m_a"
    assert loaded.buy_orders[0].price == pytest.approx(0.3)


def test_paste_import_dry_run_does_not_write(tmp_path: Path) -> None:
    registry_path = tmp_path / "registry.yaml"
    registry_path.write_text(_registry_yaml(["m_a"]), encoding="utf-8")
    output = tmp_path / "portfolio_current.yaml"

    yaml_text = import_paste(
        kind="portfolio",
        raw_text=json.dumps(_portfolio_doc()),
        output_path=output,
        registry_path=registry_path,
        dry_run=True,
    )

    assert not output.exists()
    assert "cash_available" in yaml_text


def test_paste_import_invalid_json_raises(tmp_path: Path) -> None:
    registry_path = tmp_path / "registry.yaml"
    registry_path.write_text(_registry_yaml(["m_a"]), encoding="utf-8")
    with pytest.raises(PasteImportError, match="Invalid JSON"):
        import_paste(
            kind="portfolio",
            raw_text="{not json",
            output_path=tmp_path / "out.yaml",
            registry_path=registry_path,
        )


def test_paste_import_schema_violation_surfaces_pydantic_message(tmp_path: Path) -> None:
    registry_path = tmp_path / "registry.yaml"
    registry_path.write_text(_registry_yaml(["m_a"]), encoding="utf-8")
    bad = _portfolio_doc()
    bad["positions"][0]["avg_price"] = 1.5  # out of [0, 1] range

    with pytest.raises(PasteImportError, match="Schema validation failed"):
        import_paste(
            kind="portfolio",
            raw_text=json.dumps(bad),
            output_path=tmp_path / "out.yaml",
            registry_path=registry_path,
        )


def test_paste_import_rejects_unknown_market_id(tmp_path: Path) -> None:
    registry_path = tmp_path / "registry.yaml"
    registry_path.write_text(_registry_yaml(["m_a"]), encoding="utf-8")
    doc = _portfolio_doc()
    doc["positions"][0]["market_id"] = "m_b_not_in_registry"

    with pytest.raises(PasteImportError, match="Unknown market_id"):
        import_paste(
            kind="portfolio",
            raw_text=json.dumps(doc),
            output_path=tmp_path / "out.yaml",
            registry_path=registry_path,
        )


def test_paste_import_portfolio_preserves_existing_thesis_bucket(tmp_path: Path) -> None:
    registry_path = tmp_path / "registry.yaml"
    registry_path.write_text(_registry_yaml(["m_a"]), encoding="utf-8")

    existing = tmp_path / "portfolio_current.yaml"
    existing.write_text(
        "\n".join(
            [
                "as_of: 2026-04-01T00:00:00+00:00",
                "portfolio_value: 100.0",
                "cash_available: 25.0",
                "positions:",
                "  - market_id: m_a",
                "    market_name: stale",
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

    output = tmp_path / "new.yaml"
    import_paste(
        kind="portfolio",
        raw_text=json.dumps(_portfolio_doc()),
        output_path=output,
        registry_path=registry_path,
        portfolio_path_for_thesis=existing,
    )

    loaded = load_portfolio(output)
    assert loaded.positions[0].thesis_bucket == "core_hormuz"


def test_paste_import_auto_fills_as_of_when_omitted(tmp_path: Path) -> None:
    registry_path = tmp_path / "registry.yaml"
    registry_path.write_text(_registry_yaml(["m_a"]), encoding="utf-8")
    doc = _portfolio_doc()
    del doc["as_of"]

    output = tmp_path / "out.yaml"
    import_paste(
        kind="portfolio",
        raw_text=json.dumps(doc),
        output_path=output,
        registry_path=registry_path,
        now=datetime(2026, 5, 11, tzinfo=timezone.utc),
    )

    loaded = load_portfolio(output)
    assert loaded.as_of == datetime(2026, 5, 11, tzinfo=timezone.utc)


def test_paste_import_rejects_non_object_top_level(tmp_path: Path) -> None:
    registry_path = tmp_path / "registry.yaml"
    registry_path.write_text(_registry_yaml(["m_a"]), encoding="utf-8")
    with pytest.raises(PasteImportError, match="Top-level"):
        import_paste(
            kind="portfolio",
            raw_text=json.dumps([1, 2, 3]),
            output_path=tmp_path / "out.yaml",
            registry_path=registry_path,
        )
