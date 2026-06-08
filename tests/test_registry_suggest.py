from __future__ import annotations

import yaml

from polyberg.collectors.polymarket_gamma import normalize_gamma_event
from polyberg.models import MarketRegistry
from polyberg.registry_suggest import (
    INHERIT_THRESHOLD,
    find_nearest,
    suggest_for_market,
)

# ---------------------------------------------------------------------------
# A small seeded registry resembling the real Hormuz families.
# ---------------------------------------------------------------------------


def _registry() -> MarketRegistry:
    return MarketRegistry(
        **yaml.safe_load(
            """
markets:
  - market_id: hormuz_normal_jul31
    name: Hormuz normal by July 31 2026
    polymarket_url: https://polymarket.com/event/strait-of-hormuz-traffic-returns-to-normal-by-july-31
    category: core_hormuz
    thesis_bucket: "Iran conflict"
    rule_key: hormuz_portwatch_7dma
    oracle_type: IMF Portwatch data
    preferred_side: "NO"
    risk_flags:
      - pure data oracle
      - low media ambiguity
    event_slug: strait-of-hormuz-traffic-returns-to-normal-by-july-31
    resolution_date: 2026-07-31
    notes: Resolves on IMF Portwatch 7-day moving average.
    rule_risk:
      oracle_type: pure_data
      ambiguity: low
      media_fallback: false
      official_statement_required: false
      dispute_risk: low
  - market_id: hormuz_transit_50_74_jun1_7
    name: 50-74 ships transit Strait of Hormuz between June 1-7 2026
    polymarket_url: https://polymarket.com/event/how-many-ships-transit-the-strait-of-hormuz-week-of-june-1
    category: hormuz_transit_count
    thesis_bucket: "Iran conflict"
    rule_key: hormuz_portwatch_weekly_count_band
    oracle_type: IMF Portwatch data (ship-transit count)
    preferred_side: "YES"
    risk_flags:
      - pure data oracle
      - bucketed (negative-risk) market — exactly one band resolves YES
    event_slug: how-many-ships-transit-the-strait-of-hormuz-week-of-june-1
    resolution_date: 2026-06-07
    notes: One bucket of a negative-risk weekly ship-count market.
    rule_risk:
      oracle_type: pure_data
      ambiguity: low
      media_fallback: false
      official_statement_required: false
      dispute_risk: low
  - market_id: france_warships_hormuz_may31
    name: France sends warships through Strait of Hormuz by May 31 2026
    polymarket_url: https://polymarket.com/event/will-france-send-warships-through-the-strait-of-hormuz-by-may-31-2026
    category: warships_hormuz
    thesis_bucket: "Iran conflict"
    rule_key: warships_hormuz_transit
    oracle_type: National government / military announcement
    preferred_side: "NO"
    risk_flags:
      - low base rate
    event_slug: will-france-send-warships-through-the-strait-of-hormuz-by-may-31-2026
    resolution_date: 2026-05-31
    notes: warships transit rules.
"""
        )
    )


def _ships_band_event() -> dict:
    """A fresh week's ship-count band event — a new bracket of the count family."""
    return normalize_gamma_event(
        {
            "slug": "how-many-ships-transit-the-strait-of-hormuz-week-of-july-6",
            "title": "How many ships transit the Strait of Hormuz week of July 6?",
            "endDate": "2026-07-12T00:00:00Z",
            "resolutionSource": "https://portwatch.imf.org/pages/x",
            "tags": [{"label": "Hormuz"}, {"label": "Iran"}],
            "markets": [
                {
                    "question": "Will 50-74 ships transit the Strait of Hormuz?",
                    "groupItemTitle": "50-74",
                    "conditionId": "0xband0",
                    "clobTokenIds": '["a0","b0"]',
                    "outcomes": '["Yes","No"]',
                    "description": (
                        "This market will resolve according to the finalized total "
                        "number of transit calls that IMF Portwatch reports for the "
                        "Strait of Hormuz."
                    ),
                }
            ],
        }
    )


# ---------------------------------------------------------------------------
# Nearest-neighbour matching
# ---------------------------------------------------------------------------


def test_find_nearest_exact_slug_scores_one() -> None:
    reg = _registry()
    event = normalize_gamma_event(
        {
            "slug": "strait-of-hormuz-traffic-returns-to-normal-by-july-31",
            "title": "Hormuz normal by July 31 2026",
            "endDate": "2026-07-31T00:00:00Z",
            "markets": [
                {
                    "question": "Hormuz normal?",
                    "conditionId": "0xz",
                    "clobTokenIds": '["1","2"]',
                    "outcomes": '["Yes","No"]',
                }
            ],
        }
    )
    match, score = find_nearest(event, event["markets"][0], reg)
    assert match is not None and match.market_id == "hormuz_normal_jul31"
    assert score == 1.0


