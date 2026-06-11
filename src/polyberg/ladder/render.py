"""Render a LadderPlan as a markdown table and pipe-delimited paste block."""
from __future__ import annotations

from polyberg.ladder.diff import CancelAction, LadderPlan, PlaceAction

_PASTE_HEADER = "# === LADDER RECONCILIATION PASTE BLOCK ==="
_PASTE_PREFLIGHT_PREFIX = "PRE-FLIGHT"
_TABLE_HEADER = "| # | Action | Market | Outcome | Side | Price | Shares | Notes |"
_TABLE_SEP = "|---|--------|--------|---------|------|-------|--------|-------|"


def _fmt_price(p: float) -> str:
    return f"{p:.4f}"


def _fmt_shares(s: float) -> str:
    return f"{s:.1f}"


def _cancel_paste_line(c: CancelAction, url: str | None = None) -> str:
    parts = [
        "CANCEL",
        c.market_id,
        c.outcome,
        c.action,
        _fmt_price(c.price),
        _fmt_shares(c.shares),
        f"order_id={c.order_id}",
        url or "",
    ]
    return "|".join(parts)


def _place_paste_line(p: PlaceAction, url: str | None = None) -> str:
    parts = [
        "PLACE",
        p.market_id,
        p.outcome,
        p.action,
        _fmt_price(p.price),
        _fmt_shares(p.shares),
        "limit",
        url or "",
    ]
    return "|".join(parts)


def plan_to_dict(
    plan: LadderPlan,
    url_map: dict[str, str] | None = None,
) -> dict:
    """Serialize a LadderPlan to a JSON-ready dict for the GUI.

    Every cancel/place/keep/unmanaged action carries a stable ``idx`` (1-based,
    assigned in the same CANCEL→PLACE→KEEP→UNMANAGED order the table renders) plus
    its market url and pipe-delimited paste line. CANCEL rows expose ``order_id``
    (what the GUI passes to ``ladder cancel``); PLACE rows expose the fields the
    GUI passes to ``ladder record-manual`` once the human places them by hand.
    """
    um = url_map or {}
    idx = 0

    def _next() -> int:
        nonlocal idx
        idx += 1
        return idx

    cancels = [
        {
            "idx": _next(),
            "order_id": c.order_id,
            "market_id": c.market_id,
            "outcome": c.outcome,
            "action": c.action,
            "price": c.price,
            "shares": c.shares,
            "reason": c.reason,
            "replacement_price": c.replacement.price if c.replacement else None,
            "url": um.get(c.market_id),
            "paste": _cancel_paste_line(c, um.get(c.market_id)),
        }
        for c in plan.cancel
    ]
    places = [
        {
            "idx": _next(),
            "market_id": p.market_id,
            "outcome": p.outcome,
            "action": p.action,
            "price": p.price,
            "shares": p.shares,
            "purpose": p.purpose,
            "url": um.get(p.market_id),
            "paste": _place_paste_line(p, um.get(p.market_id)),
        }
        for p in plan.place
    ]
    keeps = [
        {
            "idx": _next(),
            "order_id": k.order_id,
            "market_id": k.market_id,
            "outcome": k.outcome,
            "action": k.action,
            "price": k.price,
            "shares": k.remaining,
            "url": um.get(k.market_id),
        }
        for k in plan.keep
    ]
    unmanaged = [
        {
            "idx": _next(),
            "order_id": u.order_id,
            "market_id": u.market_id,
            "outcome": u.outcome,
            "action": u.action,
            "price": u.price,
            "shares": u.remaining,
            "url": um.get(u.market_id),
        }
        for u in plan.unmanaged
    ]
    return {
        "preflight": list(plan.preflight),
        "warnings": list(plan.warnings),
        "summary": {
            "cancel": len(cancels),
            "place": len(places),
            "keep": len(keeps),
            "unmanaged": len(unmanaged),
            "unmapped": len(plan.unmapped),
        },
        "cancel": cancels,
        "place": places,
        "keep": keeps,
        "unmanaged": unmanaged,
        "unmapped": len(plan.unmapped),
    }


