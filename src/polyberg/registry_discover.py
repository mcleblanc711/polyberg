"""Search Polymarket for events to add, annotated against the local registry.

This is the engine behind the GUI "Discover" flow and the ``search-markets`` CLI.
It runs a read-only Gamma search (keyword via ``/public-search`` or a tag browse
via ``/events``) and tags each result with how much of it is already tracked, so
the human can multi-select the genuinely-new events and bulk-add them through the
existing ``registry-add --all`` path. Nothing here writes to disk.
"""

from __future__ import annotations

from polyberg.collectors.polymarket_account import ReadOnlyHttpClient
from polyberg.collectors.polymarket_gamma import (
    normalize_event_summary,
    search_events,
)
from polyberg.models import MarketRegistry


def discover_events(
    registry: MarketRegistry,
    *,
    query: str | None = None,
    tag: str | None = None,
    limit: int = 20,
    include_closed: bool = False,
    http: ReadOnlyHttpClient | None = None,
) -> list[dict]:
    """Return annotated event summaries for a discovery search.

    Each summary gains three fields beyond the raw Gamma data:
    ``existing_market_count`` / ``new_market_count`` (brackets matched by
    condition_id against the registry) and ``in_registry`` (any bracket already
    tracked, or the event slug already present). Order follows the upstream
    search ranking (relevance for keyword, 24h volume for a browse).
    """
    raw_events = search_events(
        query=query,
        tag_slug=tag,
        limit=limit,
        include_closed=include_closed,
        http=http,
    )
    existing_cids = {m.condition_id for m in registry.markets if m.condition_id}
    existing_slugs = {m.event_slug for m in registry.markets if m.event_slug}

    results: list[dict] = []
    for event in raw_events:
        summary = normalize_event_summary(event)
        cids = summary["condition_ids"]
        existing = sum(1 for cid in cids if cid in existing_cids)
        summary["existing_market_count"] = existing
        summary["new_market_count"] = len(cids) - existing
        summary["in_registry"] = existing > 0 or (
            summary["event_slug"] is not None and summary["event_slug"] in existing_slugs
        )
        results.append(summary)
    return results
