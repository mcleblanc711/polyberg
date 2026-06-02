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

# --- Static instruction layer (the Claude "template") -----------------------
# Concise and adversarial by design: shorter than the GPT packet, task-directed,
# with sharp gates and an explicit critique mandate.

ADVERSARIAL_INSTRUCTIONS = """\
Your job is to **attack this book**, not cheerlead it.

- **Attack overconfidence and concentration.** Call out any thesis bucket or
  single position that dominates the portfolio and ask what breaks it.
- **Distinguish the oracle event from the world event.** What resolves the
  market is not the same as what happened in the world. Challenge any reasoning
  that conflates them.
- **Challenge whether each proposed trade beats holding cash.** If it does not
  clearly beat cash on risk-adjusted terms, say hold cash.
- **Identify stale or missing data before giving orders.** If the freshness or
  completeness gate is not clean, withhold orders and say why.
- **Do not claim live verification.** Unless you actually browsed or were handed
  live data in this session, state that you cannot verify live markets, prices,
  news, or order books.
- **Preserve limit-only order logic.** Limit orders and sell ladders only — no
  market orders, no automated execution, human review required.
- **Be conservative on attribution and causality.** Do not assert that a tweet
  or headline caused a move, or that a source is authoritative, without
  independent confirmation. Social media is catalyst-only.
"""

OUTPUT_FORMAT = """\
Respond in this order:

1. **Verdict on the gate** — is the data fresh and complete enough to act? If
   not, list what blocks action and stop short of orders.
2. **Adversarial critique** — overconfidence, concentration, oracle-vs-world
   confusion, attribution overreach.
3. **Per-trade test** — for each candidate, does it beat cash? Limit-only.
4. **Proposed limit orders / sell ladders** — only if the gate is clean, each
   tagged with the constraint it respects.
5. **What you could NOT verify** — be explicit about the live-data gap.
"""


def render_claude_packet(cp: CanonicalPacket) -> str:
    portfolio = cp.portfolio
    sections: list[str] = [
        "# Polyberg Current Research Packet — Claude Source",
        (
            f"- Packet built: {cp.packet_generated_at}\n"
            "- Intended use: adversarial research review. Mode: research only, "
            "limit orders only, human review required."
        ),
        "## Executive State",
        (
            f"- Portfolio value: {portfolio['portfolio_value']:.2f} · "
            f"Cash available: {portfolio['cash_available']:.2f} · "
            f"Positions: {len(portfolio['positions'])}\n"
            f"- Portfolio as of: {portfolio['as_of']}\n"
            f"- Freshness warnings: {len(cp.freshness_warnings)} · "
            f"Missing-info items: {len(cp.missing_info)} · "
            f"Market snapshot: {'present' if cp.market_snapshot is not None else 'MISSING'}\n"
            "- Marks are local marks, not live bid/ask/depth."
        ),
        "## Hard Gates Before Recommendations",
        _render_gates(cp),
        "## Portfolio And Exposure",
        (
            positions_table(portfolio["positions"])
            + "\n\n**Exposure by thesis bucket**\n\n"
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
            + "\n\n**Market snapshot**\n\n"
            + snapshot_table(cp.market_snapshot)
            + "\n\n_Stable rules live in `polymarket_rules.md` (provided separately)._"
        ),
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
        "## Adversarial Critique Instructions",
        ADVERSARIAL_INSTRUCTIONS.strip(),
        "## Required Output Format",
        OUTPUT_FORMAT.strip(),
        "## Compact State",
        "```json\n" + cp.compact_json() + "\n```",
    ]
    return "\n\n".join(sections).strip() + "\n"


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
