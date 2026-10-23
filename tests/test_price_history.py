from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from polyberg.collectors.polymarket_account import AccountImportError, ReadOnlyHttpClient
from polyberg.collectors.polymarket_data_v2 import DATA_API_V2_BASE_URL
from polyberg.collectors.polymarket_gamma import (
    CLOB_API_BASE_URL,
    GammaCollectorError,
    fetch_clob_price_history,
    fetch_price_history,
)
from polyberg.price_history import _windows_from_series, build_price_history_artifact


class FakeResponse:
    def __init__(self, payload: object) -> None:
        self.payload = payload

    def __enter__(self) -> FakeResponse:
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def read(self) -> bytes:
        return json.dumps(self.payload).encode("utf-8")


class RecordingOpener:
    def __init__(self, payload: object) -> None:
        self.payload = payload
        self.urls: list[str] = []

    def __call__(self, request, timeout: float):
        self.urls.append(request.full_url)
        return FakeResponse(self.payload)


class BoomClient:
    def __init__(self, message: str = "HTTP 502 while reading https://example") -> None:
        self.message = message
        self.calls = 0

    def get_json(self, *_args, **_kwargs):
        self.calls += 1
        raise AccountImportError(self.message)


def test_fetch_price_history_prefers_v2_and_maps_points() -> None:
    v2 = RecordingOpener(
        {
            "data": [
                {"timestamp": 1, "price": 0.5, "resolution_seconds": 3600},
                {"timestamp": 2, "price": 0.55, "resolution_seconds": 0},
                {"timestamp": "bad", "price": 0.1},
            ],
            "pagination": {"limit": 10000, "offset": 0, "has_more": False, "next_cursor": None},
        }
    )
    clob = BoomClient()

    series = fetch_price_history(
        "0xToken",
        http=ReadOnlyHttpClient(DATA_API_V2_BASE_URL, opener=v2),
        clob_http=clob,  # type: ignore[arg-type]
    )

    assert series == [{"t": 1, "p": 0.5}, {"t": 2, "p": 0.55}]
    assert v2.urls[0].startswith(DATA_API_V2_BASE_URL + "/prices-history?")
    assert "token_id=0xToken" in v2.urls[0]
    assert "interval=1m" in v2.urls[0]
    # CLOB fidelity is minutes; v2 bucket_seconds is seconds.
    assert "bucket_seconds=3600" in v2.urls[0]
    assert clob.calls == 0


def test_fetch_price_history_falls_back_to_clob_when_v2_fails() -> None:
    clob = RecordingOpener({"history": [{"t": 1, "p": 0.5}]})

    series = fetch_price_history(
        "0xToken",
        http=BoomClient(),  # type: ignore[arg-type]
        clob_http=ReadOnlyHttpClient(CLOB_API_BASE_URL, opener=clob),
    )

    assert series == [{"t": 1, "p": 0.5}]
    assert clob.urls[0].startswith(CLOB_API_BASE_URL + "/prices-history?")


def test_fetch_price_history_reports_both_failures() -> None:
    with pytest.raises(GammaCollectorError, match=r"HTTP 500.*v2 also failed: HTTP 502"):
        fetch_price_history(
            "0xToken",
            http=BoomClient(),  # type: ignore[arg-type]
            clob_http=BoomClient("HTTP 500 while reading https://clob"),  # type: ignore[arg-type]
        )


def test_fetch_price_history_rejects_blank_token() -> None:
    with pytest.raises(GammaCollectorError, match="token_id"):
        fetch_price_history("")


def test_fetch_clob_price_history_returns_cleaned_points() -> None:
    opener = RecordingOpener(
        {"history": [{"t": 1, "p": 0.5}, {"t": 2, "p": 0.55}, "junk", {"t": "bad", "p": 0.1}]}
    )
    client = ReadOnlyHttpClient(CLOB_API_BASE_URL, opener=opener)

    series = fetch_clob_price_history("0xToken", http=client)

    assert series == [{"t": 1, "p": 0.5}, {"t": 2, "p": 0.55}]
    assert opener.urls[0].startswith(CLOB_API_BASE_URL + "/prices-history?")
    assert "market=0xToken" in opener.urls[0]
    assert "interval=1m" in opener.urls[0]
    assert "fidelity=60" in opener.urls[0]


