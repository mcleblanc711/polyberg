from __future__ import annotations

from polyberg.packet_builder.normalize_packet_state import CanonicalPacket
from polyberg.packet_builder.renderers.tables import (
    bullet_list,
    catalyst_block,
    exposure_table,
    orders_table,
    positions_table,
    registry_table,
    snapshot_table,
)


def render_claude_packet(cp: CanonicalPacket) -> str:
    portfolio = cp.portfolio
    sections: list[str] = [
        "# Polyberg Current Research Packet — Claude Source",
        (
            f"- Packet built: {cp.packet_generated_at}\n"
            "- Intended use: adversarial research review. Mode: research only, "
            "limit orders only, human review required."
        ),
    ]
    if cp.blocking_warnings:
        sections.append(_render_blocking_warnings(cp.blocking_warnings))
    sections += [
        "## Executive State",
        (
            f"- Portfolio value: {portfolio['portfolio_value']:.2f} · "
            f"Cash available: {portfolio['cash_available']:.2f} · "
            f"Positions: {len(portfolio['positions'])}\n"
            f"- Portfolio as of: {portfolio['as_of']}\n"
            f"- Freshness warnings: {len(cp.freshness_warnings)} · "
            f"Missing-info items: {len(cp.missing_info)} · "
            f"Priceable markets: {len(cp.priceable_markets)}/"
            f"{len(cp.priceable_markets) + len(cp.unpriceable_markets)} "
            "(fresh live books)\n"
            "- Marks are local marks; live order books are the priced source."
        ),
        "## Hard Gates Before Recommendations",
        _render_gates(cp),
        "## Portfolio And Exposure",
        (
            positions_table(portfolio["positions"])
            + "\n\n**Exposure by thesis bucket**"
            + (
                " _(fallback: grouped by rule_key — all thesis_buckets empty)_"
                if cp.exposure_is_fallback
                else ""
            )
            + "\n\n"
            + exposure_table(cp.exposure_summary)
            + "\n\n**Concentration warnings**\n\n"
            + bullet_list(cp.concentration_warnings, empty="_None from local values._")
        ),
        "## Open Orders",
        (
            f"As of {cp.open_orders['as_of']}.\n\n"
            "**Buys**\n\n"
            + orders_table(cp.open_orders["buys"])
            + "\n\n**Sells**\n\n"
            + orders_table(cp.open_orders["sells"])
        ),
        "## Market Rules / Registry",
        (
            registry_table(cp.market_registry)
            + (
                "\n\n**Market snapshot (supplemental)**\n\n"
                + snapshot_table(cp.market_snapshot)
                if cp.market_snapshot is not None
                else ""
            )
            + "\n\n_Stable rules live in `polymarket_rules.md` (provided separately)._"
        ),
        "## Live Order Books",
        _render_order_books(cp),
        "## Catalyst Watch",
        catalyst_block(
            cp.catalysts,
            social_warning=(
                "Catalyst-only. Not resolution evidence, not verification. Be "
                "conservative on attribution and causality."
            ),
        )
        + "\n\n**Trader notes (operator hypotheses, not facts)**\n\n"
        + bullet_list(cp.trader_notes, empty="_None._"),
        "## Compact State",
        "```json\n" + cp.compact_json() + "\n```",
    ]
    return "\n\n".join(sections).strip() + "\n"


def _render_order_books(cp: CanonicalPacket) -> str:
    if cp.order_books is None:
        return (
            "_Not fetched this session — run `polyberg fetch-books`._\n\n"
            "**No live book = no order.** Without this section, withhold all "
            "order pricing."
        )
    markdown = str(cp.order_books.get("markdown") or "").strip()
    return markdown or "_Order book artifact present but empty._"


def _render_blocking_warnings(warnings: list[str]) -> str:
    lines = [
        "## ⚠ BLOCKING WARNINGS — SESSION GATE FAILURES",
        "**These must be resolved before any analysis or recommendation can proceed.**",
        "",
    ]
    lines.extend(f"- {w}" for w in warnings)
    return "\n".join(lines)


def _render_gates(cp: CanonicalPacket) -> str:
    lines = [
        "Do not emit orders unless these are clean or explicitly acknowledged:",
        "",
        "**Freshness (local timestamps only):**",
        bullet_list(cp.freshness_warnings, empty="_None from local timestamps._"),
        "",
        "**Missing / incomplete:**",
        bullet_list(cp.missing_info, empty="_None from local files._"),
        "",
        "This is a local-timestamp/completeness check only — it does not verify "
        "live markets, news, or order books.",
    ]
    return "\n".join(lines)
