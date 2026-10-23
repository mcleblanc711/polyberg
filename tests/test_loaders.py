from __future__ import annotations

import pytest

from polyberg.loaders import (
    LoaderError,
    load_live_state,
    load_market_registry,
    load_open_orders,
    load_portfolio,
)
from polyberg.models import LiveState, OpenOrders

# Registry ids from the tracked context/market_registry.yaml.
HORMUZ_NORMAL_OCT31 = "strait_hormuz_traffic_returns_normal_october_31_20260810151043583"
HORMUZ_NORMAL_NOV30 = "strait_hormuz_traffic_returns_normal_november_30_20260810151158765"
HORMUZ_40_ANY_DAY_OCT31 = "ships_transit_strait_hormuz_october_31_40"


def test_load_yaml_context_files() -> None:
    registry = load_market_registry()
    portfolio = load_portfolio(registry=registry)
    open_orders = load_open_orders(registry=registry)
    live_state = load_live_state(registry=registry)

    market_ids = {m.market_id for m in registry.markets}
    expected = {HORMUZ_NORMAL_OCT31, HORMUZ_NORMAL_NOV30, HORMUZ_40_ANY_DAY_OCT31}
    assert expected <= market_ids
    assert portfolio.cash_available >= 0
    assert isinstance(open_orders.buy_orders, list)
    assert isinstance(live_state.watchlist, list)


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
