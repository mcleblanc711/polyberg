"""Synthetic inputs for tests that must not depend on a user's local overlays."""

from __future__ import annotations

import pytest
import yaml


@pytest.fixture
def synthetic_context(tmp_path):
    directory = tmp_path / "synthetic-context"
    directory.mkdir()
    at = "2026-10-26T12:00:00Z"
    market = {
        "market_id": "synthetic_contract",
        "name": "Synthetic research contract",
        "polymarket_url": "https://example.invalid/synthetic",
        "category": "synthetic",
        "rule_key": "synthetic",
        "oracle_type": "synthetic",
        "preferred_side": "YES",
        "resolution_date": "2030-01-01",
        "notes": "Guaranteed synthetic fixture",
    }
    portfolio = {
        "as_of": at,
        "portfolio_value": 15.0,
        "cash_available": 10.0,
        "positions": [
            {
                "market_id": "synthetic_contract",
                "market_name": "Synthetic research contract",
                "side": "YES",
                "avg_price": 0.4,
                "mark_price": 0.5,
                "shares": 10.0,
                "current_value": 5.0,
                "pnl": 1.0,
                "thesis_bucket": "synthetic",
            }
        ],
    }
    inputs = {
        "market_registry.yaml": {"markets": [market]},
        "portfolio_current.yaml": portfolio,
        "open_orders.yaml": {"as_of": at, "buy_orders": [], "sell_orders": []},
        "live_state.yaml": {
            "as_of": at,
            "mode": "RESEARCH",
            "account_snapshot": {"portfolio_value": 15.0, "cash_available": 10.0},
            "active_thesis": [],
            "constraints": {"execution_allowed": False, "no_market_orders": True},
            "watchlist": ["synthetic_contract"],
            "notes": [],
        },
    }
    for filename, data in inputs.items():
        (directory / filename).write_text(yaml.safe_dump(data), encoding="utf-8")
    for filename in ["recent_catalysts.md", "stable_rules.md", "trading_principles.md"]:
        (directory / filename).write_text(
            "# Synthetic reference\n\nSynthetic test text.\n", encoding="utf-8"
        )
    return directory
