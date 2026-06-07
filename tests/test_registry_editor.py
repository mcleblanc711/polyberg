from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pytest
import yaml
from pydantic import ValidationError

from polyberg.collectors.polymarket_account import ReadOnlyHttpClient
from polyberg.collectors.polymarket_gamma import (
    GAMMA_API_BASE_URL,
    normalize_gamma_event,
)
from polyberg.models import MarketRegistry
from polyberg.registry_editor import (
    RegistryEditError,
    build_market,
    fetch_candidate,
    slug_from_url,
    suggest_market_id,
    upsert_market_entry,
)

# ---------------------------------------------------------------------------
# Fake HTTP (mirrors test_snapshots.py)
# ---------------------------------------------------------------------------


class FakeResponse:
    def __init__(self, payload: object) -> None:
        self.payload = payload

    def __enter__(self) -> FakeResponse:
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def read(self) -> bytes:
        return json.dumps(self.payload).encode("utf-8")


class ListOpener:
    def __init__(self, payload: object) -> None:
        self.payload = payload
        self.urls: list[str] = []

    def __call__(self, request, timeout: float):
        self.urls.append(request.full_url)
        return FakeResponse(self.payload)


def _event_payload() -> list:
    return [
        {
            "slug": "demo-event",
            "title": "Demo binary market?",
            "endDate": "2026-09-30T00:00:00Z",
            "markets": [
                {
                    "question": "Demo binary market?",
                    "slug": "demo-event",
                    "conditionId": "0xabc",
                    "clobTokenIds": json.dumps(["111", "222"]),
                    "outcomes": json.dumps(["Yes", "No"]),
                    "endDate": "2026-09-30T00:00:00Z",
                }
            ],
        }
    ]


def _http() -> ReadOnlyHttpClient:
    return ReadOnlyHttpClient(GAMMA_API_BASE_URL, opener=ListOpener(_event_payload()))


# ---------------------------------------------------------------------------
# slug parsing
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "value,expected",
    [
        ("https://polymarket.com/event/some-slug", "some-slug"),
        ("https://polymarket.com/event/some-slug?tid=123", "some-slug"),
        ("https://polymarket.com/market/other-slug", "other-slug"),
        ("bare-slug", "bare-slug"),
        ("bare-slug/", "bare-slug"),
    ],
)
def test_slug_from_url(value: str, expected: str) -> None:
    assert slug_from_url(value) == expected


def test_slug_from_url_rejects_empty() -> None:
    with pytest.raises(RegistryEditError):
        slug_from_url("")


# ---------------------------------------------------------------------------
# Gamma normalization — token IDs matched by Yes/No label
# ---------------------------------------------------------------------------


def test_normalize_maps_tokens_by_label() -> None:
    # outcomes order reversed: No first. Mapping must follow the label, not index.
    event = {
        "slug": "rev",
        "title": "Reversed?",
        "endDate": "2026-01-01T00:00:00Z",
        "markets": [
            {
                "question": "Reversed?",
                "conditionId": "0xrev",
                "clobTokenIds": json.dumps(["NO_TOKEN", "YES_TOKEN"]),
                "outcomes": json.dumps(["No", "Yes"]),
            }
        ],
    }
    normalized = normalize_gamma_event(event)
    m = normalized["markets"][0]
    assert m["yes_token_id"] == "YES_TOKEN"
    assert m["no_token_id"] == "NO_TOKEN"
    assert normalized["polymarket_url"] == "https://polymarket.com/event/rev"


def test_fetch_candidate_and_build_market() -> None:
    candidate = fetch_candidate("https://polymarket.com/event/demo-event", http=_http())
    assert candidate["name"] == "Demo binary market?"
    market = build_market(
        candidate,
        market_id="demo_market",
        category="test",
        rule_key="demo_rule",
        oracle_type="UMA",
        preferred_side="NO",
    )
    assert market.condition_id == "0xabc"
    assert market.yes_token_id == "111"
    assert market.no_token_id == "222"
    assert market.resolution_date == date(2026, 9, 30)
    assert market.data_collection is not None and market.data_collection.fetch_clob


def test_build_market_rejects_bad_market_id() -> None:
    candidate = fetch_candidate("demo-event", http=_http())
    with pytest.raises(ValidationError):
        build_market(
            candidate,
            market_id="Bad-ID",  # uppercase + hyphen → invalid
            category="x",
            rule_key="x",
            oracle_type="x",
            preferred_side="NO",
        )


# ---------------------------------------------------------------------------
# upsert
# ---------------------------------------------------------------------------


def _seed_registry(tmp_path: Path) -> Path:
    path = tmp_path / "market_registry.yaml"
    path.write_text(
        yaml.safe_dump(
            {
                "markets": [
                    {
                        "market_id": "existing_market",
                        "name": "Existing",
                        "polymarket_url": "https://polymarket.com/event/existing",
                        "category": "core",
                        "rule_key": "k",
                        "oracle_type": "UMA",
                        "preferred_side": "YES",
                        "resolution_date": "2026-12-31",
                        "notes": "seed",
                    }
                ]
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    return path


def test_upsert_appends_and_reparses(tmp_path) -> None:
    path = _seed_registry(tmp_path)
    candidate = fetch_candidate("demo-event", http=_http())
    entry = build_market(
        candidate,
        market_id="demo_market",
        category="test",
        rule_key="demo_rule",
        oracle_type="UMA",
        preferred_side="NO",
        notes="added via test",
    )
    upsert_market_entry(entry, path)

    registry = MarketRegistry(**(yaml.safe_load(path.read_text(encoding="utf-8")) or {}))
    ids = registry.market_ids
    assert ids == {"existing_market", "demo_market"}
    added = next(m for m in registry.markets if m.market_id == "demo_market")
    assert added.yes_token_id == "111"
    assert added.no_token_id == "222"
    # Existing entry left intact.
    assert any(m.market_id == "existing_market" for m in registry.markets)


def test_upsert_rejects_duplicate(tmp_path) -> None:
    path = _seed_registry(tmp_path)
    candidate = fetch_candidate("demo-event", http=_http())
    entry = build_market(
        candidate,
        market_id="existing_market",  # collide
        category="test",
        rule_key="demo_rule",
        oracle_type="UMA",
        preferred_side="NO",
    )
    with pytest.raises(RegistryEditError):
        upsert_market_entry(entry, path)


def test_suggest_market_id() -> None:
    assert (
        suggest_market_id("Strait of Hormuz: normal by June?")
        == "strait_of_hormuz_normal_by_june"
    )
    assert suggest_market_id("") == "new_market"
