from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from polyberg.books import filter_books_markdown
from polyberg.config import get_catalyst_window_hours, get_max_context_age_hours, get_timezone
from polyberg.lifecycle import MarketTypeFilter, packet_market_ids
from polyberg.loaders import context_path, read_text_file
from polyberg.models import LiveState, MarketRegistry, MarketSnapshot, OpenOrders, Portfolio
from polyberg.packet_builder.catalysts import filter_catalysts, parse_catalysts
from polyberg.packet_builder.collect_state import PacketState, collect_packet_state
from polyberg.packet_builder.normalize_packet_state import CanonicalPacket
from polyberg.packet_builder.session_writer import (
    SessionArtifact,
    SessionResult,
    write_session,
)


@dataclass(frozen=True)
class ContextTimestamp:
    label: str
    value: datetime


def build_packet(
    now: datetime | None = None,
    context_dir: Path | None = None,
    snapshot_path: Path | None = None,
    state: PacketState | None = None,
    *,
    include_resolved: bool = False,
    catalyst_window_hours: float | None = None,
    books_for: str = "active",
    type_filter: MarketTypeFilter | None = None,
) -> str:
    if state is None:
        state = collect_packet_state(
            now=now, context_dir=context_dir, snapshot_path=snapshot_path
        )
    registry = state.registry
    live_state = state.live_state
    portfolio = state.portfolio
    open_orders = state.open_orders
    snapshot = state.snapshot
    now = state.now

    if catalyst_window_hours is None:
        catalyst_window_hours = get_catalyst_window_hours()

    # Active set drives every trim: registry rows, books, and catalyst scope.
    active_ids = packet_market_ids(
        registry, portfolio, include_resolved=include_resolved, type_filter=type_filter
    )

    recent_catalysts = render_catalyst_watch(
        state.catalysts_markdown,
        now=now,
        window_hours=catalyst_window_hours,
        active_ids=active_ids,
    )
    order_books_md = state.order_books_markdown
    book_ids = active_ids if books_for != "all" else None
    if order_books_md and book_ids is not None:
        order_books_md = filter_books_markdown(order_books_md, book_ids)

    freshness_warnings = _compute_freshness_warnings(
        live_state, portfolio, open_orders, snapshot, now
    )

    sections = [
        "# Polymarket Research Packet",
        render_packet_metadata(now, freshness_warnings),
        "## Model Instructions",
        "- Treat factual/source data, trader notes, and model interpretation as separate layers.",
        "- Do not suggest market orders or automated execution.",
        "- Treat Twitter/X sentiment and rumours as noisy catalyst-only information.",
        "- Output structured JSON and assume human review is required before action.",
        "- Stable trading rules and principles are in polymarket_rules.md (provided separately).",
        "## Missing Info And Safety Warnings",
        render_missing_info_and_warnings(live_state, portfolio, open_orders, registry, snapshot),
        "## Context Freshness Audit",
        render_freshness_audit(live_state, portfolio, open_orders, snapshot=snapshot, now=now,
                               freshness_warnings=freshness_warnings),
        "## Factual Source Data",
        render_live_state(live_state, portfolio),
        render_portfolio(portfolio),
        render_exposure_summary(portfolio),
        render_open_orders(open_orders),
        render_market_registry(registry, active_ids),
        render_registry_thesis_summary(registry, active_ids),
        render_snapshot_summary(snapshot) if snapshot else "### Market Snapshot\n_None provided._",
        (
            order_books_md.strip()
            if order_books_md
            else "## Live Order Books\n\n_Not fetched — run `polyberg fetch-books`. "
            "No live book = no order._"
        ),
        "## Trader Notes And Catalyst Watch",
        recent_catalysts.strip(),
        "## Unresolved/Missing Information",
        (
            "- Live order book depth is in the Live Order Books section above."
            if order_books_md
            else "- Current live order book depth is not included — run `polyberg fetch-books`."
        ),
        "- Model outputs are untrusted until validated against local schemas.",
    ]
    return "\n\n".join(sections).strip() + "\n"


def render_rules(principles: str, stable_rules: str) -> str:
    sections = [
        "# Polymarket Rules Reference",
        "## Stable Trading Principles",
        principles.strip(),
        "## Stable Rules Reference",
        stable_rules.strip(),
    ]
    return "\n\n".join(sections).strip() + "\n"


def build_rules(context_dir: Path | None = None) -> str:
    principles = read_text_file(context_path(context_dir, "trading_principles.md"))
    stable_rules = read_text_file(context_path(context_dir, "stable_rules.md"))
    return render_rules(principles, stable_rules)


