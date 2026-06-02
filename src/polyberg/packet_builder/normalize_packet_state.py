from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from polyberg.config import get_max_context_age_hours
from polyberg.models import (
    MarketRegistry,
    MarketSnapshot,
    OpenOrders,
    Order,
    Portfolio,
)
from polyberg.packet_builder.catalysts import parse_catalysts
from polyberg.packet_builder.collect_state import PacketState, collect_packet_state

# Constraint keys that must hold for every research session, regardless of what
# the local live_state.yaml happens to contain. These are surfaced verbatim in
# both packets so neither model can drift toward market orders or automation.
SAFETY_CONSTRAINT_KEYS = ("no_market_orders", "use_sell_ladders", "avoid_99c_dispute_tax")


@dataclass
class CanonicalPacket:
    """Model-agnostic, fully structured packet state.

    Both the GPT and Claude renderers consume this object and nothing else, so
    the factual layer is guaranteed identical between exports. Only instruction
    framing and layout differ downstream.
    """

    packet_generated_at: str
    source_timestamps: dict[str, str | None]
    freshness_warnings: list[str]
    missing_info: list[str]
    constraints: dict[str, object]
    portfolio: dict[str, object]
    exposure_summary: list[dict[str, object]]
    concentration_warnings: list[str]
    open_orders: dict[str, object]
    market_registry: list[dict[str, object]]
    market_snapshot: list[dict[str, object]] | None
    catalysts: dict[str, list[str]]
    trader_notes: list[str]
    unresolved_missing_information: list[str]
    raw_notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, object]:
        return {
            "packet_generated_at": self.packet_generated_at,
            "source_timestamps": self.source_timestamps,
            "freshness_warnings": self.freshness_warnings,
            "missing_info": self.missing_info,
            "constraints": self.constraints,
            "portfolio": self.portfolio,
            "exposure_summary": self.exposure_summary,
            "concentration_warnings": self.concentration_warnings,
            "open_orders": self.open_orders,
            "market_registry": self.market_registry,
            "market_snapshot": self.market_snapshot,
            "catalysts": self.catalysts,
            "trader_notes": self.trader_notes,
            "unresolved_missing_information": self.unresolved_missing_information,
        }

    def compact_state(self) -> dict[str, object]:
        """A trimmed JSON-safe view for the machine-readable tail of a packet.

        Carries the facts a model needs to reason about positions and gates
        without the prose; deliberately omits long catalyst text.
        """
        return {
            "packet_generated_at": self.packet_generated_at,
            "source_timestamps": self.source_timestamps,
            "constraints": self.constraints,
            "freshness_warnings": self.freshness_warnings,
            "missing_info": self.missing_info,
            "portfolio": {
                "as_of": self.portfolio["as_of"],
                "portfolio_value": self.portfolio["portfolio_value"],
                "cash_available": self.portfolio["cash_available"],
                "positions": [
                    {
                        "market_id": p["market_id"],
                        "side": p["side"],
                        "shares": p["shares"],
                        "avg_price": p["avg_price"],
                        "mark_price": p["mark_price"],
                        "current_value": p["current_value"],
                        "thesis_bucket": p["thesis_bucket"],
                    }
                    for p in self.portfolio["positions"]  # type: ignore[union-attr]
                ],
            },
            "exposure_summary": self.exposure_summary,
            "concentration_warnings": self.concentration_warnings,
            "open_orders": {
                "as_of": self.open_orders["as_of"],
                "buys": self.open_orders["buys"],
                "sells": self.open_orders["sells"],
            },
            "market_snapshot_present": self.market_snapshot is not None,
        }

    def compact_json(self) -> str:
        return json.dumps(self.compact_state(), indent=2, sort_keys=False)


