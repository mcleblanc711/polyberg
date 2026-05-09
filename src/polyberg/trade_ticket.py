from __future__ import annotations

from pathlib import Path
from typing import Any

from polyberg.validators import load_json, validate_adjudicator_output


def build_trade_ticket(adjudicator_output: Path, output_path: Path) -> Path:
    validate_adjudicator_output(adjudicator_output)
    payload = load_json(adjudicator_output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(render_trade_ticket(payload), encoding="utf-8")
    return output_path


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