def render_packet_from_session(
    payload: dict[str, Any], state: PacketState, canonical: CanonicalPacket
) -> str:
    """Session-artifact renderer: trim flags come from the payload, not closures."""
    params = payload["build_parameters"]
    raw_filter = params["type_filter"]
    type_filter = (
        MarketTypeFilter(
            category=raw_filter["category"],
            thesis_bucket=raw_filter["thesis_bucket"],
            rule_key=raw_filter["rule_key"],
        )
        if raw_filter
        else None
    )
    return build_packet(
        state=state,
        include_resolved=params["include_resolved"],
        catalyst_window_hours=params["catalyst_window_hours"],
        books_for=params["books_for"],
        type_filter=type_filter,
    )


def render_rules_from_session(
    payload: dict[str, Any], state: PacketState, canonical: CanonicalPacket
) -> str:
    static = payload["static_reference"]
    return render_rules(static["trading_principles"], static["stable_rules"])


def write_packet(
    output_path: Path,
    context_dir: Path | None = None,
    snapshot_path: Path | None = None,
    *,
    include_resolved: bool = False,
    catalyst_window_hours: float | None = None,
    books_for: str = "active",
    type_filter: MarketTypeFilter | None = None,
    sessions_root: Path | None = None,
    latest_pointer: Path | None = None,
) -> SessionResult:
    """Build the legacy packet + rules through the session pipeline.

    The session dir keeps canonical filenames (packet.md, polymarket_rules.md);
    mirrors land at the caller's output path and its sibling, exactly as before.
    """
    artifacts = [
        SessionArtifact(
            key="packet_legacy",
            filename="packet.md",
            render=render_packet_from_session,
            mirror_to=output_path,
        ),
        SessionArtifact(
            key="rules",
            filename="polymarket_rules.md",
            render=render_rules_from_session,
            mirror_to=output_path.parent / "polymarket_rules.md",
        ),
    ]
    return write_session(
        artifacts,
        targets=["legacy"],
        context_dir=context_dir,
        snapshot_path=snapshot_path,
        include_resolved=include_resolved,
        catalyst_window_hours=catalyst_window_hours,
        books_for=books_for,
        type_filter=type_filter,
        sessions_root=sessions_root,
        latest_pointer=latest_pointer,
    )


def render_catalyst_watch(
    markdown: str,
    *,
    now: datetime,
    window_hours: float,
    active_ids: set[str],
) -> str:
    """Render the catalyst watch, windowed + scoped to the active set.

    The credible/noisy watch lists are limited to entries ingested within the
    window and tagged to an active-set market, and deduplicated; trader notes and
    unresolved/missing info pass through. Replaces the old verbatim dump of
    recent_catalysts.md.
    """
    parsed = filter_catalysts(
        parse_catalysts(markdown),
        now=now,
        window_hours=window_hours,
        active_ids=active_ids,
    )

    def _bullets(items: list[str]) -> list[str]:
        return [f"- {item}" for item in items] or ["- none in window/scope"]

    lines = [
        f"### Credible Reporting Watch (last {window_hours:g}h, active markets)",
        *_bullets(parsed.credible_reporting_watch),
        "",
        f"### Noisy Social-Media And Rumour Watch (last {window_hours:g}h, active markets)",
        *_bullets(parsed.noisy_social_media_watch),
        "",
        "### Trader Interpretation Notes",
        *_bullets(parsed.trader_notes),
        "",
        "### Unresolved/Missing Information",
        *_bullets(parsed.unresolved_missing_information),
    ]
    return "\n".join(lines)


def render_packet_metadata(now: datetime, freshness_warnings: list[str]) -> str:
    lines = [
        "## Packet Metadata",
        f"- generated_at: {now.isoformat()}",
        "- freshness_warnings:",
    ]
    if freshness_warnings:
        lines.extend(f"  - {w}" for w in freshness_warnings)
    else:
        lines.append("  - none")
    return "\n".join(lines)


