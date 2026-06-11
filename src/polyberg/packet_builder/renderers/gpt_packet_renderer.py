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

# --- Static instruction layer (the GPT "template") --------------------------
# Verbose by design: GPT performs better when state, rules, trader notes, and
# model interpretation are explicitly separated and the freshness/completeness
# gate is stated as a hard requirement.

HOW_TO_USE = """\
This document is **current-session state**, not stable project instructions.
The stable trading rules and principles live in `polymarket_rules.md`, which is
provided separately — do not infer rules from this packet alone.

Treat the following as four distinct layers and never collapse them:

1. **Factual source data** — portfolio, open orders, registry, snapshot. These
   are locally timestamped facts, not live market data.
2. **Market rules** — provided separately in `polymarket_rules.md`.
3. **Trader interpretation notes** — the human operator's working hypotheses.
   These are opinions, not facts.
4. **Your model interpretation** — your own analysis, clearly labelled as such.

Hard rules for using this source:

- Portfolio marks are **local marks, not live bid/ask/depth**. Do not treat a
  mark as a price you can transact at.
- Social-media / tweet items are **catalyst-only**. They are never resolution
  evidence and never independent verification.
- Do **not** recommend market orders or automated execution. Limit orders and
  sell ladders only; a human reviews every action.
- Distinguish the **oracle event** (what actually resolves the market) from the
  **world event** (what happened in reality). They are not the same.
"""

RESPONSE_REQUIREMENTS = """\
Before producing any trade recommendation, you must:

1. Pass the freshness/completeness gate in Section 1. If any blocking gap
   exists, say so and **withhold trade recommendations** until it is resolved.
2. Explicitly flag every one of these if absent, before recommending anything:
   - missing market snapshot,
   - order-book depth,
   - exact market resolution rules,
   - IMF Portwatch data,
   - live news verification.
3. For each candidate trade, state whether it beats simply holding cash, and why.
4. Keep social-media items as catalyst-only; never cite them as verification.
5. Recommend **limit orders / sell ladders only** — never market orders, never
   automated execution. Assume human review is required.
6. Label each statement as one of: source-fact, market-rule, trader-note, or
   model-interpretation.
"""


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
        "## 0. How GPT Should Use This Source",
        HOW_TO_USE.strip(),
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
        registry_table(cp.market_registry),
        "## 8. Market Snapshot",
        snapshot_table(cp.market_snapshot),
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
        "## 11. Recommended GPT Response Requirements For This Packet",
        RESPONSE_REQUIREMENTS.strip(),
        "## 12. Compact Machine-Readable State",
        "```json\n" + cp.compact_json() + "\n```",
    ]
    return "\n\n".join(sections).strip() + "\n"


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