def render_plan(
    plan: LadderPlan,
    url_map: dict[str, str] | None = None,
    paste: bool = True,
) -> str:
    lines: list[str] = []

    # Warnings
    if plan.warnings:
        lines.append("## Warnings\n")
        for w in plan.warnings:
            lines.append(f"- {w}")
        lines.append("")

    # Pre-flight banner
    if plan.preflight:
        lines.append("## Pre-flight\n")
        for step in plan.preflight:
            lines.append(f"- {step}")
        lines.append("")

    # Summary
    n_cancel = len(plan.cancel)
    n_place = len(plan.place)
    n_keep = len(plan.keep)
    n_unmanaged = len(plan.unmanaged)
    n_unmapped = len(plan.unmapped)
    lines.append(
        f"**Plan:** {n_cancel} cancel · {n_place} place · {n_keep} keep · "
        f"{n_unmanaged} unmanaged · {n_unmapped} unmapped\n"
    )

    # Table sections
    row_idx = 1

    def _table_rows(rows: list[str]) -> None:
        nonlocal row_idx
        for row in rows:
            lines.append(f"| {row_idx} {row}")
            row_idx += 1

    if plan.cancel:
        lines.append("### CANCEL\n")
        lines.append(_TABLE_HEADER)
        lines.append(_TABLE_SEP)
        for c in plan.cancel:
            note = c.reason
            if c.replacement:
                note += f" → replace@{_fmt_price(c.replacement.price)}"
            _table_rows([
                f"| CANCEL | {c.market_id} | {c.outcome} | {c.action} "
                f"| {_fmt_price(c.price)} | {_fmt_shares(c.shares)} | {note} |"
            ])
        lines.append("")

    if plan.place:
        lines.append("### PLACE\n")
        lines.append(_TABLE_HEADER)
        lines.append(_TABLE_SEP)
        for p in plan.place:
            note = p.purpose or ""
            _table_rows([
                f"| PLACE | {p.market_id} | {p.outcome} | {p.action} "
                f"| {_fmt_price(p.price)} | {_fmt_shares(p.shares)} | {note} |"
            ])
        lines.append("")

    if plan.keep:
        lines.append("### KEEP\n")
        lines.append(_TABLE_HEADER)
        lines.append(_TABLE_SEP)
        for k in plan.keep:
            _table_rows([
                f"| KEEP | {k.market_id} | {k.outcome} | {k.action} "
                f"| {_fmt_price(k.price)} | {_fmt_shares(k.remaining)} | |"
            ])
        lines.append("")

    if plan.unmanaged:
        lines.append("### UNMANAGED (not in target — untouched)\n")
        lines.append(_TABLE_HEADER)
        lines.append(_TABLE_SEP)
        for u in plan.unmanaged:
            _table_rows([
                f"| UNMANAGED | {u.market_id} | {u.outcome} | {u.action} "
                f"| {_fmt_price(u.price)} | {_fmt_shares(u.remaining)} | |"
            ])
        lines.append("")

    if plan.unmapped:
        lines.append(
            f"### UNRESOLVABLE ({len(plan.unmapped)} orders not in registry — not cancelled)\n"
        )

    # Paste block
    if paste and (plan.preflight or plan.cancel or plan.place):
        lines.append(_PASTE_HEADER)
        if plan.preflight:
            for step in plan.preflight:
                lines.append(f"{_PASTE_PREFLIGHT_PREFIX}|{step}")
        for c in plan.cancel:
            url = (url_map or {}).get(c.market_id)
            lines.append(_cancel_paste_line(c, url))
        for p in plan.place:
            url = (url_map or {}).get(p.market_id)
            lines.append(_place_paste_line(p, url))
        lines.append("")

    return "\n".join(lines) + ("\n" if lines else "")
