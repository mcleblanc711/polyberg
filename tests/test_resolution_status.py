"""resolution-status: oracle lifecycle suggestion, artifact builder, CLI wiring.

Fetchers are injected or monkeypatched — no network.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest
import yaml

from polyberg import cli
from polyberg.collectors.polymarket_data_v2 import DataApiV2Error
from polyberg.lifecycle import suggest_lifecycle_from_oracle
from polyberg.models import MarketRegistry
from polyberg.resolution_status import build_resolution_status_artifact

_NOW = datetime(2026, 10, 23, 12, 0, tzinfo=UTC)


def _row(status: str, **extra) -> dict:
    return {
        "oracle_status": status,
        "was_disputed": False,
        "extended_review": False,
        "proposed_outcome": None,
        "settled_outcome": None,
        "resolved_at": None,
        "expected_settlement_time": None,
        **extra,
    }


def _write_registry(path: Path, entries: list[tuple[str, str, str | None]]) -> Path:
    """entries: (market_id, lifecycle, condition_id or None)."""
    lines = ["markets:"]
    for market_id, lifecycle, condition_id in entries:
        lines.extend(
            [
                f"  - market_id: {market_id}",
                f"    name: {market_id}",
                "    polymarket_url: https://example.invalid",
                "    category: test",
                "    rule_key: test",
                "    oracle_type: pure_data",
                '    preferred_side: "YES"',
                "    risk_flags: []",
                "    resolution_date: 2026-10-31",
                f"    lifecycle: {lifecycle}",
                '    notes: ""',
            ]
        )
        if condition_id:
            lines.append(f'    condition_id: "{condition_id}"')
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


# --- lifecycle suggestion ---------------------------------------------------------


@pytest.mark.parametrize(
    ("current", "status", "expected"),
    [
        ("active", "posed", None),
        ("active", "proposed", "resolving"),
        ("active", "disputed", "resolving"),
        ("active", "resolved", "resolved"),
        ("resolving", "proposed", None),  # already there
        ("resolving", "resolved", "resolved"),
        ("resolving", "posed", None),  # never backward (date-based resolving stands)
        ("resolved", "proposed", None),
        ("archived", "resolved", None),  # manual archive outranks the oracle
        ("active", "something_new", None),
    ],
)
def test_suggest_lifecycle_from_oracle_is_forward_only(
    current: str, status: str, expected: str | None
) -> None:
    assert suggest_lifecycle_from_oracle(current, status) == expected


# --- artifact builder ---------------------------------------------------------------


def test_artifact_records_status_suggestion_and_skips(tmp_path: Path) -> None:
    registry = _write_registry(
        tmp_path / "market_registry.yaml",
        [
            ("m_resolved", "active", "0xAA"),
            ("m_open", "active", "0xbb"),
            ("m_no_row", "active", "0xcc"),
            ("m_no_condition", "active", None),
        ],
    )
    seen: list[list[str]] = []

    def fake_fetch(condition_ids) -> dict:
        seen.append(list(condition_ids))
        return {
            "0xaa": _row("resolved", settled_outcome="YES"),
            "0xbb": _row("posed"),
        }

    output = tmp_path / "live" / "resolution_status.json"
    build_resolution_status_artifact(
        output, registry_path=registry, fetcher=fake_fetch, now=_NOW
    )
    payload = json.loads(output.read_text(encoding="utf-8"))

    assert seen == [["0xAA", "0xbb", "0xcc"]]
    assert payload["as_of"] == _NOW.isoformat()
    resolved = payload["markets"]["m_resolved"]
    # Registry case is preserved even though the lookup is case-insensitive.
    assert resolved["condition_id"] == "0xAA"
    assert resolved["lifecycle"] == "active"
    assert resolved["settled_outcome"] == "YES"
    assert resolved["suggested_lifecycle"] == "resolved"
    assert payload["markets"]["m_open"]["suggested_lifecycle"] is None
    assert payload["skipped"] == [
        {"market_id": "m_no_condition", "reason": "missing condition_id"},
        {"market_id": "m_no_row", "reason": "no resolution row"},
    ]


def test_artifact_without_conditions_makes_no_fetch(tmp_path: Path) -> None:
    registry = _write_registry(tmp_path / "r.yaml", [("m_only", "active", None)])

    def boom(_ids):
        raise AssertionError("fetch should not run")

    output = tmp_path / "out.json"
    build_resolution_status_artifact(output, registry_path=registry, fetcher=boom, now=_NOW)
    assert json.loads(output.read_text(encoding="utf-8"))["markets"] == {}


# --- CLI ------------------------------------------------------------------------------


def test_cli_resolution_status_writes_artifact(tmp_path: Path, monkeypatch, capsys) -> None:
    _write_registry(tmp_path / "market_registry.yaml", [("m_x", "active", "0xaa")])
    monkeypatch.setattr(
        "polyberg.resolution_status.fetch_resolutions",
        lambda ids: {"0xaa": _row("proposed", proposed_outcome="NO")},
    )
    output = tmp_path / "status.json"

    code = cli.main(
        ["resolution-status", "--context-dir", str(tmp_path), "--output", str(output)]
    )

    assert code == 0
    assert str(output) in capsys.readouterr().out
    entry = json.loads(output.read_text(encoding="utf-8"))["markets"]["m_x"]
    assert entry["suggested_lifecycle"] == "resolving"


def test_cli_resolution_status_reports_api_failure(tmp_path: Path, monkeypatch, capsys) -> None:
    _write_registry(tmp_path / "market_registry.yaml", [("m_x", "active", "0xaa")])

    def fail(_ids):
        raise DataApiV2Error("HTTP 503 while reading https://data-api")

    monkeypatch.setattr("polyberg.resolution_status.fetch_resolutions", fail)

    code = cli.main(
        ["resolution-status", "--context-dir", str(tmp_path), "--output", str(tmp_path / "o.json")]
    )

    assert code == 1
    assert "HTTP 503" in capsys.readouterr().err


def test_cli_registry_update_sets_lifecycle(tmp_path: Path) -> None:
    path = _write_registry(tmp_path / "market_registry.yaml", [("m_x", "active", "0xaa")])

    code = cli.main(
        [
            "registry-update",
            "--market-id",
            "m_x",
            "--lifecycle",
            "resolved",
            "--context-dir",
            str(tmp_path),
        ]
    )

    assert code == 0
    registry = MarketRegistry(**yaml.safe_load(path.read_text(encoding="utf-8")))
    assert registry.markets[0].lifecycle == "resolved"
    assert registry.markets[0].condition_id == "0xaa"  # identifiers untouched


def test_cli_registry_update_rejects_unknown_lifecycle(tmp_path: Path) -> None:
    _write_registry(tmp_path / "market_registry.yaml", [("m_x", "active", "0xaa")])
    with pytest.raises(SystemExit):
        cli.main(
            [
                "registry-update",
                "--market-id",
                "m_x",
                "--lifecycle",
                "done",
                "--context-dir",
                str(tmp_path),
            ]
        )