def build_canonical_packet(
    now: datetime | None = None,
    context_dir: Path | None = None,
    snapshot_path: Path | None = None,
    state: PacketState | None = None,
) -> CanonicalPacket:
    if state is None:
        state = collect_packet_state(
            now=now, context_dir=context_dir, snapshot_path=snapshot_path
        )

    freshness_warnings = _compute_freshness_warnings(state)
    exposure_summary, concentration_warnings = _build_exposure(state.portfolio)
    missing_info = _build_missing_info(state)
    parsed = parse_catalysts(state.catalysts_markdown)

    return CanonicalPacket(
        packet_generated_at=state.now.isoformat(),
        source_timestamps={
            "portfolio_current": state.portfolio.as_of.isoformat(),
            "open_orders": state.open_orders.as_of.isoformat(),
            "market_snapshot": state.snapshot.as_of.isoformat() if state.snapshot else None,
            # recent_catalysts.md carries no machine timestamp; entries are
            # individually dated in their text.
            "catalysts": None,
        },
        freshness_warnings=freshness_warnings,
        missing_info=missing_info,
        constraints=_build_constraints(state),
        portfolio=_build_portfolio(state.portfolio),
        exposure_summary=exposure_summary,
        concentration_warnings=concentration_warnings,
        open_orders=_build_open_orders(state.open_orders),
        market_registry=_build_registry(state.registry),
        market_snapshot=_build_snapshot(state.snapshot),
        catalysts={
            "credible_reporting_watch": parsed.credible_reporting_watch,
            "noisy_social_media_watch": parsed.noisy_social_media_watch,
        },
        trader_notes=parsed.trader_notes,
        unresolved_missing_information=parsed.unresolved_missing_information,
        raw_notes=list(state.live_state.notes),
    )


def _compute_freshness_warnings(state: PacketState) -> list[str]:
    max_age = get_max_context_age_hours()
    timestamps = [
        state.live_state.as_of,
        state.portfolio.as_of,
        state.open_orders.as_of,
    ]
    if state.snapshot is not None:
        timestamps.append(state.snapshot.as_of)
    oldest = min(timestamps)
    age_hours = (state.now - oldest.astimezone(state.now.tzinfo)).total_seconds() / 3600
    distinct = {ts.isoformat() for ts in timestamps}

    warnings: list[str] = []
    if len(distinct) > 1:
        warnings.append("context files do not share the same as_of timestamp")
    if age_hours > max_age:
        warnings.append(f"oldest context is older than {max_age:g} hours")
    if age_hours < 0:
        warnings.append("one or more context timestamps are in the future")
    return warnings


def _build_constraints(state: PacketState) -> dict[str, object]:
    constraints = state.live_state.constraints
    return {
        "mode": "research_only",
        "no_market_orders": constraints.get("no_market_orders", True) is True,
        "use_sell_ladders": constraints.get("use_sell_ladders", True) is True,
        "avoid_99c_dispute_tax": constraints.get("avoid_99c_dispute_tax", True) is True,
        "automated_execution": False,
        "human_review_required": True,
    }


def _build_portfolio(portfolio: Portfolio) -> dict[str, object]:
    return {
        "as_of": portfolio.as_of.isoformat(),
        "portfolio_value": round(portfolio.portfolio_value, 2),
        "cash_available": round(portfolio.cash_available, 2),
        "positions": [
            {
                "market_id": p.market_id,
                "market_name": p.market_name,
                "side": p.side,
                "avg_price": p.avg_price,
                "mark_price": p.mark_price,
                "shares": p.shares,
                "current_value": round(p.current_value, 2),
                "pnl": round(p.pnl, 2),
                "thesis_bucket": p.thesis_bucket,
            }
            for p in portfolio.positions
        ],
    }


def _build_exposure(portfolio: Portfolio) -> tuple[list[dict[str, object]], list[str]]:
    total = portfolio.portfolio_value
    bucket_values: dict[str, float] = {}
    bucket_counts: dict[str, int] = {}
    warnings: list[str] = []
    for position in portfolio.positions:
        bucket_values[position.thesis_bucket] = (
            bucket_values.get(position.thesis_bucket, 0) + position.current_value
        )
        bucket_counts[position.thesis_bucket] = (
            bucket_counts.get(position.thesis_bucket, 0) + 1
        )
        if total > 0 and position.current_value / total > 0.35:
            warnings.append(
                f"single position {position.market_id} exceeds 35% of portfolio value"
            )

    if total > 0 and portfolio.cash_available / total < 0.05:
        warnings.append("cash is below 5% of portfolio value")

    summary: list[dict[str, object]] = []
    for bucket in sorted(bucket_values):
        value = bucket_values[bucket]
        percent = (value / total * 100) if total else 0.0
        if percent > 40:
            warnings.append(f"thesis bucket {bucket} exceeds 40% of portfolio value")
        summary.append(
            {
                "thesis_bucket": bucket,
                "current_value": round(value, 2),
                "percent_of_portfolio": round(percent, 1),
                "position_count": bucket_counts[bucket],
            }
        )
    return summary, warnings


