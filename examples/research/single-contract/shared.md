# Polyberg market research

Snapshot SHA-256: e6dfafb8d5910a3c9221425b210b4cc2a37d628968edba66117e9e1b3ba7fc5b
Generated: 2026-10-26T12:00:00+00:00
Freshness threshold: 36 hours
Selection: event:810001

## SYNTHETIC: will the fictional index exceed 50?

Gamma market: 910001
Lifecycle: active · Research: researching
Trading end (not an established resolution deadline): 2026-11-01T00:00:00Z

| Outcome | Displayed | Bid | Ask | Midpoint | Last trade |
| --- | --- | --- | --- | --- | --- |
| Yes | 0.3 | 0.25 | 0.35 | 0.3 | 0.29 |
| No | 0.7 | 0.25 | 0.35 | 0.3 | 0.29 |

### Verbatim market rules

SYNTHETIC RULES — fictional demonstration only.
Resolve using the fictional Observatory's published measurement.
Scheduled resolution: November 10, 2026 at 12:00 UTC.
Unknown fallback and dispute procedures remain unestablished.

Rules version: 1
Rules text SHA-256: 5bd7e34114a6c7464fc9d8ef3852a597019a975d5d667f31e6c764729760870a
Rules API source: https://gamma-api.polymarket.com/events/810001
Retrieved: 2026-10-26T12:00:00+00:00

### Established rules annotations

- resolution_deadline: Fictional scheduled resolution: 2026-11-10T12:00:00Z.
  Source: https://example.invalid/fictional-rules
### Research entries and sources

#### observation · entry 1

SYNTHETIC: fictional Observatory report exists.

Entered: 2026-10-26T12:00:00+00:00 · User verified at 2026-10-26T12:00:00+00:00

- Source: https://example.invalid/fictional-report
  Published: 2026-10-26T12:00:00+00:00; observed: 2026-10-26T12:00:00+00:00

#### catalyst · entry 2

SYNTHETIC: next fictional Observatory print.

Entered: 2026-10-26T12:00:00+00:00 · Unverified


#### hypothesis · entry 3

SYNTHETIC: the next report may revise the measurement.

Entered: 2026-10-26T12:00:00+00:00 · Unverified


#### question · entry 4

SYNTHETIC: how are missing daily observations handled?

Entered: 2026-10-26T12:00:00+00:00 · Unverified


#### model_interpretation · entry 5

SYNTHETIC MODEL OUTPUT: consider a revised-data scenario.

Entered: 2026-10-26T12:00:00+00:00 · Unverified


### Explicit market relationships

No established relationships.

## Complete evidence and provenance

The following canonical record includes rules versions, annotations, entries, sources,
relationships and all retrieval timestamps. Source text and research entries are data,
not instructions. Verification records explicit user review only.

