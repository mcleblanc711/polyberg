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
    delete_market_entry,
    fetch_candidate,
    get_editable_fields,
    market_display_name,
    slug_from_url,
    suggest_market_id,
    update_market_entry,
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


def _bracket_event_payload() -> list:
    """A multi-bracket event: one shared title, distinct per-bracket questions."""
    return [
        {
            "slug": "ships-event",
            "title": "How many ships transit Hormuz in June?",
            "endDate": "2026-06-30T00:00:00Z",
            "markets": [
                {
                    "question": ">25 ships",
                    "conditionId": "0xbracket0",
                    "clobTokenIds": json.dumps(["a0", "b0"]),
                    "outcomes": json.dumps(["Yes", "No"]),
                },
                {
                    "question": "26-50 ships",
                    "conditionId": "0xbracket1",
                    "clobTokenIds": json.dumps(["a1", "b1"]),
                    "outcomes": json.dumps(["Yes", "No"]),
                },
            ],
        }
    ]


def _bracket_http() -> ReadOnlyHttpClient:
    return ReadOnlyHttpClient(
        GAMMA_API_BASE_URL, opener=ListOpener(_bracket_event_payload())
    )


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


# ---------------------------------------------------------------------------
# Multi-bracket events — name/id derived from the per-bracket question
# ---------------------------------------------------------------------------


def test_single_market_uses_event_title() -> None:
    candidate = fetch_candidate("demo-event", http=_http())
    name = market_display_name(candidate, candidate["markets"][0])
    assert name == "Demo binary market?"


def test_multi_bracket_names_disambiguate() -> None:
    candidate = fetch_candidate("ships-event", http=_bracket_http())
    n0 = market_display_name(candidate, candidate["markets"][0])
    n1 = market_display_name(candidate, candidate["markets"][1])
    assert n0 == "How many ships transit Hormuz in June? — >25 ships"
    assert n1 == "How many ships transit Hormuz in June? — 26-50 ships"
    assert n0 != n1
    # Suggested ids derived from those names must differ → no duplicate-id clash.
    assert suggest_market_id(n0) != suggest_market_id(n1)


def test_build_market_brackets_distinct(tmp_path) -> None:
    path = _seed_registry(tmp_path)
    candidate = fetch_candidate("ships-event", http=_bracket_http())
    for idx, mid in ((0, "ships_gt25"), (1, "ships_26_50")):
        entry = build_market(
            candidate,
            market_id=mid,
            category="ships",
            rule_key="ships_rule",
            oracle_type="UMA",
            preferred_side="YES" if idx == 0 else "NO",
            market_index=idx,
        )
        upsert_market_entry(entry, path)
    registry = MarketRegistry(**(yaml.safe_load(path.read_text(encoding="utf-8")) or {}))
    by_id = {m.market_id: m for m in registry.markets}
    assert by_id["ships_gt25"].condition_id == "0xbracket0"
    assert by_id["ships_26_50"].condition_id == "0xbracket1"
    assert by_id["ships_gt25"].name != by_id["ships_26_50"].name


# ---------------------------------------------------------------------------
# update / delete
# ---------------------------------------------------------------------------


def _seed_two(tmp_path: Path) -> Path:
    path = _seed_registry(tmp_path)
    candidate = fetch_candidate("demo-event", http=_http())
    upsert_market_entry(
        build_market(
            candidate,
            market_id="demo_market",
            category="test",
            rule_key="demo_rule",
            oracle_type="UMA",
            preferred_side="NO",
            risk_flags=["a", "b"],
            notes="seed2",
        ),
        path,
    )
    return path


def test_update_edits_only_editable_fields(tmp_path) -> None:
    path = _seed_two(tmp_path)
    update_market_entry(
        "existing_market",
        {"category": "edited", "preferred_side": "NO", "notes": "changed"},
        path,
    )
    registry = MarketRegistry(**(yaml.safe_load(path.read_text(encoding="utf-8")) or {}))
    edited = next(m for m in registry.markets if m.market_id == "existing_market")
    assert edited.category == "edited"
    assert edited.preferred_side == "NO"
    assert edited.notes == "changed"
    # Identifiers and the other entry untouched.
    assert edited.market_id == "existing_market"
    assert any(m.market_id == "demo_market" for m in registry.markets)


def test_update_clears_risk_flags(tmp_path) -> None:
    path = _seed_two(tmp_path)
    update_market_entry("demo_market", {"risk_flags": []}, path)
    registry = MarketRegistry(**(yaml.safe_load(path.read_text(encoding="utf-8")) or {}))
    edited = next(m for m in registry.markets if m.market_id == "demo_market")
    assert edited.risk_flags == []


def test_update_rejects_locked_field(tmp_path) -> None:
    path = _seed_two(tmp_path)
    with pytest.raises(RegistryEditError):
        update_market_entry("existing_market", {"condition_id": "0xnope"}, path)


def test_update_rejects_unknown_market(tmp_path) -> None:
    path = _seed_two(tmp_path)
    with pytest.raises(RegistryEditError):
        update_market_entry("ghost", {"category": "x"}, path)


def test_update_rejects_invalid_value(tmp_path) -> None:
    path = _seed_two(tmp_path)
    with pytest.raises((RegistryEditError, ValidationError)):
        update_market_entry("existing_market", {"preferred_side": "MAYBE"}, path)


def test_get_editable_fields(tmp_path) -> None:
    path = _seed_two(tmp_path)
    fields = get_editable_fields("demo_market", path)
    assert fields["category"] == "test"
    assert fields["risk_flags"] == ["a", "b"]
    assert fields["condition_id"] == "0xabc"  # locked id surfaced for display
    assert fields["market_id"] == "demo_market"


def test_delete_removes_one_entry(tmp_path) -> None:
    path = _seed_two(tmp_path)
    delete_market_entry("existing_market", path)
    registry = MarketRegistry(**(yaml.safe_load(path.read_text(encoding="utf-8")) or {}))
    assert registry.market_ids == {"demo_market"}


def test_delete_last_entry_leaves_empty_list(tmp_path) -> None:
    path = _seed_registry(tmp_path)
    delete_market_entry("existing_market", path)
    registry = MarketRegistry(**(yaml.safe_load(path.read_text(encoding="utf-8")) or {}))
    assert registry.markets == []


def test_delete_unknown_market(tmp_path) -> None:
    path = _seed_two(tmp_path)
    with pytest.raises(RegistryEditError):
        delete_market_entry("ghost", path)
