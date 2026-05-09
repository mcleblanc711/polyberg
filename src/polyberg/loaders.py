from __future__ import annotations

from pathlib import Path
from typing import Any, TypeVar

import yaml
from pydantic import BaseModel, ValidationError

from polyberg.config import repo_path
from polyberg.models import LiveState, MarketRegistry, MarketSnapshot, OpenOrders, Portfolio

T = TypeVar("T", bound=BaseModel)


class LoaderError(RuntimeError):
    pass


def read_text_file(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except OSError as exc:
        raise LoaderError(f"Unable to read {path}: {exc}") from exc


def load_yaml_file(path: Path) -> dict[str, Any]:
    try:
        with path.open("r", encoding="utf-8") as handle:
            data = yaml.safe_load(handle)
    except OSError as exc:
        raise LoaderError(f"Unable to read YAML file {path}: {exc}") from exc
    except yaml.YAMLError as exc:
        raise LoaderError(f"Invalid YAML in {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise LoaderError(f"Expected top-level mapping in {path}")
    return data


def parse_model(model_type: type[T], path: Path) -> T:
    data = load_yaml_file(path)
    try:
        return model_type.model_validate(data)
    except ValidationError as exc:
        raise LoaderError(f"Validation failed for {path}:\n{exc}") from exc


def load_market_registry(path: Path | None = None) -> MarketRegistry:
    return parse_model(MarketRegistry, path or repo_path("context", "market_registry.yaml"))


def context_path(context_dir: Path | None, filename: str) -> Path:
    return (context_dir or repo_path("context")).joinpath(filename)


def load_market_registry_from_context(context_dir: Path | None = None) -> MarketRegistry:
    return load_market_registry(context_path(context_dir, "market_registry.yaml"))


def load_portfolio(path: Path | None = None, registry: MarketRegistry | None = None) -> Portfolio:
    portfolio = parse_model(Portfolio, path or repo_path("context", "portfolio_current.yaml"))
    if registry is not None:
        validate_market_references(
            [position.market_id for position in portfolio.positions],
            registry,
            "portfolio positions",
        )
    return portfolio


def load_open_orders(
    path: Path | None = None,
    registry: MarketRegistry | None = None,
) -> OpenOrders:
    open_orders = parse_model(OpenOrders, path or repo_path("context", "open_orders.yaml"))
    if registry is not None:
        validate_market_references(
            [order.market_id for order in open_orders.buy_orders + open_orders.sell_orders],
            registry,
            "open orders",
        )
    return open_orders


def load_live_state(path: Path | None = None, registry: MarketRegistry | None = None) -> LiveState:
    live_state = parse_model(LiveState, path or repo_path("context", "live_state.yaml"))
    if registry is not None:
        validate_market_references(live_state.watchlist, registry, "live state watchlist")
    return live_state


def load_market_snapshot(path: Path) -> MarketSnapshot:
    data = load_yaml_file(path)
    try:
        return MarketSnapshot.model_validate(data)
    except ValidationError as exc:
        raise LoaderError(f"Validation failed for {path}:\n{exc}") from exc


def validate_market_references(
    market_ids: list[str], registry: MarketRegistry, context_label: str
) -> None:
    unknown = sorted(set(market_ids) - registry.market_ids)
    if unknown:
        raise LoaderError(
            f"Unknown market_id values in {context_label}: {', '.join(unknown)}. "
            "Add them to context/market_registry.yaml or fix the reference."
        )
