from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from polymarket_desk.config import DEFAULT_TIMEZONE, repo_path
from polymarket_desk.loaders import (
    load_live_state,
    load_market_registry,
    load_open_orders,
    load_portfolio,
    read_text_file,
)
from polymarket_desk.models import LiveState, MarketRegistry, OpenOrders, Portfolio

MAX_CONTEXT_AGE_HOURS = 36


@dataclass(frozen=True)
class ContextTimestamp:
    label: str
    value: datetime


def build_packet(now: datetime | None = None) -> str:
    registry = load_market_registry()
    live_state = load_live_state(registry=registry)
    portfolio = load_portfolio(registry=registry)
    open_orders = load_open_orders(registry=registry)
    recent_catalysts = read_text_file(repo_path("context", "recent_catalysts.md"))
    principles = read_text_file(repo_path("context", "trading_principles.md"))
    stable_rules = read_text_file(repo_path("context", "stable_rules.md"))

    sections = [
        "# Polymarket Research Packet",
        "## Model Instructions",
        "- Treat factual/source data, trader notes, and model interpretation as separate layers.",
        "- Do not suggest market orders or automated execution.",
        "- Treat Twitter/X sentiment and rumours as noisy catalyst-only information.",
        "- Output structured JSON and assume human review is required before action.",
        "## Context Freshness Audit",
        render_freshness_audit(live_state, portfolio, open_orders, now=now),
        "## Factual Source Data",
        render_live_state(live_state),
        render_portfolio(portfolio),
        render_open_orders(open_orders),
        render_market_registry(registry),
        "## Trader Notes And Catalyst Watch",
        recent_catalysts.strip(),
        "## Stable Trading Principles",
        principles.strip(),
        "## Stable Rules Reference",
        stable_rules.strip(),
        "## Unresolved/Missing Information",
        "- Current live order book depth is not included unless manually added.",
        "- Live API data is intentionally out of scope for this first pass.",
        "- Model outputs are untrusted until validated against local schemas.",
    ]
    return "\n\n".join(sections).strip() + "\n"


def write_packet(output_path: Path) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(build_packet(), encoding="utf-8")
    return output_path


def render_live_state(live_state: LiveState) -> str:
    lines = [
        "### Live State",
        f"- As of: {live_state.as_of.isoformat()}",
        f"- Mode: {live_state.mode}",
        f"- Cash available: {live_state.account_snapshot.cash_available:.2f}",
        f"- Portfolio value: {live_state.account_snapshot.portfolio_value:.2f}",
        "- Active thesis:",
    ]
    lines.extend(f"  - {item}" for item in live_state.active_thesis)
    lines.append("- Constraints:")
    for key in sorted(live_state.constraints):
        lines.append(f"  - {key}: {live_state.constraints[key]}")
    lines.append("- Watchlist:")
    lines.extend(f"  - {market_id}" for market_id in live_state.watchlist)
    lines.append("- Notes:")
    lines.extend(f"  - {note}" for note in live_state.notes)
    return "\n".join(lines)


def render_freshness_audit(
    live_state: LiveState,
    portfolio: Portfolio,
    open_orders: OpenOrders,
    now: datetime | None = None,
) -> str:
    if now is None:
        now = datetime.now(ZoneInfo(DEFAULT_TIMEZONE))
    elif now.tzinfo is None or now.utcoffset() is None:
        now = now.replace(tzinfo=ZoneInfo(DEFAULT_TIMEZONE))

    timestamps = [
        ContextTimestamp("live_state", live_state.as_of),
        ContextTimestamp("portfolio_current", portfolio.as_of),
        ContextTimestamp("open_orders", open_orders.as_of),
    ]
    newest = max(item.value for item in timestamps)
    oldest = min(item.value for item in timestamps)
    age_hours = (now - oldest.astimezone(now.tzinfo)).total_seconds() / 3600
    distinct_values = {item.value.isoformat() for item in timestamps}

    lines = [
        f"- Packet built at: {now.isoformat()}",
        f"- Oldest context timestamp: {oldest.isoformat()}",
        f"- Newest context timestamp: {newest.isoformat()}",
        "- Source timestamps:",
    ]
    lines.extend(f"  - {item.label}: {item.value.isoformat()}" for item in timestamps)

    warnings = []
    if len(distinct_values) > 1:
        warnings.append("context files do not share the same as_of timestamp")
    if age_hours > MAX_CONTEXT_AGE_HOURS:
        warnings.append(f"oldest context is older than {MAX_CONTEXT_AGE_HOURS} hours")
    if age_hours < 0:
        warnings.append("one or more context timestamps are in the future")

    if warnings:
        lines.append("- Freshness warnings:")
        lines.extend(f"  - {warning}" for warning in warnings)
    else:
        lines.append("- Freshness warnings: none from local timestamps")

    lines.append(
        "- Important: this audit checks local file timestamps only; it does not verify "
        "live markets, news, or order books."
    )
    return "\n".join(lines)


def render_portfolio(portfolio: Portfolio) -> str:
    lines = [
        "### Portfolio",
        f"- As of: {portfolio.as_of.isoformat()}",
        f"- Portfolio value: {portfolio.portfolio_value:.2f}",
        f"- Cash available: {portfolio.cash_available:.2f}",
        "",
        "| Market | Side | Avg | Mark | Shares | Current value | PnL | Thesis |",
        "| --- | --- | ---: | ---: | ---: | ---: | ---: | --- |",
    ]
    for position in portfolio.positions:
        lines.append(
            "| "
            f"{position.market_id} | {position.side} | {position.avg_price:.3f} | "
            f"{position.mark_price:.3f} | {position.shares:g} | "
            f"{position.current_value:.2f} | {position.pnl:.2f} | {position.thesis_bucket} |"
        )
    return "\n".join(lines)


def render_open_orders(open_orders: OpenOrders) -> str:
    lines = [
        "### Open Orders",
        f"- As of: {open_orders.as_of.isoformat()}",
        "",
        "#### Buy Orders",
        render_order_table(open_orders.buy_orders),
        "#### Sell Orders",
        render_order_table(open_orders.sell_orders),
    ]
    return "\n".join(lines)


def render_order_table(orders: list) -> str:
    if not orders:
        return "_None._"
    lines = [
        "| Market | Side | Price | Shares | Type | Notes |",
        "| --- | --- | ---: | ---: | --- | --- |",
    ]
    for order in orders:
        lines.append(
            f"| {order.market_id} | {order.side} | {order.price:.3f} | "
            f"{order.shares:g} | {order.order_type} | {order.notes} |"
        )
    return "\n".join(lines)


def render_market_registry(registry: MarketRegistry) -> str:
    lines = [
        "### Market Registry Summary",
        "| Market ID | Name | Preferred side | Rule key | Oracle | Resolution | Risk flags |",
        "| --- | --- | --- | --- | --- | --- | --- |",
    ]
    for market in registry.markets:
        flags = ", ".join(market.risk_flags)
        lines.append(
            f"| {market.market_id} | {market.name} | {market.preferred_side} | "
            f"{market.rule_key} | {market.oracle_type} | {market.resolution_date.isoformat()} | "
            f"{flags} |"
        )
    return "\n".join(lines)
