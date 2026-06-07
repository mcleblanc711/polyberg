from __future__ import annotations

from pathlib import Path
from typing import Any

from polyberg.loaders import load_market_registry
from polyberg.models import (
    Market,
    TradeTicket,
    TradeTicketAttribution,
    TradeTicketDecision,
    TradeTicketRejected,
)
from polyberg.validators import load_json, validate_adjudicator_output


def build_trade_ticket(
    adjudicator_output: Path,
    output_path: Path,
    registry_path: Path | None = None,
) -> Path:
    """Write the human ``.md`` ticket and a ledger-ready ``.json`` sibling.

    The JSON file is written next to ``output_path`` with a ``.json`` suffix; it
    is the structured half of the trade_ticket loop that Polygraph imports.
    """
    validate_adjudicator_output(adjudicator_output)
    payload = load_json(adjudicator_output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(render_trade_ticket(payload), encoding="utf-8")

    ticket = build_trade_ticket_payload(payload, registry_path)
    json_path = output_path.with_suffix(".json")
    json_path.write_text(ticket.model_dump_json(indent=2), encoding="utf-8")
    return output_path


def build_trade_ticket_payload(
    payload: dict[str, Any],
    registry_path: Path | None = None,
) -> TradeTicket:
    """Project the adjudicator output into the ledger-ready ticket model.

    Registry fields (``oracle_type``, ``thesis_bucket``, title, slug, rule key)
    are copied verbatim — this side does no enum mapping by design.
    """
    registry = load_market_registry(registry_path)
    by_id = {market.market_id: market for market in registry.markets}

    final_orders = payload.get("final_order_list", [])
    decisions = [
        _decision_from_order(order, by_id.get(order["market_id"])) for order in final_orders
    ]
    rejected = [
        TradeTicketRejected(
            market_id=item.get("market_id", ""),
            rationale=item.get("rationale", ""),
        )
        for item in payload.get("rejected_trades", [])
    ]
    human_review = (
        all(order.get("human_review_required", True) for order in final_orders)
        if final_orders
        else True
    )
    return TradeTicket(
        as_of=payload["as_of"],
        human_review_required=human_review,
        decisions=decisions,
        rejected=rejected,
    )


def _decision_from_order(order: dict[str, Any], market: Market | None) -> TradeTicketDecision:
    price = float(order.get("price", 0))
    shares = float(order.get("shares", 0))
    action = order.get("action", "")
    rationale = order.get("rationale", "")

    attributions: list[TradeTicketAttribution] = []
    support = order.get("source_model_support")
    if support:
        attributions.append(
            TradeTicketAttribution(
                source_model_support=support,
                recommended_price=price,
                recommended_size=shares,
                evidence=rationale,
            )
        )

    thesis_bucket = (market.thesis_bucket or None) if market else None
    return TradeTicketDecision(
        market_id=order["market_id"],
        market_slug=(market.event_slug or market.market_id) if market else order["market_id"],
        market_title=market.name if market else order["market_id"],
        side=order["side"],
        intent=action,
        decision_type=_decision_type(action),
        price_used=price,
        max_allocation=round(price * shares, 6),
        thesis_summary=rationale,
        rule_summary=market.rule_key if market else "",
        oracle_type=market.oracle_type if market else None,
        thesis_bucket=thesis_bucket,
        attributions=attributions,
    )


def _decision_type(action: str) -> str | None:
    lowered = action.lower()
    if "buy" in lowered:
        return "ENTRY"
    if any(token in lowered for token in ("sell", "trim", "reduce", "exit", "ladder")):
        return "EXIT"
    return None


def render_trade_ticket(payload: dict[str, Any]) -> str:
    final_orders = payload.get("final_order_list", [])
    buy_orders = [order for order in final_orders if "buy" in order.get("action", "").lower()]
    sell_orders = [order for order in final_orders if "sell" in order.get("action", "").lower()]
    other_orders = [
        order
        for order in final_orders
        if order not in buy_orders and order not in sell_orders
    ]
    rejected = payload.get("rejected_trades", [])
    lines = [
        "# Human Trade Ticket",
        "",
        "**HUMAN REVIEW REQUIRED. No orders were placed.**",
        "",
        f"- Timestamp: {payload.get('as_of')}",
        f"- Estimated cost: {estimate_total(buy_orders):.2f}",
        f"- Estimated proceeds: {estimate_total(sell_orders):.2f}",
        "",
        "## All Final Orders Requiring Human Review",
        render_order_table(final_orders),
        "",
        "## Buy Orders",
        render_order_table(buy_orders),
        "",
        "## Sell Orders",
        render_order_table(sell_orders),
        "",
        "## Other Final Orders",
        render_order_table(other_orders),
        "",
        "## Invalidation Triggers",
        render_bullets(payload.get("invalidation_triggers", [])),
        "",
        "## Missing Info Checklist",
        render_bullets(payload.get("missing_info_checklist", [])),
        "",
        "## Do-Not-Trade / Rejected Trades",
        render_rejected(rejected),
        "",
        "## Liquidity Warnings",
        render_liquidity_warnings(final_orders, payload.get("adjudicator_notes", [])),
        "",
        (
            "No orders were placed by this tool. Any Polymarket action must be reviewed "
            "and entered manually."
        ),
    ]
    return "\n".join(lines).strip() + "\n"


def estimate_total(orders: list[dict[str, Any]]) -> float:
    return sum(float(order.get("price", 0)) * float(order.get("shares", 0)) for order in orders)


def render_order_table(orders: list[dict[str, Any]]) -> str:
    if not orders:
        return "_None._"
    lines = [
        "| Market | Side | Action | Price | Shares | Rationale |",
        "| --- | --- | --- | ---: | ---: | --- |",
    ]
    for order in orders:
        lines.append(
            f"| {order['market_id']} | {order['side']} | {order['action']} | "
            f"{order['price']:.3f} | {order['shares']:g} | {order['rationale']} |"
        )
    return "\n".join(lines)


def render_bullets(items: list[str]) -> str:
    if not items:
        return "- None listed."
    return "\n".join(f"- {item}" for item in items)


def render_rejected(items: list[dict[str, Any]]) -> str:
    if not items:
        return "- None listed."
    return "\n".join(f"- {item.get('market_id')}: {item.get('rationale')}" for item in items)


def render_liquidity_warnings(final_orders: list[dict[str, Any]], notes: list[str]) -> str:
    warnings = []
    for order in final_orders:
        text = " ".join(str(order.get(field, "")) for field in ["action", "rationale"])
        if "liquid" in text.lower() or "spread" in text.lower():
            warnings.append(f"{order['market_id']}: {text}")
    warnings.extend(note for note in notes if "liquid" in note.lower() or "spread" in note.lower())
    return render_bullets(warnings)
