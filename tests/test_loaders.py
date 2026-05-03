from __future__ import annotations

import pytest

from polymarket_desk.loaders import (
    LoaderError,
    load_live_state,
    load_market_registry,
    load_open_orders,
    load_portfolio,
)
from polymarket_desk.models import LiveState, OpenOrders


def test_load_yaml_context_files() -> None:
    registry = load_market_registry()
    portfolio = load_portfolio(registry=registry)
    open_orders = load_open_orders(registry=registry)
    live_state = load_live_state(registry=registry)

    assert len(registry.markets) == 3
    assert portfolio.cash_available >= 0
    assert open_orders.sell_orders[0].side == "NO"
    assert "hormuz_normal_may15" in live_state.watchlist


def test_portfolio_references_must_exist_in_registry(tmp_path) -> None:
    portfolio_path = tmp_path / "portfolio_current.yaml"
    portfolio_path.write_text(
        """
as_of: 2026-04-26T09:00:00-06:00
portfolio_value: 10
cash_available: 5
positions:
  - market_id: missing_market
    market_name: Missing
    side: "NO"
    avg_price: 0.5
    mark_price: 0.5
    shares: 1
    current_value: 0.5
    pnl: 0
    thesis_bucket: test
""".strip(),
        encoding="utf-8",
    )

    with pytest.raises(LoaderError, match="Unknown market_id"):
        load_portfolio(path=portfolio_path, registry=load_market_registry())


def test_open_orders_order_type_defaults_to_limit() -> None:
    orders = OpenOrders.model_validate(
        {
            "as_of": "2026-04-26T09:00:00-06:00",
            "buy_orders": [
                {
                    "market_id": "hormuz_normal_may15",
                    "side": "NO",
                    "price": 0.5,
                    "shares": 1,
                }
            ],
            "sell_orders": [],
        }
    )

    assert orders.buy_orders[0].order_type == "limit"


def test_open_orders_rejects_market_order_type() -> None:
    with pytest.raises(ValueError):
        OpenOrders.model_validate(
            {
                "as_of": "2026-04-26T09:00:00-06:00",
                "buy_orders": [
                    {
                        "market_id": "hormuz_normal_may15",
                        "side": "NO",
                        "price": 0.5,
                        "shares": 1,
                        "order_type": "market",
                    }
                ],
                "sell_orders": [],
            }
        )


def test_live_state_mode_accepts_arbitrary_non_empty_string() -> None:
    state = LiveState.model_validate(
        {
            "as_of": "2026-04-26T09:00:00-06:00",
            "mode": "manual_research_archive",
            "account_snapshot": {"portfolio_value": 100, "cash_available": 10},
            "active_thesis": [],
            "constraints": {},
            "watchlist": [],
            "notes": [],
        }
    )

    assert state.mode == "manual_research_archive"
