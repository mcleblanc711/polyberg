"""Registry lifecycle helpers shared by every packet builder.

A market's stored ``lifecycle`` is authoritative. These helpers derive the
*default packet active set* from it and offer a date-based suggestion, but the
suggestion is deliberately conservative: it never returns ``resolved`` or
``archived`` because a past resolution_date does not mean the oracle has printed
(PortWatch markets resolve on the next Tuesday print). Flipping a market to
resolved/archived is always a manual, human decision.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from polyberg.models import Market, MarketRegistry, Portfolio

# Lifecycles that render in the default packet (without --include-resolved).
DEFAULT_PACKET_LIFECYCLES = ("active", "resolving")


@dataclass(frozen=True)
class MarketTypeFilter:
    """Optional narrowing of a packet to a registry 'market type'.

    Each set field must match a market's value exactly; multiple set fields AND
    together. An all-None filter (``is_active`` False) matches everything — the
    default no-op. Held positions are deliberately never filtered out (see
    :func:`packet_market_ids`), so a focused packet still shows your full risk.
    """

    category: str | None = None
    thesis_bucket: str | None = None
    rule_key: str | None = None

    @property
    def is_active(self) -> bool:
        return any((self.category, self.thesis_bucket, self.rule_key))

    def matches(self, market: Market) -> bool:
        if self.category is not None and market.category != self.category:
            return False
        if self.thesis_bucket is not None and market.thesis_bucket != self.thesis_bucket:
            return False
        if self.rule_key is not None and market.rule_key != self.rule_key:
            return False
        return True


def suggest_lifecycle(resolution_date: date, today: date) -> str:
    """Suggest active vs resolving from the resolution date only.

    Returns ``active`` while the market is still open (resolution_date in the
    future or today) and ``resolving`` once its close date has passed. Never
    returns ``resolved``/``archived`` — that is a human call (see module docs).
    """
    return "active" if resolution_date >= today else "resolving"


def packet_market_ids(
    registry: MarketRegistry,
    portfolio: Portfolio,
    *,
    include_resolved: bool = False,
    type_filter: MarketTypeFilter | None = None,
) -> set[str]:
    """The active set for a packet build.

    Registry markets whose stored lifecycle is active/resolving (or any
    lifecycle when ``include_resolved``), optionally narrowed by ``type_filter``
    (category/thesis_bucket/rule_key), unioned with every currently held
    position — a market you hold is always watched, regardless of its registry
    lifecycle or the type filter, so a focused packet never hides live risk.
    """
    ids = {
        market.market_id
        for market in registry.markets
        if (include_resolved or market.lifecycle in DEFAULT_PACKET_LIFECYCLES)
        and (type_filter is None or type_filter.matches(market))
    }
    ids.update(position.market_id for position in portfolio.positions)
    return ids
