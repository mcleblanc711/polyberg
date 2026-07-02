from __future__ import annotations

"""Shared markdown table/list helpers for the model-specific packet renderers.

These operate purely on the canonical packet dicts (see
``normalize_packet_state.CanonicalPacket``) so the GPT and Claude renderers
share one source of truth for facts and only diverge on framing.
"""

EMPTY_ORDERS = "_None._"


def _fmt_price(value: float | None) -> str:
    return "missing" if value is None else f"{value:.3f}"


def _fmt_num(value: float | None) -> str:
    return "missing" if value is None else f"{value:g}"


def positions_table(positions: list[dict]) -> str:
    if not positions:
        return "_No open positions._"
    lines = [
        "| Market | Band | Side | Avg | Mark | Shares | Current value | PnL | Thesis |",
        "| --- | --- | --- | ---: | ---: | ---: | ---: | ---: | --- |",
    ]
    for p in positions:
        band = p.get("band_label") or ""
        lines.append(
            f"| {p['market_id']} | {band} | {p['side']} | {p['avg_price']:.3f} | "
            f"{p['mark_price']:.3f} | {p['shares']:g} | {p['current_value']:.2f} | "
            f"{p['pnl']:.2f} | {p['thesis_bucket']} |"
        )
    return "\n".join(lines)


def exposure_table(exposure_summary: list[dict]) -> str:
    if not exposure_summary:
        return "_No exposure to summarize._"
    lines = [
        "| Thesis bucket | Current value | Percent of portfolio | Position count |",
        "| --- | ---: | ---: | ---: |",
    ]
    for row in exposure_summary:
        lines.append(
            f"| {row['thesis_bucket']} | {row['current_value']:.2f} | "
            f"{row['percent_of_portfolio']:.1f}% | {row['position_count']} |"
        )
    return "\n".join(lines)


def orders_table(orders: list[dict]) -> str:
    if not orders:
        return EMPTY_ORDERS
    lines = [
        "| Market | Side | Price | Shares | Type | Notes |",
        "| --- | --- | ---: | ---: | --- | --- |",
    ]
    for o in orders:
        lines.append(
            f"| {o['market_id']} | {o['side']} | {o['price']:.3f} | "
            f"{o['shares']:g} | {o['order_type']} | {o['notes']} |"
        )
    return "\n".join(lines)


def registry_table(market_registry: list[dict]) -> str:
    if not market_registry:
        return "_Registry is empty._"
    lines = [
        "| Market ID | Lifecycle | Thesis | Name | Preferred side | Rule key | Oracle | "
        "Resolution | Rule risk | Risk flags |",
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for m in market_registry:
        flags = ", ".join(m["risk_flags"])
        lines.append(
            f"| {m['market_id']} | {m.get('lifecycle', 'active')} | {m['thesis_bucket']} | "
            f"{m['name']} | {m['preferred_side']} | {m['rule_key']} | {m['oracle_type']} | "
            f"{m['resolution_date']} | {m['rule_risk']} | {flags} |"
        )
    return "\n".join(lines)


def snapshot_table(market_snapshot: list[dict] | None) -> str:
    if market_snapshot is None:
        # Supplemental snapshots are optional; live order books are the priced
        # source. Callers omit this section when absent, so this is a no-op guard.
        return "_No supplemental snapshot provided; live order books are the priced source._"
    if not market_snapshot:
        return "_Snapshot present but contained no markets._"
    lines = [
        "| Market | YES | NO | Spread | Top depth | Liquidity warning | Missing info |",
        "| --- | ---: | ---: | ---: | ---: | --- | --- |",
    ]
    for m in market_snapshot:
        lines.append(
            f"| {m['market_id']} | {_fmt_price(m['yes_price'])} | "
            f"{_fmt_price(m['no_price'])} | {_fmt_price(m['spread'])} | "
            f"{_fmt_num(m['orderbook_depth_top'])} | {m['liquidity_warning']} | "
            f"{'; '.join(m['missing_info'])} |"
        )
    return "\n".join(lines)


def bullet_list(items: list[str], empty: str = "_None._") -> str:
    if not items:
        return empty
    return "\n".join(f"- {item}" for item in items)


def catalyst_block(catalysts: dict, *, social_warning: str) -> str:
    credible = catalysts.get("credible_reporting_watch", [])
    noisy = catalysts.get("noisy_social_media_watch", [])
    parts = [
        "**Credible Reporting Watch**",
        bullet_list(credible, empty="_No credible-reporting entries._"),
        "",
        "**Noisy Social-Media And Rumour Watch**",
        f"> {social_warning}",
        bullet_list(noisy, empty="_No social-media entries._"),
    ]
    return "\n".join(parts)
