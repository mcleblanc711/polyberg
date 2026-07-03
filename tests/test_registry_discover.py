from __future__ import annotations

import json

from polyberg.collectors.polymarket_account import ReadOnlyHttpClient
from polyberg.collectors.polymarket_gamma import (
    GAMMA_API_BASE_URL,
    normalize_event_summary,
    search_events,
)
from polyberg.models import MarketRegistry
from polyberg.registry_discover import discover_events


class FakeResponse:
    def __init__(self, payload: object) -> None:
        self.payload = payload

    def __enter__(self) -> FakeResponse:
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def read(self) -> bytes:
        return json.dumps(self.payload).encode("utf-8")


class RoutingOpener:
    """Return a different payload depending on the requested path."""

    def __init__(self, by_path: dict[str, object]) -> None:
        self.by_path = by_path
        self.urls: list[str] = []

    def __call__(self, request, timeout: float):
        self.urls.append(request.full_url)
        for needle, payload in self.by_path.items():
            if needle in request.full_url:
                return FakeResponse(payload)
        return FakeResponse(None)


def _hormuz_event() -> dict:
    return {
        "slug": "hormuz-ships-week",
        "title": "How many ships transit Hormuz this week?",
        "endDate": "2026-07-06T00:00:00Z",
        "volume": 140000.0,
        "volume24hr": 9000.0,
        "liquidity": 12000.0,
        "closed": False,
        "tags": [{"label": "Iran"}, {"label": "Geopolitics"}],
        "markets": [
            {"conditionId": "0xnew0", "question": "<25", "groupItemTitle": "<25"},
            {"conditionId": "0xexisting", "question": "25-50", "groupItemTitle": "25-50"},
        ],
    }


def _registry_with(condition_id: str) -> MarketRegistry:
    return MarketRegistry(
        markets=[
            {
                "market_id": "seed_market",
                "name": "Seed",
                "polymarket_url": "https://polymarket.com/event/seed",
                "category": "core",
                "rule_key": "k",
                "oracle_type": "UMA",
                "preferred_side": "NO",
                "resolution_date": "2026-12-31",
                "notes": "seed",
                "condition_id": condition_id,
                "event_slug": "seed",
            }
        ]
    )


def test_search_events_keyword_uses_public_search() -> None:
    opener = RoutingOpener({"/public-search": {"events": [_hormuz_event()]}})
    http = ReadOnlyHttpClient(GAMMA_API_BASE_URL, opener=opener)
    events = search_events(query="hormuz", http=http)
    assert len(events) == 1
    assert "/public-search" in opener.urls[0]
    assert "q=hormuz" in opener.urls[0]
    assert "events_status=active" in opener.urls[0]


def test_search_events_tag_browse_uses_events() -> None:
    opener = RoutingOpener({"/events": [_hormuz_event()]})
    http = ReadOnlyHttpClient(GAMMA_API_BASE_URL, opener=opener)
    events = search_events(tag_slug="iran", http=http)
    assert len(events) == 1
    url = opener.urls[0]
    assert "/events" in url
    assert "tag_slug=iran" in url
    assert "closed=false" in url and "active=true" in url


def test_normalize_event_summary_extracts_fields() -> None:
    summary = normalize_event_summary(_hormuz_event())
    assert summary["event_slug"] == "hormuz-ships-week"
    assert summary["num_markets"] == 2
    assert summary["end_date"] == "2026-07-06"
    assert summary["volume"] == 140000.0
    assert summary["condition_ids"] == ["0xnew0", "0xexisting"]
    assert summary["tags"] == ["Iran", "Geopolitics"]


def test_discover_flags_existing_brackets() -> None:
    opener = RoutingOpener({"/public-search": {"events": [_hormuz_event()]}})
    http = ReadOnlyHttpClient(GAMMA_API_BASE_URL, opener=opener)
    registry = _registry_with("0xexisting")
    results = discover_events(registry, query="hormuz", http=http)
    assert len(results) == 1
    row = results[0]
    assert row["existing_market_count"] == 1
    assert row["new_market_count"] == 1
    assert row["in_registry"] is True


def test_discover_all_new_when_no_overlap() -> None:
    opener = RoutingOpener({"/public-search": {"events": [_hormuz_event()]}})
    http = ReadOnlyHttpClient(GAMMA_API_BASE_URL, opener=opener)
    registry = _registry_with("0xunrelated")
    results = discover_events(registry, query="hormuz", http=http)
    row = results[0]
    assert row["existing_market_count"] == 0
    assert row["new_market_count"] == 2
    assert row["in_registry"] is False