def _compute_freshness_warnings(
    live_state: LiveState,
    portfolio: Portfolio,
    open_orders: OpenOrders,
    snapshot: MarketSnapshot | None,
    now: datetime,
) -> list[str]:
    max_context_age_hours = get_max_context_age_hours()
    # Ingest-time only: keyed on locally fetched context file as_of, never on the
    # event dates inside catalyst content. The optional supplemental snapshot is
    # not a freshness driver — live books carry their own per-book provenance.
    timestamps = [
        live_state.as_of,
        portfolio.as_of,
        open_orders.as_of,
    ]
    oldest = min(timestamps)
    age_hours = (now - oldest.astimezone(now.tzinfo)).total_seconds() / 3600
    distinct_values = {ts.isoformat() for ts in timestamps}

    warnings = []
    if len(distinct_values) > 1:
        warnings.append("context files do not share the same as_of timestamp")
    if age_hours > max_context_age_hours:
        warnings.append(f"oldest context is older than {max_context_age_hours:g} hours")
    if age_hours < 0:
        warnings.append("one or more context timestamps are in the future")
    return warnings


def render_live_state(live_state: LiveState, portfolio: Portfolio | None = None) -> str:
    cash = (
        portfolio.cash_available
        if portfolio is not None
        else live_state.account_snapshot.cash_available
    )
    port_value = (
        portfolio.portfolio_value
        if portfolio is not None
        else live_state.account_snapshot.portfolio_value
    )
    lines = [
        "### Live State",
        f"- As of: {live_state.as_of.isoformat()}",
        f"- Mode: {live_state.mode}",
        f"- Cash available: {cash:.2f}",
        f"- Portfolio value: {port_value:.2f}",
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
    snapshot: MarketSnapshot | None = None,
    now: datetime | None = None,
    freshness_warnings: list[str] | None = None,
) -> str:
    if now is None:
        now = datetime.now(get_timezone())
    elif now.tzinfo is None or now.utcoffset() is None:
        now = now.replace(tzinfo=get_timezone())

    timestamps = [
        ContextTimestamp("live_state", live_state.as_of),
        ContextTimestamp("portfolio_current", portfolio.as_of),
        ContextTimestamp("open_orders", open_orders.as_of),
    ]
    if snapshot is not None:
        timestamps.append(ContextTimestamp("market_snapshot", snapshot.as_of))
    newest = max(item.value for item in timestamps)
    oldest = min(item.value for item in timestamps)

    if freshness_warnings is None:
        freshness_warnings = _compute_freshness_warnings(
        live_state, portfolio, open_orders, snapshot, now
    )

    lines = [
        f"- Packet built at: {now.isoformat()}",
        f"- Oldest context timestamp: {oldest.isoformat()}",
        f"- Newest context timestamp: {newest.isoformat()}",
        "- Source timestamps:",
    ]
    lines.extend(f"  - {item.label}: {item.value.isoformat()}" for item in timestamps)

    if freshness_warnings:
        lines.append("- Freshness warnings:")
        lines.extend(f"  - {w}" for w in freshness_warnings)
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


def render_exposure_summary(portfolio: Portfolio) -> str:
    total = portfolio.portfolio_value
    bucket_values: dict[str, float] = {}
    bucket_counts: dict[str, int] = {}
    warnings: list[str] = []
    for position in portfolio.positions:
        bucket_values[position.thesis_bucket] = (
            bucket_values.get(position.thesis_bucket, 0) + position.current_value
        )
        bucket_counts[position.thesis_bucket] = bucket_counts.get(position.thesis_bucket, 0) + 1
        if total > 0 and position.current_value / total > 0.35:
            warnings.append(f"single position {position.market_id} exceeds 35% of portfolio value")

    if total > 0 and portfolio.cash_available / total < 0.05:
        warnings.append("cash is below 5% of portfolio value")

    lines = [
        "### Exposure Summary By Thesis Bucket",
        "| Thesis bucket | Current value | Percent of portfolio | Position count |",
        "| --- | ---: | ---: | ---: |",
    ]
    for bucket in sorted(bucket_values):
        value = bucket_values[bucket]
        percent = (value / total * 100) if total else 0
        if percent > 40:
            warnings.append(f"thesis bucket {bucket} exceeds 40% of portfolio value")
        lines.append(f"| {bucket} | {value:.2f} | {percent:.1f}% | {bucket_counts[bucket]} |")
    if warnings:
        lines.append("")
        lines.append("- Concentration warnings:")
        lines.extend(f"  - {warning}" for warning in warnings)
    else:
        lines.extend(["", "- Concentration warnings: none from local portfolio values"])
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


