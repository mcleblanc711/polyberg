"""Rebuild three guaranteed synthetic, reproducible research handoffs. No network calls."""

from __future__ import annotations

import tempfile
from pathlib import Path
from unittest.mock import patch

from polyberg.research.models import Discovery, Source, canonical, digest
from polyberg.research.packets import freeze, render
from polyberg.research.public import normalize_event
from polyberg.research.storage import Store
from polyberg.research.workspace import Workspace

AT = "2026-10-26T12:00:00+00:00"
ROOT = Path(__file__).resolve().parents[1] / "examples" / "research"


def contract(mid: str, title: str, end: str, probability: str, rules: str):
    return {
        "id": mid,
        "slug": f"synthetic-{mid}",
        "question": title,
        "conditionId": "0x" + f"{int(mid):064x}",
        "questionID": f"synthetic-question-{mid}",
        "version": "v2",
        "positionIds": [f"{mid}0", f"{mid}1"],
        "outcomes": '["Yes", "No"]',
        "outcomePrices": probability,
        "active": True,
        "endDate": end,
        "description": rules,
        "resolutionSource": "https://example.invalid/fictional-observatory",
    }


def scenario(name: str, eid: str, contracts: list[dict]):
    raw = {
        "id": eid,
        "slug": name,
        "title": f"SYNTHETIC EXAMPLE: {name}",
        "description": "Fictional training example. These are not real markets or observations.",
        "markets": contracts,
    }
    event, markets = normalize_event(raw, AT)
    for market in markets:
        for q in market.quotes:
            q.best_bid = 0.25
            q.best_ask = 0.35
            q.midpoint = 0.30
            q.last_trade = 0.29
            q.book_retrieved_at = q.midpoint_retrieved_at = q.last_trade_retrieved_at = AT
            q.source_urls = ["https://example.invalid/synthetic-public-prices"]
    with (
        tempfile.TemporaryDirectory() as directory,
        patch("polyberg.research.workspace.utcnow", return_value=AT),
        patch("polyberg.research.storage.utcnow", return_value=AT),
    ):
        with Store(Path(directory) / "example.sqlite3") as store:
            w = Workspace(store)
            w.ingest(Discovery(events=[event], markets=markets), follow=True)
            for market in markets:
                mid = market.identification.market_id
                w.set_status(mid, "researching")
                w.tags(mid, ["synthetic", name])
                version = w.rules_history(mid)[0].rules_version_id
                if name == "weekly-distribution":
                    w.annotate(
                        mid,
                        version,
                        "measurement_period",
                        "Fictional week: 2026-10-26 through 2026-11-01 UTC inclusive.",
                        "https://example.invalid/fictional-rules",
                    )
                w.annotate(
                    mid,
                    version,
                    "resolution_deadline",
                    "Fictional scheduled resolution: 2026-11-10T12:00:00Z.",
                    "https://example.invalid/fictional-rules",
                )
                entry = w.add_entry(
                    mid,
                    "observation",
                    "SYNTHETIC: fictional Observatory report exists.",
                    [
                        Source(
                            url="https://example.invalid/fictional-report",
                            title="Fictional report",
                            published_at=AT,
                            observed_at=AT,
                        )
                    ],
                )
                w.verify_entry(entry)
                for category, text in [
                    ("catalyst", "SYNTHETIC: next fictional Observatory print."),
                    ("hypothesis", "SYNTHETIC: the next report may revise the measurement."),
                    ("question", "SYNTHETIC: how are missing daily observations handled?"),
                    (
                        "model_interpretation",
                        "SYNTHETIC MODEL OUTPUT: consider a revised-data scenario.",
                    ),
                ]:
                    w.add_entry(mid, category, text, [])
            if len(markets) > 1:
                w.relate(
                    markets[0].identification.market_id,
                    markets[1].identification.market_id,
                    "alternative_deadline"
                    if name == "multiple-deadlines"
                    else "mutually_exclusive",
                    "SYNTHETIC: explicitly reviewed contract relationship; "
                    "no inferred implication.",
                    "https://example.invalid/fictional-rules",
                )
            frozen = freeze(w, event=eid, generated_at=AT)
            destination = ROOT / name
            destination.mkdir(parents=True, exist_ok=True)
            contents = render(frozen)
            for filename, content in contents.items():
                (destination / filename).write_text(content, encoding="utf-8", newline="\n")
            (destination / "manifest.json").write_text(
                canonical(
                    {
                        "schema_version": "polyberg_research_export_v1",
                        "packet_id": frozen.packet_id,
                        "snapshot_sha256": frozen.snapshot_sha256,
                        "files": {
                            filename: digest(content) for filename, content in contents.items()
                        },
                        "synthetic": True,
                        "scenario": name,
                    }
                ),
                encoding="utf-8",
            )


def main():
    rules = (
        "SYNTHETIC RULES — fictional demonstration only.\n"
        "Resolve using the fictional Observatory's published measurement.\n"
        "Scheduled resolution: November 10, 2026 at 12:00 UTC.\n"
        "Unknown fallback and dispute procedures remain unestablished."
    )
    scenario(
        "single-contract",
        "810001",
        [
            contract(
                "910001",
                "SYNTHETIC: will the fictional index exceed 50?",
                "2026-11-01T00:00:00Z",
                '["0.30", "0.70"]',
                rules,
            )
        ],
    )
    scenario(
        "multiple-deadlines",
        "810002",
        [
            contract(
                "920001",
                "SYNTHETIC: index above 50 by November 1?",
                "2026-11-01T00:00:00Z",
                '["0.30", "0.70"]',
                rules + "\nObservation cutoff: November 1, 2026.",
            ),
            contract(
                "920002",
                "SYNTHETIC: index above 50 by November 8?",
                "2026-11-08T00:00:00Z",
                '["0.45", "0.55"]',
                rules + "\nObservation cutoff: November 8, 2026.",
            ),
        ],
    )
    weekly_rules = rules + (
        "\nMeasurement period: October 26 through November 1, 2026 UTC inclusive."
        "\nThe fictional total determines the matching non-overlapping band."
    )
    scenario(
        "weekly-distribution",
        "810003",
        [
            contract(
                "930001",
                "SYNTHETIC: weekly fictional count below 10?",
                "2026-11-02T00:00:00Z",
                '["0.20", "0.80"]',
                weekly_rules,
            ),
            contract(
                "930002",
                "SYNTHETIC: weekly fictional count 10–19?",
                "2026-11-02T00:00:00Z",
                '["0.30", "0.70"]',
                weekly_rules,
            ),
            contract(
                "930003",
                "SYNTHETIC: weekly fictional count 20 or more?",
                "2026-11-02T00:00:00Z",
                '[null, "0.50"]',
                weekly_rules,
            ),
        ],
    )


if __name__ == "__main__":
    main()
