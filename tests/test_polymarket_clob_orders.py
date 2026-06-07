from __future__ import annotations

import base64
import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from polyberg.collectors.polymarket_account import (
    AccountImportError,
    ReadOnlyHttpClient,
)
from polyberg.collectors.polymarket_clob_auth import (
    ClobCredentials,
    build_hmac_signature,
)
from polyberg.collectors.polymarket_clob_orders import (
    fetch_open_orders,
    write_clob_open_orders,
)

TEST_SECRET = base64.urlsafe_b64encode(b"\x01" * 32).decode("ascii")
TEST_WALLET = "0x1111111111111111111111111111111111111111"


def _creds() -> ClobCredentials:
    return ClobCredentials(
        address=TEST_WALLET,
        api_key="test-key",
        api_secret=TEST_SECRET,
        api_passphrase="test-passphrase",
    )


class FakeResponse:
    def __init__(self, payload: object) -> None:
        self.payload = payload

    def __enter__(self) -> FakeResponse:
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def read(self) -> bytes:
        return json.dumps(self.payload).encode("utf-8")


class ScriptedOpener:
    """Opener that serves a queued list of responses, one per request."""

    def __init__(self, responses: list[object]) -> None:
        self._responses = list(responses)
        self.urls: list[str] = []
        self.headers: list[dict[str, str]] = []

    def __call__(self, request, timeout):
        self.urls.append(request.full_url)
        self.headers.append(dict(request.header_items()))
        if not self._responses:
            raise AssertionError("Opener exhausted — unexpected extra request")
        return FakeResponse(self._responses.pop(0))


def _make_http(opener: ScriptedOpener) -> ReadOnlyHttpClient:
    return ReadOnlyHttpClient("https://clob.local", opener=opener)


def test_fetch_open_orders_returns_single_page_when_end_cursor_sent() -> None:
    opener = ScriptedOpener(
        [{"data": [{"id": "ord-1"}, {"id": "ord-2"}], "next_cursor": "LTE="}]
    )
    http = _make_http(opener)

    orders = fetch_open_orders(_creds(), http=http, timestamp_seconds=lambda: 1700000000)

    assert [o["id"] for o in orders] == ["ord-1", "ord-2"]
    assert len(opener.urls) == 1
    assert "/data/orders" in opener.urls[0]
    assert "next_cursor=MA%3D%3D" in opener.urls[0]


def test_fetch_open_orders_follows_pagination_to_end() -> None:
    opener = ScriptedOpener(
        [
            {"data": [{"id": "ord-1"}], "next_cursor": "CURSOR-1"},
            {"data": [{"id": "ord-2"}], "next_cursor": "CURSOR-2"},
            {"data": [{"id": "ord-3"}], "next_cursor": "LTE="},
        ]
    )
    http = _make_http(opener)

    orders = fetch_open_orders(_creds(), http=http, timestamp_seconds=lambda: 1700000000)

    assert [o["id"] for o in orders] == ["ord-1", "ord-2", "ord-3"]
    assert len(opener.urls) == 3
    # Each successive request carries the previously returned cursor.
    assert "next_cursor=MA%3D%3D" in opener.urls[0]
    assert "next_cursor=CURSOR-1" in opener.urls[1]
    assert "next_cursor=CURSOR-2" in opener.urls[2]


def test_fetch_open_orders_attaches_signed_headers() -> None:
    opener = ScriptedOpener([{"data": [], "next_cursor": "LTE="}])
    http = _make_http(opener)

    fetch_open_orders(_creds(), http=http, timestamp_seconds=lambda: 1700000000)

    headers = opener.headers[0]
    # urllib normalizes header names to Title-Case; assert case-insensitive.
    lowered = {k.lower(): v for k, v in headers.items()}
    assert lowered["poly_address"] == TEST_WALLET
    assert lowered["poly_timestamp"] == "1700000000"
    assert lowered["poly_api_key"] == "test-key"
    assert lowered["poly_passphrase"] == "test-passphrase"
    # Signature is over the bare path /data/orders only (matching py-clob-client,
    # which builds headers once outside the pagination loop).
    expected_sig = build_hmac_signature(
        TEST_SECRET, 1700000000, "GET", "/data/orders"
    )
    assert lowered["poly_signature"] == expected_sig


def test_fetch_open_orders_reuses_same_signature_across_pages() -> None:
    opener = ScriptedOpener(
        [
            {"data": [{"id": "ord-1"}], "next_cursor": "C1"},
            {"data": [{"id": "ord-2"}], "next_cursor": "LTE="},
        ]
    )
    http = _make_http(opener)

    fetch_open_orders(_creds(), http=http, timestamp_seconds=lambda: 1700000000)

    page1_lowered = {k.lower(): v for k, v in opener.headers[0].items()}
    page2_lowered = {k.lower(): v for k, v in opener.headers[1].items()}
    assert page1_lowered["poly_signature"] == page2_lowered["poly_signature"]
    assert page1_lowered["poly_timestamp"] == page2_lowered["poly_timestamp"]


def test_fetch_open_orders_passes_optional_filters_as_query_params() -> None:
    opener = ScriptedOpener([{"data": [], "next_cursor": "LTE="}])
    http = _make_http(opener)

    fetch_open_orders(
        _creds(),
        market="0xabc",
        asset_id="123",
        order_id="ord-xyz",
        http=http,
        timestamp_seconds=lambda: 1700000000,
    )

    url = opener.urls[0]
    assert "market=0xabc" in url
    assert "asset_id=123" in url
    assert "id=ord-xyz" in url


def test_fetch_open_orders_raises_on_non_dict_response() -> None:
    opener = ScriptedOpener([[1, 2, 3]])
    http = _make_http(opener)

    with pytest.raises(AccountImportError, match="not an object"):
        fetch_open_orders(_creds(), http=http, timestamp_seconds=lambda: 1700000000)


def test_fetch_open_orders_raises_on_non_list_data() -> None:
    opener = ScriptedOpener([{"data": {"oops": "object"}, "next_cursor": "LTE="}])
    http = _make_http(opener)

    with pytest.raises(AccountImportError, match="'data' field"):
        fetch_open_orders(_creds(), http=http, timestamp_seconds=lambda: 1700000000)


def test_fetch_open_orders_safety_stops_on_runaway_pagination() -> None:
    opener = ScriptedOpener(
        [{"data": [], "next_cursor": f"CURSOR-{i}"} for i in range(5)]
    )
    http = _make_http(opener)

    with pytest.raises(AccountImportError, match="did not paginate to end"):
        fetch_open_orders(
            _creds(),
            http=http,
            timestamp_seconds=lambda: 1700000000,
            max_pages=3,
        )


def test_write_clob_open_orders_writes_payload_keyed_json(tmp_path: Path) -> None:
    opener = ScriptedOpener(
        [{"data": [{"id": "ord-1", "side": "BUY"}], "next_cursor": "LTE="}]
    )
    http = _make_http(opener)
    output = tmp_path / "account" / "open_orders_clob.json"
    frozen = datetime(2026, 5, 11, 12, 0, 0, tzinfo=UTC)

    path = write_clob_open_orders(
        _creds(),
        output,
        http=http,
        timestamp_seconds=lambda: 1700000000,
        now=frozen,
    )

    assert path == output
    doc = json.loads(output.read_text(encoding="utf-8"))
    assert doc["source"] == "polymarket_clob_open_orders"
    assert doc["wallet_address"] == TEST_WALLET
    assert doc["as_of"] == frozen.isoformat()
    assert doc["payload"] == [{"id": "ord-1", "side": "BUY"}]