def test_fetch_clob_price_history_wraps_http_errors() -> None:
    with pytest.raises(GammaCollectorError, match="HTTP 502"):
        fetch_clob_price_history("0xToken", http=BoomClient())  # type: ignore[arg-type]


def test_fetch_clob_price_history_rejects_non_dict_response() -> None:
    class ListClient:
        def get_json(self, *_args, **_kwargs):
            return ["nope"]

    with pytest.raises(GammaCollectorError, match="not an object"):
        fetch_clob_price_history("0xToken", http=ListClient())  # type: ignore[arg-type]


def test_windows_from_series_picks_high_low_per_window() -> None:
    now = 1_000_000
    day = 24 * 3600
    series = [
        {"t": now - 25 * day, "p": 0.10},
        {"t": now - 10 * day, "p": 0.70},
        {"t": now - 3 * day, "p": 0.40},
        {"t": now - 12 * 3600, "p": 0.55},
        {"t": now - 2 * 3600, "p": 0.45},
    ]
    windows = _windows_from_series(series, now)
    assert windows["d1"] == {"high": 0.55, "low": 0.45}
    assert windows["w1"] == {"high": 0.55, "low": 0.40}
    assert windows["m1"] == {"high": 0.70, "low": 0.10}


def test_windows_from_series_empty_window_is_zero() -> None:
    windows = _windows_from_series([], now_ts=1_000_000)
    assert windows == {
        "d1": {"high": 0.0, "low": 0.0},
        "w1": {"high": 0.0, "low": 0.0},
        "m1": {"high": 0.0, "low": 0.0},
    }


def test_build_price_history_artifact_skips_missing_tokens(tmp_path: Path) -> None:
    registry_path = tmp_path / "registry.yaml"
    registry_path.write_text(
        _registry_yaml(
            [
                ("market_with_token", "tok-abc"),
                ("market_no_token", ""),
            ]
        ),
        encoding="utf-8",
    )

    calls: list[str] = []

    def fake_fetch(token_id: str) -> list[dict]:
        calls.append(token_id)
        return [{"t": 1_000_000 - 10, "p": 0.5}, {"t": 1_000_000, "p": 0.6}]

    output = tmp_path / "price_history.json"
    build_price_history_artifact(
        output,
        registry_path=registry_path,
        fetcher=fake_fetch,
        now=datetime(2026, 5, 11, tzinfo=UTC),
    )
    payload = json.loads(output.read_text(encoding="utf-8"))

    assert calls == ["tok-abc"]
    assert set(payload["markets"]) == {"market_with_token"}
    assert payload["skipped"] == [
        {"market_id": "market_no_token", "reason": "missing yes_token_id"}
    ]
    entry = payload["markets"]["market_with_token"]
    assert entry["yes_token_id"] == "tok-abc"
    assert entry["series"][0] == {"t": 1_000_000 - 10, "p": 0.5}
    assert set(entry["windows"]) == {"d1", "w1", "m1"}


def test_build_price_history_artifact_records_fetch_errors(tmp_path: Path) -> None:
    registry_path = tmp_path / "registry.yaml"
    registry_path.write_text(_registry_yaml([("flaky_market", "tok-flaky")]), encoding="utf-8")

    def fake_fetch(_token_id: str) -> list[dict]:
        raise GammaCollectorError("HTTP 429 rate limited")

    output = tmp_path / "price_history.json"
    build_price_history_artifact(
        output,
        registry_path=registry_path,
        fetcher=fake_fetch,
        now=datetime(2026, 5, 11, tzinfo=UTC),
    )
    payload = json.loads(output.read_text(encoding="utf-8"))

    assert payload["markets"] == {}
    assert payload["skipped"] == [{"market_id": "flaky_market", "reason": "HTTP 429 rate limited"}]


def _registry_yaml(entries: list[tuple[str, str]]) -> str:
    lines = ["markets:"]
    for market_id, token in entries:
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
                "    resolution_date: 2027-01-01",
                '    notes: ""',
                f'    yes_token_id: "{token}"',
            ]
        )
    return "\n".join(lines) + "\n"