def test_find_nearest_keyword_overlap_picks_family() -> None:
    reg = _registry()
    event = _ships_band_event()
    match, score = find_nearest(event, event["markets"][0], reg)
    # A new ship-count week matches the ship-count family, not warships/normal.
    assert match is not None and match.market_id == "hormuz_transit_50_74_jun1_7"
    assert score >= INHERIT_THRESHOLD


def test_find_nearest_no_overlap_returns_none() -> None:
    reg = _registry()
    event = normalize_gamma_event(
        {
            "slug": "will-the-fed-cut-rates-in-september",
            "title": "Fed rate cut in September?",
            "endDate": "2026-09-30T00:00:00Z",
            "markets": [
                {
                    "question": "Fed cut?",
                    "conditionId": "0xfed",
                    "clobTokenIds": '["1","2"]',
                    "outcomes": '["Yes","No"]',
                }
            ],
        }
    )
    match, score = find_nearest(event, event["markets"][0], reg)
    assert score < INHERIT_THRESHOLD


# ---------------------------------------------------------------------------
# Inheritance path
# ---------------------------------------------------------------------------


def test_band_inherits_family_but_keeps_safe_side() -> None:
    reg = _registry()
    event = _ships_band_event()
    sug = suggest_for_market(event, event["markets"][0], reg)
    # Inherited the ship-count family's curated judgment fields...
    assert sug["oracle_type"] == "IMF Portwatch data (ship-transit count)"
    assert sug["rule_key"] == "hormuz_portwatch_weekly_count_band"
    assert sug["thesis_bucket"] == "Iran conflict"
    assert sug["sources"]["oracle_type"] == "inherited"
    assert sug["matched_market_id"] == "hormuz_transit_50_74_jun1_7"
    # ...but a band never inherits a sibling's YES side.
    assert sug["preferred_side"] == "NO"
    assert sug["sources"]["preferred_side"] == "default"
    # Notes come from the resolution description.
    assert "Portwatch" in sug["notes"]


# ---------------------------------------------------------------------------
# Rules fallback path (no matching family)
# ---------------------------------------------------------------------------


def test_rules_fallback_portwatch_pure_data() -> None:
    reg = MarketRegistry(markets=[])  # empty → no neighbour, force fallback
    event = _ships_band_event()
    sug = suggest_for_market(event, event["markets"][0], reg)
    assert sug["oracle_type"] == "IMF Portwatch data"
    assert "pure data oracle" in sug["risk_flags"]
    assert sug["rule_risk"]["oracle_type"] == "pure_data"
    assert sug["sources"]["oracle_type"] == "rules"
    # Band-specific risk flag is mined from the bracket label.
    assert any("bucketed" in f for f in sug["risk_flags"])
    # Tag-derived category/thesis.
    assert sug["category"] == "core_hormuz"
    assert sug["thesis_bucket"] == "Iran conflict"


def test_rules_fallback_announcement_oracle() -> None:
    reg = MarketRegistry(markets=[])
    event = normalize_gamma_event(
        {
            "slug": "will-trump-announce-x-by-may-31",
            "title": "Will Trump announce X by May 31?",
            "endDate": "2026-05-31T00:00:00Z",
            "tags": [{"label": "Politics"}],
            "markets": [
                {
                    "question": "Will Trump announce X?",
                    "conditionId": "0xann",
                    "clobTokenIds": '["1","2"]',
                    "outcomes": '["Yes","No"]',
                    "description": "Resolves YES if Trump makes an official announcement.",
                }
            ],
        }
    )
    sug = suggest_for_market(event, event["markets"][0], reg)
    assert sug["rule_risk"]["oracle_type"] == "official_statement_required"
    assert "media fallback may matter" in sug["risk_flags"]
    assert "Trump social post can qualify" in sug["risk_flags"]
    assert sug["preferred_side"] == "NO"


# ---------------------------------------------------------------------------
# Gamma normalization carries the new fields
# ---------------------------------------------------------------------------


def test_normalize_carries_description_tags_group_item() -> None:
    event = _ships_band_event()
    assert event["resolution_source"] == "https://portwatch.imf.org/pages/x"
    assert event["tags"] == ["Hormuz", "Iran"]
    m = event["markets"][0]
    assert m["group_item_title"] == "50-74"
    assert "Portwatch" in (m["description"] or "")
