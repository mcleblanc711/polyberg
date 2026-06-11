"""Pure diff: TargetLadders + live orders -> LadderPlan.

No I/O, no side effects. All lists in LadderPlan are sorted deterministically
by (market_id, outcome, action, price) so plan output is stable across runs.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from polyberg.ladder.live_orders import LiveRung, UnmappedOrder
from polyberg.ladder.models import Ladder, MatchingConfig, Rung, TargetLadders
from polyberg.models import Side

PREFLIGHT_DESCRIPTION = (
    "GET /balance-allowance/update — required after any position close before new orders accepted"
)


@dataclass
class PlaceAction:
    market_id: str
    outcome: Side
    action: str
    price: float
    shares: float
    purpose: str | None = None


@dataclass
class CancelAction:
    order_id: str
    market_id: str
    outcome: Side
    action: str
    price: float
    shares: float  # remaining shares being cancelled
    reason: str  # "shares_mismatch" | "not_in_target"
    replacement: PlaceAction | None = None


@dataclass
class KeepAction:
    order_id: str
    market_id: str
    outcome: Side
    action: str
    price: float
    remaining: float


@dataclass
class LadderPlan:
    preflight: list[str] = field(default_factory=list)
    cancel: list[CancelAction] = field(default_factory=list)
    place: list[PlaceAction] = field(default_factory=list)
    keep: list[KeepAction] = field(default_factory=list)
    unmanaged: list[LiveRung] = field(default_factory=list)
    unmapped: list[UnmappedOrder] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def _sort_key_cancel(a: CancelAction) -> tuple[str, str, str, float]:
    return (a.market_id, a.outcome, a.action, a.price)


def _sort_key_place(a: PlaceAction) -> tuple[str, str, str, float]:
    return (a.market_id, a.outcome, a.action, a.price)


def _sort_key_keep(a: KeepAction) -> tuple[str, str, str, float]:
    return (a.market_id, a.outcome, a.action, a.price)


def _sort_key_live(a: LiveRung) -> tuple[str, str, str, float]:
    return (a.market_id, a.outcome, a.action, a.price)


def _greedy_match(
    target_rungs: list[Rung],
    live_rungs: list[LiveRung],
    price_tolerance: float,
) -> tuple[list[tuple[Rung, LiveRung]], list[Rung], list[LiveRung]]:
    """Greedy nearest-price one-to-one matching within price_tolerance.

    Returns (matched_pairs, unmatched_targets, unmatched_live).
    """
    available = list(live_rungs)
    matched: list[tuple[Rung, LiveRung]] = []
    unmatched_targets: list[Rung] = []

    for target in sorted(target_rungs, key=lambda r: r.price):
        best_live: LiveRung | None = None
        best_diff = float("inf")
        for live in available:
            diff = abs(live.price - target.price)
            if diff <= price_tolerance and diff < best_diff:
                best_live = live
                best_diff = diff
        if best_live is not None:
            matched.append((target, best_live))
            available.remove(best_live)
        else:
            unmatched_targets.append(target)

    return matched, unmatched_targets, available


def _purpose(ladder: Ladder) -> str | None:
    return ladder.tags.purpose if ladder.tags else None


def diff_ladders(
    targets: TargetLadders,
    live_rungs: list[LiveRung],
    unmapped: list[UnmappedOrder],
    matching: MatchingConfig | None = None,
    manage_all: bool = False,
) -> LadderPlan:
    """Produce a LadderPlan from declared targets and live open orders."""
    m = matching if matching is not None else targets.matching
    pt = m.price_tolerance
    st = m.shares_tolerance

    managed_keys: set[tuple[str, str, str]] = {
        (ladder.market_id, ladder.outcome, ladder.action)
        for ladder in targets.ladders
    }

    live_by_key: dict[tuple[str, str, str], list[LiveRung]] = {}
    unmanaged_rungs: list[LiveRung] = []
    for live in live_rungs:
        key = (live.market_id, live.outcome, live.action)
        if key in managed_keys:
            live_by_key.setdefault(key, []).append(live)
        else:
            unmanaged_rungs.append(live)

    cancels: list[CancelAction] = []
    places: list[PlaceAction] = []
    keeps: list[KeepAction] = []

    for ladder in targets.ladders:
        key = (ladder.market_id, ladder.outcome, ladder.action)
        live_for_key = live_by_key.get(key, [])

        matched, unmatched_targets, unmatched_live = _greedy_match(
            ladder.rungs, live_for_key, pt
        )

        for target_rung, live_rung in matched:
            if abs(live_rung.remaining - target_rung.shares) <= st:
                keeps.append(
                    KeepAction(
                        order_id=live_rung.order_id,
                        market_id=ladder.market_id,
                        outcome=ladder.outcome,
                        action=ladder.action,
                        price=live_rung.price,
                        remaining=live_rung.remaining,
                    )
                )
            else:
                replacement = PlaceAction(
                    market_id=ladder.market_id,
                    outcome=ladder.outcome,
                    action=ladder.action,
                    price=target_rung.price,
                    shares=target_rung.shares,
                    purpose=_purpose(ladder),
                )
                cancels.append(
                    CancelAction(
                        order_id=live_rung.order_id,
                        market_id=ladder.market_id,
                        outcome=ladder.outcome,
                        action=ladder.action,
                        price=live_rung.price,
                        shares=live_rung.remaining,
                        reason="shares_mismatch",
                        replacement=replacement,
                    )
                )
                places.append(replacement)

        for target_rung in unmatched_targets:
            places.append(
                PlaceAction(
                    market_id=ladder.market_id,
                    outcome=ladder.outcome,
                    action=ladder.action,
                    price=target_rung.price,
                    shares=target_rung.shares,
                    purpose=_purpose(ladder),
                )
            )

        for live_rung in unmatched_live:
            cancels.append(
                CancelAction(
                    order_id=live_rung.order_id,
                    market_id=ladder.market_id,
                    outcome=ladder.outcome,
                    action=ladder.action,
                    price=live_rung.price,
                    shares=live_rung.remaining,
                    reason="not_in_target",
                )
            )

    if manage_all:
        for live_rung in unmanaged_rungs:
            cancels.append(
                CancelAction(
                    order_id=live_rung.order_id,
                    market_id=live_rung.market_id,
                    outcome=live_rung.outcome,
                    action=live_rung.action,
                    price=live_rung.price,
                    shares=live_rung.remaining,
                    reason="not_in_target",
                )
            )
        unmanaged_rungs = []

    preflight: list[str] = []
    if places:
        preflight.append(PREFLIGHT_DESCRIPTION)

    return LadderPlan(
        preflight=preflight,
        cancel=sorted(cancels, key=_sort_key_cancel),
        place=sorted(places, key=_sort_key_place),
        keep=sorted(keeps, key=_sort_key_keep),
        unmanaged=sorted(unmanaged_rungs, key=_sort_key_live),
        unmapped=list(unmapped),
        warnings=[],
    )