def _order_to_dict(order: Order) -> dict[str, object]:
    return {
        "market_id": order.market_id,
        "side": order.side,
        "price": order.price,
        "shares": order.shares,
        "order_type": order.order_type,
        "notes": order.notes,
    }


def _build_open_orders(open_orders: OpenOrders) -> dict[str, object]:
    return {
        "as_of": open_orders.as_of.isoformat(),
        "buys": [_order_to_dict(o) for o in open_orders.buy_orders],
        "sells": [_order_to_dict(o) for o in open_orders.sell_orders],
    }


def _build_registry(registry: MarketRegistry) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    sorted_markets = sorted(
        registry.markets, key=lambda m: (m.thesis_bucket, m.resolution_date)
    )
    for market in sorted_markets:
        rule_risk = "not specified"
        if market.rule_risk is not None:
            rule_risk = (
                f"oracle={market.rule_risk.oracle_type}; "
                f"ambiguity={market.rule_risk.ambiguity}; "
                f"media_fallback={market.rule_risk.media_fallback}; "
                f"official_required={market.rule_risk.official_statement_required}; "
                f"dispute={market.rule_risk.dispute_risk}"
            )
        rows.append(
            {
                "market_id": market.market_id,
                "thesis_bucket": market.thesis_bucket or "(unassigned)",
                "name": market.name,
                "preferred_side": market.preferred_side,
                "rule_key": market.rule_key,
                "oracle_type": market.oracle_type,
                "resolution_date": market.resolution_date.isoformat(),
                "rule_risk": rule_risk,
                "risk_flags": list(market.risk_flags),
                "yes_token_id": market.yes_token_id,
                "no_token_id": market.no_token_id,
            }
        )
    return rows


def _build_snapshot(snapshot: MarketSnapshot | None) -> list[dict[str, object]] | None:
    if snapshot is None:
        return None
    return [
        {
            "market_id": m.market_id,
            "yes_price": m.yes_price,
            "no_price": m.no_price,
            "spread": m.spread,
            "orderbook_depth_top": m.orderbook_depth_top,
            "liquidity_warning": m.liquidity_warning,
            "missing_info": list(m.missing_info),
        }
        for m in snapshot.markets
    ]


def _build_missing_info(state: PacketState) -> list[str]:
    missing: list[str] = []
    if state.snapshot is None:
        missing.append("missing market snapshot")
    for market in state.registry.markets:
        if not market.yes_token_id:
            missing.append(f"{market.market_id}: missing YES token ID")
        if not market.no_token_id:
            missing.append(f"{market.market_id}: missing NO token ID")
    if state.snapshot is not None:
        by_id = {item.market_id: item for item in state.snapshot.markets}
        for position in state.portfolio.positions:
            item = by_id.get(position.market_id)
            if item is None or item.yes_price is None:
                missing.append(f"{position.market_id}: missing current mark in snapshot")
            if item is None or item.orderbook_depth_top is None:
                missing.append(f"{position.market_id}: missing order book depth")
            if item is not None:
                missing.extend(f"{position.market_id}: {info}" for info in item.missing_info)

    local_timestamps = {
        state.live_state.as_of.isoformat(),
        state.portfolio.as_of.isoformat(),
        state.open_orders.as_of.isoformat(),
    }
    if len(local_timestamps) > 1:
        missing.append("mismatched as_of timestamps across local context files")

    # Safety constraints that are missing or not strictly True are a gap the
    # model must be told about before recommending anything.
    constraints = state.live_state.constraints
    for key in SAFETY_CONSTRAINT_KEYS:
        if constraints.get(key) is not True:
            missing.append(f"safety constraint {key} is missing or not true")

    return sorted(set(missing))
