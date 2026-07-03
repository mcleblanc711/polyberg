from __future__ import annotations

import yaml

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


def _yaml_block(data: dict) -> str:
    return yaml.safe_dump(data, sort_keys=False, default_flow_style=False).strip()


def render_gpt_packet(cp: CanonicalPacket) -> str:
    metadata = {
        "packet_generated_at": cp.packet_generated_at,
        "source_timestamps": cp.source_timestamps,
        "freshness_warning_count": len(cp.freshness_warnings),
        "missing_info_count": len(cp.missing_info),
    }

    portfolio = cp.portfolio
    sections: list[str] = [
        "# Polyberg Current Research Packet — GPT Source",
        (
            f"- Packet built: {cp.packet_generated_at}\n"
            "- Intended use: paste into a GPT research/risk session alongside "
            "`polymarket_rules.md`.\n"
            "- Mode: research only. Human review required before any action."
        ),
    ]
    if cp.blocking_warnings:
        sections.append(_render_blocking_warnings(cp.blocking_warnings))
    sections += [
        "## 1. Freshness And Completeness Warnings",
        _render_gate(cp),
        "## 2. Packet Metadata",
        "```yaml\n" + _yaml_block(metadata) + "\n```",
        "## 3. Session Operating Constraints",
        "```yaml\n" + _yaml_block(cp.constraints) + "\n```",
        "## 4. Current Portfolio State",
        (
            f"- As of: {portfolio['as_of']}\n"
            f"- Portfolio value: {portfolio['portfolio_value']:.2f}\n"
            f"- Cash available: {portfolio['cash_available']:.2f}\n\n"
            "_Marks below are local marks, not live bid/ask/depth._\n\n"
            + positions_table(portfolio["positions"])
            + "\n\n**Exposure Summary By Thesis Bucket**"
            + (
                " _(fallback: grouped by rule_key — all thesis_buckets empty)_"
                if cp.exposure_is_fallback
                else ""
            )
            + "\n\n"
            + exposure_table(cp.exposure_summary)
            + "\n\n"
            + "**Concentration warnings**\n\n"
            + bullet_list(
                cp.concentration_warnings,
                empty="_None from local portfolio values._",
            )
        ),
        "## 5. Open Orders",
        (
            f"- As of: {cp.open_orders['as_of']}\n\n"
            "**Buy Orders**\n\n"
            + orders_table(cp.open_orders["buys"])
            + "\n\n**Sell Orders**\n\n"
            + orders_table(cp.open_orders["sells"])
        ),
        "## 6. Active Thesis Notes",
        bullet_list(cp.raw_notes, empty="_No active thesis notes._"),
        "## 7. Market Registry Summary",
        (
            registry_table(cp.market_registry)
            + (
                "\n\n**Market snapshot (supplemental)**\n\n"
                + snapshot_table(cp.market_snapshot)
                if cp.market_snapshot is not None
                else ""
            )
        ),
        "## 8. Live Order Books",
        _render_order_books(cp),
        "## 9. Catalyst Watch",
        catalyst_block(
            cp.catalysts,
            social_warning=(
                "Social-media items are catalyst-only. They are NOT resolution "
                "evidence and NOT live verification."
            ),
        ),
        "## 10. Trader Interpretation Notes",
        (
            bullet_list(cp.trader_notes, empty="_No trader interpretation notes._")
            + "\n\n_These are the human operator's hypotheses — opinions, not facts._"
        ),
        "## 11. Compact Machine-Readable State",
        "```json\n" + cp.compact_json() + "\n```",
    ]
    return "\n\n".join(sections).strip() + "\n"


def _render_order_books(cp: CanonicalPacket) -> str:
    if cp.order_books is None:
        return (
            "_Not fetched this session — run `polyberg fetch-books`._\n\n"
            "**No live book = no order.** Without this section, withhold all "
            "order pricing and flag the gap in your gate verdict."
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


def _render_gate(cp: CanonicalPacket) -> str:
    lines = [
        "**Hard gate: do not produce trade recommendations until these are "
        "resolved or explicitly acknowledged.**",
        "",
        "**Freshness warnings (local timestamps only):**",
        bullet_list(cp.freshness_warnings, empty="_None from local timestamps._"),
        "",
        "**Missing / incomplete information:**",
        bullet_list(cp.missing_info, empty="_None from local files._"),
        "",
        "This gate checks local file timestamps and completeness only. It does "
        "**not** verify live markets, news, or order books. Data here is locally "
        "timestamped, not live.",
    ]
    return "\n".join(lines)