def render_market_registry(registry: MarketRegistry, active_ids: set[str]) -> str:
    lines = [
        "### Market Registry Summary",
        "| Market ID | Lifecycle | Thesis | Name | Preferred side | Rule key | Oracle | "
        "Resolution | Rule risk | Risk flags |",
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    sorted_markets = sorted(
        (m for m in registry.markets if m.market_id in active_ids),
        key=lambda m: (m.thesis_bucket, m.resolution_date),
    )
    for market in sorted_markets:
        flags = ", ".join(market.risk_flags)
        rule_risk = "not specified"
        if market.rule_risk is not None:
            rule_risk = (
                f"oracle={market.rule_risk.oracle_type}; ambiguity={market.rule_risk.ambiguity}; "
                f"media_fallback={market.rule_risk.media_fallback}; "
                f"official_required={market.rule_risk.official_statement_required}; "
                f"dispute={market.rule_risk.dispute_risk}"
            )
        lines.append(
            f"| {market.market_id} | {market.lifecycle} | {market.thesis_bucket} | {market.name} | "
            f"{market.preferred_side} | "
            f"{market.rule_key} | {market.oracle_type} | {market.resolution_date.isoformat()} | "
            f"{rule_risk} | {flags} |"
        )
    return "\n".join(lines)


def render_registry_thesis_summary(registry: MarketRegistry, active_ids: set[str]) -> str:
    bucket_counts: dict[str, int] = {}
    for market in registry.markets:
        if market.market_id not in active_ids:
            continue
        bucket = market.thesis_bucket or "(unassigned)"
        bucket_counts[bucket] = bucket_counts.get(bucket, 0) + 1
    lines = [
        "### Market Registry — Thesis Summary",
        "| Thesis | Market count |",
        "| --- | ---: |",
    ]
    for bucket in sorted(bucket_counts):
        lines.append(f"| {bucket} | {bucket_counts[bucket]} |")
    return "\n".join(lines)


def render_missing_info_and_warnings(
    live_state: LiveState,
    portfolio: Portfolio,
    open_orders: OpenOrders,
    registry: MarketRegistry,
    snapshot: MarketSnapshot | None,
) -> str:
    lines: list[str] = []
    safety_warnings = render_safety_warnings(live_state)
    if safety_warnings:
        lines.append("- Safety constraint warnings:")
        lines.extend(f"  - {warning}" for warning in safety_warnings)
    else:
        lines.append("- Safety constraint warnings: none from local constraints")

    missing = []
    for market in registry.markets:
        if not market.yes_token_id:
            missing.append(f"{market.market_id}: missing YES token ID")
        if not market.no_token_id:
            missing.append(f"{market.market_id}: missing NO token ID")
    # Empty thesis_bucket is INFO, not a blocker — exposure groups by rule_key.
    for position in portfolio.positions:
        if not position.thesis_bucket:
            missing.append(
                f"{position.market_id}: thesis_bucket empty (INFO — exposure grouped by "
                f"rule_key fallback)"
            )
    local_timestamps = {
        live_state.as_of.isoformat(),
        portfolio.as_of.isoformat(),
        open_orders.as_of.isoformat(),
    }
    if len(local_timestamps) > 1:
        missing.append("mismatched as_of timestamps across local context files")
    lines.append("- Missing info:")
    if missing:
        lines.extend(f"  - {item}" for item in sorted(set(missing)))
    else:
        lines.append("  - none from local files")
    return "\n".join(lines)


def render_safety_warnings(live_state: LiveState) -> list[str]:
    constraints = live_state.constraints
    checks = {
        "no_market_orders": "no_market_orders is missing or false",
        "use_sell_ladders": "use_sell_ladders is missing or false",
        "avoid_99c_dispute_tax": "avoid_99c_dispute_tax is missing or false",
    }
    return [message for key, message in checks.items() if constraints.get(key) is not True]


def render_snapshot_summary(snapshot: MarketSnapshot) -> str:
    lines = [
        "### Market Snapshot",
        f"- As of: {snapshot.as_of.isoformat()}",
        "| Market | YES | NO | Spread | Top depth | Liquidity warning | Missing info |",
        "| --- | ---: | ---: | ---: | ---: | --- | --- |",
    ]
    for market in snapshot.markets:
        lines.append(
            f"| {market.market_id} | {format_optional_price(market.yes_price)} | "
            f"{format_optional_price(market.no_price)} | {format_optional_price(market.spread)} | "
            f"{format_optional_number(market.orderbook_depth_top)} | {market.liquidity_warning} | "
            f"{'; '.join(market.missing_info)} |"
        )
    return "\n".join(lines)


def format_optional_price(value: float | None) -> str:
    return "missing" if value is None else f"{value:.3f}"


def format_optional_number(value: float | None) -> str:
    return "missing" if value is None else f"{value:g}"
