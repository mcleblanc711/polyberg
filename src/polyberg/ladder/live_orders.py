from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from polyberg.models import MarketRegistry, Side


@dataclass
class LiveRung:
    order_id: str
    market_id: str
    outcome: Side
    action: str  # "BUY" or "SELL"
    price: float
    original_size: float
    size_matched: float
    remaining: float


@dataclass
class UnmappedOrder:
    raw: dict[str, Any]


def build_token_index(registry: MarketRegistry) -> dict[str, tuple[str, Side]]:
    """Return {asset_id: (market_id, outcome)} for every token in the registry."""
    index: dict[str, tuple[str, Side]] = {}
    for market in registry.markets:
        if market.yes_token_id:
            index[market.yes_token_id] = (market.market_id, "YES")
        if market.no_token_id:
            index[market.no_token_id] = (market.market_id, "NO")
    return index


def live_rungs_from_raw(
    raw_orders: list[dict[str, Any]],
    registry: MarketRegistry,
) -> tuple[list[LiveRung], list[UnmappedOrder]]:
    """Convert raw CLOB order dicts to LiveRungs and collect unresolvable orders.

    Primary match: asset_id lookup in the registry token index.
    Cross-check: order.outcome must agree with the token-index outcome (mismatch raises).
    Filled orders (remaining <= 0) are silently dropped.
    """
    token_index = build_token_index(registry)
    rungs: list[LiveRung] = []
    unmapped: list[UnmappedOrder] = []

    for raw in raw_orders:
        asset_id = str(raw.get("asset_id", ""))
        entry = token_index.get(asset_id)
        if entry is None:
            unmapped.append(UnmappedOrder(raw=raw))
            continue

        market_id, outcome = entry

        raw_outcome = raw.get("outcome")
        if raw_outcome and str(raw_outcome).upper() != outcome:
            raise ValueError(
                f"Order {raw.get('id')!r}: asset_id maps to outcome={outcome!r} "
                f"but order.outcome={raw_outcome!r} — registry token index may be stale"
            )

        side = str(raw.get("side", "")).upper()
        if side not in ("BUY", "SELL"):
            unmapped.append(UnmappedOrder(raw=raw))
            continue

        try:
            price = float(raw["price"])
            original_size = float(raw["original_size"])
            size_matched = float(raw["size_matched"])
        except (KeyError, TypeError, ValueError):
            unmapped.append(UnmappedOrder(raw=raw))
            continue

        remaining = original_size - size_matched
        if remaining <= 0:
            continue

        rungs.append(
            LiveRung(
                order_id=str(raw.get("id", "")),
                market_id=market_id,
                outcome=outcome,
                action=side,
                price=price,
                original_size=original_size,
                size_matched=size_matched,
                remaining=remaining,
            )
        )

    return rungs, unmapped