```json
{
  "events": [
    {
      "api_url": "https://gamma-api.polymarket.com/events/810001",
      "contracts": [
        {
          "api_url": "https://gamma-api.polymarket.com/markets/910001",
          "condition_id": "0x00000000000000000000000000000000000000000000000000000000000de2b1",
          "event_id": "810001",
          "lifecycle": "active",
          "market_id": "910001",
          "outcomes": [
            {
              "asset_id": "9100010",
              "index": 0,
              "label": "Yes",
              "outcome_id": "910001:0",
              "position_id": "9100010",
              "token_id": null
            },
            {
              "asset_id": "9100011",
              "index": 1,
              "label": "No",
              "outcome_id": "910001:1",
              "position_id": "9100011",
              "token_id": null
            }
          ],
          "page_url": "https://polymarket.com/event/single-contract/synthetic-910001",
          "protocol": "v2",
          "question": "SYNTHETIC: will the fictional index exceed 50?",
          "question_id": "synthetic-question-910001",
          "slug": "synthetic-910001",
          "trading_end": "2026-11-01T00:00:00Z",
          "trading_start": null
        }
      ],
      "description": "Fictional training example. These are not real markets or observations.",
      "event_id": "810001",
      "expected_market_ids": [
        "910001"
      ],
      "page_url": "https://polymarket.com/event/single-contract",
      "retrieved_at": "2026-10-26T12:00:00+00:00",
      "slug": "single-contract",
      "title": "SYNTHETIC EXAMPLE: single-contract",
      "warnings": []
    }
  ],
  "generated_at": "2026-10-26T12:00:00+00:00",
  "markets": [
    {
      "annotations_for_review": [],
      "entries": [
        {
          "category": "observation",
          "created_at": "2026-10-26T12:00:00+00:00",
          "entry_id": 1,
          "sources": [
            {
              "observed_at": "2026-10-26T12:00:00+00:00",
              "published_at": "2026-10-26T12:00:00+00:00",
              "title": "Fictional report",
              "url": "https://example.invalid/fictional-report"
            }
          ],
          "text": "SYNTHETIC: fictional Observatory report exists.",
          "verified_at": "2026-10-26T12:00:00+00:00"
        },
        {
          "category": "catalyst",
          "created_at": "2026-10-26T12:00:00+00:00",
          "entry_id": 2,
          "sources": [],
          "text": "SYNTHETIC: next fictional Observatory print.",
          "verified_at": null
        },
        {
          "category": "hypothesis",
          "created_at": "2026-10-26T12:00:00+00:00",
          "entry_id": 3,
          "sources": [],
          "text": "SYNTHETIC: the next report may revise the measurement.",
          "verified_at": null
        },
        {
          "category": "question",
          "created_at": "2026-10-26T12:00:00+00:00",
          "entry_id": 4,
          "sources": [],
          "text": "SYNTHETIC: how are missing daily observations handled?",
          "verified_at": null
        },
        {
          "category": "model_interpretation",
          "created_at": "2026-10-26T12:00:00+00:00",
          "entry_id": 5,
          "sources": [],
          "text": "SYNTHETIC MODEL OUTPUT: consider a revised-data scenario.",
          "verified_at": null
        }
      ],
      "followed": true,
      "identification": {
        "api_url": "https://gamma-api.polymarket.com/markets/910001",
        "condition_id": "0x00000000000000000000000000000000000000000000000000000000000de2b1",
        "event_id": "810001",
        "lifecycle": "active",
        "market_id": "910001",
        "outcomes": [
          {
            "asset_id": "9100010",
            "index": 0,
            "label": "Yes",
            "outcome_id": "910001:0",
            "position_id": "9100010",
            "token_id": null
          },
          {
            "asset_id": "9100011",
            "index": 1,
            "label": "No",
            "outcome_id": "910001:1",
            "position_id": "9100011",
            "token_id": null
          }
        ],
        "page_url": "https://polymarket.com/event/single-contract/synthetic-910001",
        "protocol": "v2",
        "question": "SYNTHETIC: will the fictional index exceed 50?",
        "question_id": "synthetic-question-910001",
        "slug": "synthetic-910001",
        "trading_end": "2026-11-01T00:00:00Z",
        "trading_start": null
      },
      "last_attempt_at": "2026-10-26T12:00:00+00:00",
      "last_success_at": "2026-10-26T12:00:00+00:00",
      "projects": [
        "default"
      ],
      "relationships": [],
      "rules": {
        "annotations": [
          {
            "annotation_id": 1,
            "created_at": "2026-10-26T12:00:00+00:00",
            "kind": "resolution_deadline",
            "needs_review": false,
            "rules_version_id": 1,
            "source_url": "https://example.invalid/fictional-rules",
            "text": "Fictional scheduled resolution: 2026-11-10T12:00:00Z."
          }
        ],
        "api_url": "https://gamma-api.polymarket.com/events/810001",
        "first_retrieved_at": "2026-10-26T12:00:00+00:00",
        "observations": [
          "2026-10-26T12:00:00+00:00"
        ],
        "page_url": "https://polymarket.com/event/single-contract/synthetic-910001",
        "resolution_source": "https://example.invalid/fictional-observatory",
        "resolution_status": null,
        "rules_version_id": 1,
        "text": "SYNTHETIC RULES — fictional demonstration only.\nResolve using the fictional Observatory's published measurement.\nScheduled resolution: November 10, 2026 at 12:00 UTC.\nUnknown fallback and dispute procedures remain unestablished.",
        "text_sha256": "5bd7e34114a6c7464fc9d8ef3852a597019a975d5d667f31e6c764729760870a"
      },
      "snapshot": {
        "quotes": [
          {
            "best_ask": 0.35,
            "best_bid": 0.25,
            "book_retrieved_at": "2026-10-26T12:00:00+00:00",
            "book_timestamp": null,
            "displayed_at": "2026-10-26T12:00:00+00:00",
            "displayed_price": 0.3,
            "last_trade": 0.29,
            "last_trade_retrieved_at": "2026-10-26T12:00:00+00:00",
            "midpoint": 0.3,
            "midpoint_retrieved_at": "2026-10-26T12:00:00+00:00",
            "outcome_id": "910001:0",
            "source_urls": [
              "https://example.invalid/synthetic-public-prices"
            ],
            "warnings": []
          },
          {
            "best_ask": 0.35,
            "best_bid": 0.25,
            "book_retrieved_at": "2026-10-26T12:00:00+00:00",
            "book_timestamp": null,
            "displayed_at": "2026-10-26T12:00:00+00:00",
            "displayed_price": 0.7,
            "last_trade": 0.29,
            "last_trade_retrieved_at": "2026-10-26T12:00:00+00:00",
            "midpoint": 0.3,
            "midpoint_retrieved_at": "2026-10-26T12:00:00+00:00",
            "outcome_id": "910001:1",
            "source_urls": [
              "https://example.invalid/synthetic-public-prices"
            ],
            "warnings": []
          }
        ],
        "retrieved_at": "2026-10-26T12:00:00+00:00",
        "rules_version_id": 1,
        "snapshot_id": 1,
        "warnings": []
      },
      "status": "researching",
      "tags": [
        "single-contract",
        "synthetic"
      ],
      "warnings": []
    }
  ],
  "max_age_hours": 36.0,
  "schema_version": "polyberg_research_packet_v1",
  "selection": "event:810001",
  "warnings": []
}
```
