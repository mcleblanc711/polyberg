"""geo-check: Polymarket geoblock read, artifact, CLI. Injected HTTP only."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from polyberg import cli
from polyberg.collectors.polymarket_account import AccountImportError
from polyberg.collectors.polymarket_geoblock import (
    GEOBLOCK_PATH,
    GeoblockError,
    fetch_geoblock,
    write_geo_status,
)


class FakeClient:
    def __init__(self, payload: object) -> None:
        self.payload = payload
        self.paths: list[str] = []

    def get_json(self, path, params=None, headers=None):
        self.paths.append(path)
        return self.payload


def test_fetch_geoblock_normalizes_and_drops_ip() -> None:
    client = FakeClient({"blocked": True, "ip": "203.0.113.7", "country": "ca", "region": "ab"})

    status = fetch_geoblock(http=client)  # type: ignore[arg-type]

    assert client.paths == [GEOBLOCK_PATH]
    assert status == {"blocked": True, "country": "CA", "region": "AB"}


def test_fetch_geoblock_tolerates_missing_location() -> None:
    status = fetch_geoblock(http=FakeClient({"blocked": False}))  # type: ignore[arg-type]
    assert status == {"blocked": False, "country": "", "region": ""}


@pytest.mark.parametrize("payload", [["nope"], {"country": "CA"}, {"blocked": "yes"}])
def test_fetch_geoblock_rejects_shape_drift(payload: object) -> None:
    with pytest.raises(GeoblockError, match="Unexpected geoblock response"):
        fetch_geoblock(http=FakeClient(payload))  # type: ignore[arg-type]


def test_fetch_geoblock_wraps_transport_errors() -> None:
    class Boom:
        def get_json(self, *_args, **_kwargs):
            raise AccountImportError("HTTP 503 while reading https://polymarket.com")

    with pytest.raises(GeoblockError, match="HTTP 503"):
        fetch_geoblock(http=Boom())  # type: ignore[arg-type]


def test_write_geo_status_records_check_without_ip(tmp_path: Path) -> None:
    out = tmp_path / "live" / "geo_status.json"
    now = datetime(2026, 10, 23, 12, 0, tzinfo=UTC)

    write_geo_status(
        out,
        http=FakeClient({"blocked": False, "ip": "203.0.113.7", "country": "CA", "region": "SK"}),  # type: ignore[arg-type]
        now=now,
    )

    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload == {
        "as_of": now.isoformat(),
        "source": "https://polymarket.com/api/geoblock",
        "blocked": False,
        "country": "CA",
        "region": "SK",
    }
    assert "203.0.113.7" not in out.read_text(encoding="utf-8")


def test_cli_geo_check_reports_location(tmp_path: Path, monkeypatch, capsys) -> None:
    monkeypatch.setattr(
        "polyberg.collectors.polymarket_geoblock.fetch_geoblock",
        lambda http=None: {"blocked": True, "country": "CA", "region": "AB"},
    )
    out = tmp_path / "geo.json"

    assert cli.main(["geo-check", "--output", str(out)]) == 0

    stdout = capsys.readouterr().out
    assert "CA-AB — BLOCKED" in stdout
    assert json.loads(out.read_text(encoding="utf-8"))["region"] == "AB"


def test_cli_geo_check_reports_failure(tmp_path: Path, monkeypatch, capsys) -> None:
    def fail(http=None):
        raise GeoblockError("HTTP 503 while reading https://polymarket.com")

    monkeypatch.setattr("polyberg.collectors.polymarket_geoblock.fetch_geoblock", fail)

    assert cli.main(["geo-check", "--output", str(tmp_path / "geo.json")]) == 1
    assert "HTTP 503" in capsys.readouterr().err
