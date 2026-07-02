"""Payoff/return calculator across mutually-exclusive (neg-risk) positions.

Polymarket neg-risk events resolve *exactly one* of their bands YES and the rest
NO (e.g. "how many ships transit Hormuz this week?" → one of <25 / 25-49 / 50-74
/ 75-99 / 100+). When you hold legs across such a family the terminal P&L depends
only on which band wins. This module enumerates every resolution scenario and
reports the net P&L and return for each, plus the worst / best case and whether a
profit (or loss) is locked in regardless of outcome.

The math always models mutual exclusivity ("exactly one market in the group
resolves YES"). Whether that assumption is *trustworthy* is tracked separately:
a group is ``exclusivity_verified`` only when the registry recorded the parent
event as neg-risk. Cumulative families (e.g. "peace deal by <date>") are NOT
mutually exclusive — they surface unverified so the caller can warn or regroup.

Pure and dependency-light: no network, no disk. The CLI loads the registry and
portfolio and hands them in.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field

from polyberg.models import MarketRegistry, Portfolio

RESIDUAL_KEY = "__none__"
_EPS = 1e-9


class HedgeError(ValueError):
    pass


@dataclass(frozen=True)
class HedgeLeg:
    """One position (held) or contemplated trade (what-if) in a group."""

    market_id: str
    label: str
    side: str  # "YES" | "NO"
    price: float  # entry price per share: avg_price for held, quote for what-if
    shares: float
    source: str  # "held" | "what-if"

    @property
    def cost(self) -> float:
        return self.price * self.shares


@dataclass(frozen=True)
class ScenarioPayoff:
    """Group-wide outcome if ``key`` is the winning market (or none of them)."""

    key: str  # winning market_id, or RESIDUAL_KEY
    label: str
    feasible: bool
    leg_payoffs: list[float]  # per-leg net P&L, aligned to group.legs
    net: float
    return_pct: float | None


@dataclass(frozen=True)
class HedgeGroup:
    group_id: str  # event_slug, or "custom"
    name: str
    legs: list[HedgeLeg]
    scenarios: list[ScenarioPayoff]
    total_cost: float
    worst: ScenarioPayoff | None  # over feasible scenarios only
    best: ScenarioPayoff | None
    guaranteed_min: float | None  # worst feasible net; >0 ⇒ profit locked in
    locked_profit: bool
    locked_loss: bool
    exclusivity_verified: bool
    has_held: bool
    notes: list[str] = field(default_factory=list)


def parse_leg_spec(spec: str) -> tuple[str, str, float, float]:
    """Parse a ``market_id:SIDE:price:shares`` what-if leg spec."""
    parts = spec.split(":")
    if len(parts) != 4:
        raise HedgeError(
            f"Bad leg spec {spec!r}; expected market_id:SIDE:price:shares"
        )
    market_id, side, price_s, shares_s = (p.strip() for p in parts)
    side = side.upper()
    if side not in ("YES", "NO"):
        raise HedgeError(f"Bad side {side!r} in {spec!r}; use YES or NO")
    try:
        price = float(price_s)
        shares = float(shares_s)
    except ValueError as exc:
        raise HedgeError(f"Bad price/shares in {spec!r}: {exc}") from exc
    if not 0.0 <= price <= 1.0:
        raise HedgeError(f"Price {price} in {spec!r} must be between 0 and 1")
    if shares < 0:
        raise HedgeError(f"Shares {shares} in {spec!r} must be ≥ 0")
    return market_id, side, price, shares


def _ret(net: float, cost: float) -> float | None:
    return (net / cost * 100.0) if cost > _EPS else None


def _leg_payoffs(legs: list[HedgeLeg], winner: str | None) -> tuple[list[float], float]:
    """Per-leg net P&L if ``winner`` resolves YES and every other market NO.

    A YES leg pays $1/share only when its own market wins; a NO leg pays
    $1/share whenever a *different* market wins (or none does). ``winner`` of
    ``None`` is the residual: no tracked market wins, so every NO leg pays.
    """
    payoffs: list[float] = []
    for leg in legs:
        won = (leg.side == "YES" and leg.market_id == winner) or (
            leg.side == "NO" and leg.market_id != winner
        )
        payout = leg.shares if won else 0.0
        payoffs.append(round(payout - leg.cost, 4))
    return payoffs, round(sum(payoffs), 4)


def compute_group(
    group_id: str,
    name: str,
    legs: list[HedgeLeg],
    *,
    winners: list[tuple[str, str]],
    residual_feasible: bool,
    exclusivity_verified: bool,
    notes: list[str] | None = None,
) -> HedgeGroup:
    """Build the scenario matrix and summary for one exclusive group.

    ``winners`` is the ordered list of ``(market_id, label)`` that can each be
    the sole YES. A residual "none of these win" scenario is always appended but
    only counts toward worst/best/guaranteed when ``residual_feasible``.
    """
    total_cost = round(sum(leg.cost for leg in legs), 4)
    scenarios: list[ScenarioPayoff] = []
    for market_id, label in winners:
        payoffs, net = _leg_payoffs(legs, market_id)
        scenarios.append(
            ScenarioPayoff(market_id, label, True, payoffs, net, _ret(net, total_cost))
        )
    payoffs, net = _leg_payoffs(legs, None)
    scenarios.append(
        ScenarioPayoff(
            RESIDUAL_KEY,
            "no tracked band resolves YES",
            residual_feasible,
            payoffs,
            net,
            _ret(net, total_cost),
        )
    )

    feasible = [s for s in scenarios if s.feasible]
    worst = min(feasible, key=lambda s: s.net) if feasible else None
    best = max(feasible, key=lambda s: s.net) if feasible else None
    guaranteed_min = worst.net if worst else None
    return HedgeGroup(
        group_id=group_id,
        name=name,
        legs=legs,
        scenarios=scenarios,
        total_cost=total_cost,
        worst=worst,
        best=best,
        guaranteed_min=guaranteed_min,
        locked_profit=guaranteed_min is not None and guaranteed_min > _EPS,
        locked_loss=best is not None and best.net < -_EPS,
        exclusivity_verified=exclusivity_verified,
        has_held=any(leg.source == "held" for leg in legs),
        notes=notes or [],
    )


def _band_label(name: str, fallback: str) -> str:
    """The band portion of a registry name ("Event — band") for a compact row."""
    if name and " — " in name:
        return name.split(" — ", 1)[1].strip()
    return (name or fallback).strip()


def _family_name(member_names: list[str], event_slug: str) -> str:
    for name in member_names:
        if name and " — " in name:
            return name.split(" — ", 1)[0].strip()
    if member_names and member_names[0]:
        return member_names[0]
    return event_slug.replace("-", " ")


def build_hedge_groups(
    registry: MarketRegistry,
    portfolio: Portfolio,
    *,
    what_if_specs: list[str] | None = None,
    from_holdings: bool = True,
    event: str | None = None,
    include_singletons: bool = False,
) -> list[HedgeGroup]:
    """Assemble hedge groups from held positions and/or what-if legs.

    Held positions and what-if legs are bucketed by their registry market's
    ``event_slug`` (markets with no event_slug fall into a single ``custom``
    group). Groups with fewer than two legs are dropped unless ``include_singletons``
    (or an explicit ``event`` filter) asks otherwise. Mutual exclusivity is only
    *trusted* for families the registry recorded as neg-risk; others are flagged.
    """
    what_if_specs = list(what_if_specs or [])
    reg_by_id = {m.market_id: m for m in registry.markets}
    family: dict[str, list] = defaultdict(list)
    for market in registry.markets:
        if market.event_slug:
            family[market.event_slug].append(market)

    def group_key(market_id: str) -> str:
        market = reg_by_id.get(market_id)
        return market.event_slug if (market and market.event_slug) else "custom"

    def label_for(market_id: str) -> str:
        market = reg_by_id.get(market_id)
        if market is None:
            return market_id
        if market.band_label:
            return market.band_label
        return _band_label(market.name, market_id)

    legs_by_group: dict[str, list[HedgeLeg]] = defaultdict(list)
    if from_holdings:
        for position in portfolio.positions:
            gk = group_key(position.market_id)
            legs_by_group[gk].append(
                HedgeLeg(
                    market_id=position.market_id,
                    label=position.band_label or label_for(position.market_id),
                    side=position.side,
                    price=position.avg_price,
                    shares=position.shares,
                    source="held",
                )
            )
    for spec in what_if_specs:
        market_id, side, price, shares = parse_leg_spec(spec)
        gk = group_key(market_id)
        legs_by_group[gk].append(
            HedgeLeg(
                market_id=market_id,
                label=label_for(market_id),
                side=side,
                price=price,
                shares=shares,
                source="what-if",
            )
        )

    groups: list[HedgeGroup] = []
    for gk, legs in legs_by_group.items():
        if event is not None and gk != event:
            continue
        keep_singletons = include_singletons or event is not None
        if len(legs) < 2 and not keep_singletons:
            continue

        distinct = {leg.market_id for leg in legs}
        winners = sorted({(leg.market_id, leg.label) for leg in legs}, key=lambda t: t[1])

        if gk == "custom":
            groups.append(
                compute_group(
                    gk,
                    "Custom group",
                    legs,
                    winners=winners,
                    residual_feasible=True,
                    exclusivity_verified=False,
                    notes=[
                        "custom group (markets not in a shared event) — payoffs assume "
                        "exactly one leg's market resolves YES; confirm they are exclusive"
                    ],
                )
            )
            continue

        members = family.get(gk, [])
        verified = any(m.neg_risk is True for m in members)
        complete = len(members) > 0 and distinct >= {m.market_id for m in members}
        residual_feasible = not (verified and complete)
        notes: list[str] = []
        if not verified:
            notes.append(
                "⚠ exclusivity unverified — this event was not recorded as neg-risk; "
                "payoffs assume exactly one band resolves YES. Confirm before trusting."
            )
        if verified and not complete:
            notes.append(
                "you do not hold/track every band — the 'no tracked band' row is a real "
                "outcome (some untracked band wins)."
            )
        groups.append(
            compute_group(
                gk,
                _family_name([m.name for m in members], gk),
                legs,
                winners=winners,
                residual_feasible=residual_feasible,
                exclusivity_verified=verified,
                notes=notes,
            )
        )

    # Held-bearing groups first, then by name, for a stable, useful order.
    groups.sort(key=lambda g: (not g.has_held, g.name.lower()))
    return groups


def scenario_to_dict(scenario: ScenarioPayoff) -> dict:
    return {
        "key": scenario.key,
        "label": scenario.label,
        "feasible": scenario.feasible,
        "leg_payoffs": scenario.leg_payoffs,
        "net": scenario.net,
        "return_pct": scenario.return_pct,
    }


def group_to_dict(group: HedgeGroup) -> dict:
    return {
        "group_id": group.group_id,
        "name": group.name,
        "exclusivity_verified": group.exclusivity_verified,
        "has_held": group.has_held,
        "total_cost": group.total_cost,
        "guaranteed_min": group.guaranteed_min,
        "locked_profit": group.locked_profit,
        "locked_loss": group.locked_loss,
        "worst": scenario_to_dict(group.worst) if group.worst else None,
        "best": scenario_to_dict(group.best) if group.best else None,
        "legs": [
            {
                "market_id": leg.market_id,
                "label": leg.label,
                "side": leg.side,
                "price": leg.price,
                "shares": leg.shares,
                "cost": round(leg.cost, 4),
                "source": leg.source,
            }
            for leg in group.legs
        ],
        "scenarios": [scenario_to_dict(s) for s in group.scenarios],
        "notes": group.notes,
    }


def groups_to_dict(groups: list[HedgeGroup]) -> dict:
    return {"groups": [group_to_dict(g) for g in groups]}


def _money(value: float) -> str:
    return f"-${abs(value):,.2f}" if value < 0 else f"${value:,.2f}"


def render_markdown(groups: list[HedgeGroup]) -> str:
    """Human-readable payoff report for the CLI."""
    if not groups:
        return (
            "# Hedge Calculator\n\n_No multi-leg groups found._ Hold positions across a "
            "neg-risk family, or pass `--leg market_id:SIDE:price:shares` what-if legs "
            "(and `--event <slug>` to force a single-leg group).\n"
        )
    out: list[str] = ["# Hedge Calculator", ""]
    for group in groups:
        out.append(f"## {group.name}")
        verified = "neg-risk verified" if group.exclusivity_verified else "EXCLUSIVITY UNVERIFIED"
        out.append(f"_{group.group_id} · {verified} · capital at risk {_money(group.total_cost)}_")
        for note in group.notes:
            out.append(f"> {note}")
        out.append("")
        out.append("Legs:")
        for leg in group.legs:
            tag = "held" if leg.source == "held" else "what-if"
            out.append(
                f"- [{tag}] {leg.label} · {leg.side} {leg.shares:g} @ {leg.price:.4f} "
                f"(cost {_money(leg.cost)})"
            )
        out.append("")
        out.append("| if winner is | net P&L | return |")
        out.append("|---|---:|---:|")
        for scenario in group.scenarios:
            if not scenario.feasible:
                continue
            ret = f"{scenario.return_pct:+.1f}%" if scenario.return_pct is not None else "—"
            out.append(f"| {scenario.label} | {_money(scenario.net)} | {ret} |")
        out.append("")
        if group.worst is not None and group.best is not None:
            out.append(
                f"**worst** {_money(group.worst.net)} ({group.worst.label}) · "
                f"**best** {_money(group.best.net)} ({group.best.label})"
            )
            if group.locked_profit:
                out.append(
                    f"**✅ profit locked in: ≥ {_money(group.guaranteed_min or 0)} "
                    f"whatever resolves**"
                )
            elif group.locked_loss and group.worst.net >= -_EPS:
                out.append("no guaranteed loss — at worst you break even")
            elif group.guaranteed_min is not None and group.guaranteed_min < 0:
                out.append(f"worst-case drawdown {_money(group.guaranteed_min)} (not fully hedged)")
        out.append("")
    return "\n".join(out).rstrip() + "\n"
