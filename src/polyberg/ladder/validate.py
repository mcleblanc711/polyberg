"""Hard validators and warnings for ladder targets.

Call validate_targets() BEFORE diff. All hard errors are collected and raised
together as LadderValidationError so the user sees every problem at once.
"""
from __future__ import annotations

from decimal import Decimal

from polyberg.ladder.models import TargetLadders
from polyberg.models import MarketRegistry

SELL_CAP = 0.96


class LadderValidationError(Exception):
    def __init__(self, messages: list[str]) -> None:
        self.messages = list(messages)
        super().__init__("\n".join(messages))


def validate_targets(
    targets: TargetLadders,
    registry: MarketRegistry,
    cash: Decimal,
    cash_is_stale: bool = False,
) -> list[str]:
    """Validate ladder targets; return warnings list.

    Hard failures raise LadderValidationError (exit code 2).
    Stale-cash warning fires when cash_is_stale=True (came from portfolio yaml,
    not a live /balance-allowance fetch).
    """
    errors: list[str] = []
    warnings: list[str] = []
    registry_by_id = {m.market_id: m for m in registry.markets}

    # HARD: [sell-cap] SELL rung price > 0.96
    for ladder in targets.ladders:
        if ladder.action == "SELL":
            for rung in ladder.rungs:
                if rung.price > SELL_CAP:
                    errors.append(
                        f"[sell-cap] SELL rung price {rung.price} > {SELL_CAP} "
                        f"in {ladder.market_id}/{ladder.outcome} — "
                        "lower the price or use 0.96 exactly"
                    )

    if errors:
        raise LadderValidationError(errors)

    # WARN: [cash-collision] BUY worst-case cost > available cash.
    # Not a hard fail: the only downside of overcommitting is the exchange
    # cancelling unfunded orders if everything fills.
    total_buy_cost = Decimal(0)
    for ladder in targets.ladders:
        if ladder.action == "BUY":
            for rung in ladder.rungs:
                total_buy_cost += Decimal(str(rung.price)) * Decimal(str(rung.shares))
    if total_buy_cost > cash:
        overage = total_buy_cost - cash
        warnings.append(
            f"[cash-collision] BUY rungs worst-case cost ${total_buy_cost:.2f} "
            f"> available cash ${cash:.2f} (overage: ${overage:.2f}) — "
            "exchange may cancel unfunded orders if all rungs fill"
        )

    # WARN: [dirty-oracle] BUY ladder on unverified or media-fallback market
    for ladder in targets.ladders:
        if ladder.action == "BUY":
            market = registry_by_id.get(ladder.market_id)
            if market is not None:
                if not market.band_verified:
                    warnings.append(
                        f"[dirty-oracle] BUY ladder on {ladder.market_id}: "
                        "band_verified=false — fill-inversion risk on unverified bands"
                    )
                elif market.rule_risk and market.rule_risk.media_fallback:
                    warnings.append(
                        f"[dirty-oracle] BUY ladder on {ladder.market_id}: "
                        "rule_risk.media_fallback=true — fill-inversion risk"
                    )

    # WARN: [stale-cash] cash from portfolio yaml, not live fetch
    if cash_is_stale:
        warnings.append(
            "[stale-cash] cash_available came from portfolio_current.yaml, "
            "not a live /balance-allowance fetch — may be outdated"
        )

    return warnings
