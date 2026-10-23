"""Data API v2 collector: envelope, pagination, resolution normalization.

All HTTP goes through injected fakes — no network.
"""

from __future__ import annotations

from urllib.parse import parse_qs, urlparse

import pytest

from polyberg.collectors.polymarket_account import AccountImportError
from polyberg.collectors.polymarket_data_v2 import (
    RESOLUTIONS_BATCH_SIZE,
    DataApiV2Error,
    fetch_prices_history_v2,
    fetch_resolutions,
    normalize_resolution,
)

YES_1E18 = "1000000000000000000"


class ScriptedClient:
    """Returns queued payloads in order and records (path, params) per call."""

    def __init__(self, *payloads: object) -> None:
        self.payloads = list(payloads)
        self.calls: list[tuple[str, dict]] = []

    def get_json(self, path, params=None, headers=None):
        self.calls.append((path, dict(params or {})))
        return self.payloads.pop(0)


def _page(rows: list[dict], *, has_more: bool = False, cursor: str | None = None) -> dict:
    return {
        "data": rows,
        "pagination": {"limit": 2, "offset": 0, "has_more": has_more, "next_cursor": cursor},
    }


# --- prices-history ---------------------------------------------------------------


def test_prices_history_follows_cursor_and_resends_query() -> None:
    client = ScriptedClient(
        _page([{"timestamp": 1, "price": 0.1}], has_more=True, cursor="c1"),
        _page([{"timestamp": 2, "price": 0.2}]),
    )

    series = fetch_prices_history_v2("tok", http=client)  # type: ignore[arg-type]

    assert series == [{"t": 1, "p": 0.1}, {"t": 2, "p": 0.2}]
    first, second = (params for _, params in client.calls)
    assert "cursor" not in first
    # v2 rejects a cursor-only request: the original query rides along.
    assert second == {**first, "cursor": "c1"}
    assert first == {"token_id": "tok", "interval": "1m", "bucket_seconds": 3600}


def test_prices_history_stops_when_has_more_without_cursor() -> None:
    client = ScriptedClient(_page([{"timestamp": 1, "price": 0.1}], has_more=True, cursor=None))
    assert fetch_prices_history_v2("tok", http=client) == [{"t": 1, "p": 0.1}]  # type: ignore[arg-type]


def test_prices_history_aborts_runaway_pagination() -> None:
    pages = [_page([], has_more=True, cursor=f"c{i}") for i in range(3)]
    with pytest.raises(DataApiV2Error, match="did not paginate to end after 3 pages"):
        fetch_prices_history_v2("tok", http=ScriptedClient(*pages), max_pages=3)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("payload", "match"),
    [
        (["not", "an", "object"], "not an object"),
        ({"history": []}, "'data' is not a list"),
    ],
)
def test_prices_history_rejects_shape_drift(payload: object, match: str) -> None:
    with pytest.raises(DataApiV2Error, match=match):
        fetch_prices_history_v2("tok", http=ScriptedClient(payload))  # type: ignore[arg-type]


def test_prices_history_wraps_transport_errors() -> None:
    class Boom:
        def get_json(self, *_args, **_kwargs):
            raise AccountImportError("HTTP 503 while reading https://example")

    with pytest.raises(DataApiV2Error, match="HTTP 503"):
        fetch_prices_history_v2("tok", http=Boom())  # type: ignore[arg-type]


def test_prices_history_rejects_blank_token() -> None:
    with pytest.raises(DataApiV2Error, match="token_id"):
        fetch_prices_history_v2("")


# --- resolutions ------------------------------------------------------------------


@pytest.mark.parametrize(
    ("price", "expected"),
    [
        (YES_1E18, "YES"),
        ("0", "NO"),
        ("500000000000000000", "50-50"),
        ("1", "YES"),
        ("69", None),  # UMA's unset sentinel
        (None, None),
        ("garbage", None),
    ],
)
def test_normalize_resolution_maps_uma_prices(price: str | None, expected: str | None) -> None:
    row = normalize_resolution({"status": "resolved", "proposed_price": price, "price": price})
    assert row["proposed_outcome"] == expected
    assert row["settled_outcome"] == expected


def test_normalize_resolution_prefers_payouts_over_price() -> None:
    row = normalize_resolution(
        {"status": "resolved", "price": "0", "payouts": [1_000_000, 0], "was_disputed": True}
    )
    assert row["settled_outcome"] == "YES"
    assert row["was_disputed"] is True


def test_normalize_resolution_unsettled_has_no_settled_outcome() -> None:
    row = normalize_resolution(
        {
            "status": "proposed",
            "proposed_price": "0",
            "price": "0",
            "expected_settlement_time": "2026-10-24T12:00:00Z",
        }
    )
    assert row == {
        "oracle_status": "proposed",
        "was_disputed": False,
        "extended_review": False,
        "proposed_outcome": "NO",
        "settled_outcome": None,
        "resolved_at": None,
        "expected_settlement_time": "2026-10-24T12:00:00Z",
    }


def test_fetch_resolutions_batches_dedupes_and_keys_lowercase() -> None:
    ids = [f"0x{i:064X}" for i in range(RESOLUTIONS_BATCH_SIZE + 1)]
    client = ScriptedClient(
        {
            "data": [
                {"condition_id": ids[0].lower(), "status": "posed"},
                # A later row for the same condition loses to the first.
                {"condition_id": ids[0].lower(), "status": "resolved"},
                "junk",
            ]
        },
        {"data": [{"condition_id": ids[-1].lower(), "status": "disputed"}]},
    )

    out = fetch_resolutions([*ids, ids[0]], http=client)  # type: ignore[arg-type]

    assert [path for path, _ in client.calls] == ["/resolutions", "/resolutions"]
    first_batch = client.calls[0][1]["condition"].split(",")
    assert len(first_batch) == RESOLUTIONS_BATCH_SIZE
    assert client.calls[1][1]["condition"] == ids[-1].lower()
    assert out[ids[0].lower()]["oracle_status"] == "posed"
    assert out[ids[-1].lower()]["oracle_status"] == "disputed"
    assert set(out) == {ids[0].lower(), ids[-1].lower()}


def test_fetch_resolutions_comma_list_survives_url_encoding() -> None:
    from polyberg.collectors.polymarket_account import ReadOnlyHttpClient
    from polyberg.collectors.polymarket_data_v2 import DATA_API_V2_BASE_URL

    url = ReadOnlyHttpClient(DATA_API_V2_BASE_URL).build_url(
        "/resolutions", {"condition": "0xa,0xb"}
    )
    assert parse_qs(urlparse(url).query)["condition"] == ["0xa,0xb"]


def test_fetch_resolutions_empty_input_makes_no_request() -> None:
    client = ScriptedClient()
    assert fetch_resolutions([], http=client) == {}  # type: ignore[arg-type]
    assert client.calls == []
