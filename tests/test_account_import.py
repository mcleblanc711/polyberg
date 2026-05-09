from __future__ import annotations

import json

import pytest

from polyberg.collectors.polymarket_account import (
    AccountImportError,
    PolymarketUSReadOnlyClient,
    PublicDataAccountClient,
    ReadOnlyHttpClient,
    build_query,
    build_signed_path,
    write_authenticated_account_snapshot,
    write_public_positions,
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


class RecordingOpener:
    def __init__(self, payload: object) -> None:
        self.payload = payload
        self.urls: list[str] = []
        self.headers: list[dict[str, str]] = []

    def __call__(self, request, timeout: float):
        self.urls.append(request.full_url)
        self.headers.append(dict(request.header_items()))
        return FakeResponse(self.payload)


def test_read_only_http_client_rejects_non_get() -> None:
    client = ReadOnlyHttpClient("https://example.local")

    with pytest.raises(AccountImportError, match="GET"):
        client.request_json("POST", "/v1/orders")


def test_public_positions_import_writes_raw_payload(tmp_path) -> None:
    opener = RecordingOpener([{"conditionId": "0xabc", "size": 10}])
    http = ReadOnlyHttpClient("https://data-api.polymarket.com", opener=opener)
    client = PublicDataAccountClient(http)
    output = tmp_path / "positions.json"

    write_public_positions("0x1111111111111111111111111111111111111111", output, client=client)
    data = json.loads(output.read_text(encoding="utf-8"))

    assert data["source"] == "polymarket_data_api_positions"
    assert data["payload"] == [{"conditionId": "0xabc", "size": 10}]
    assert "user=0x1111111111111111111111111111111111111111" in opener.urls[0]


def test_public_positions_rejects_malformed_address(tmp_path) -> None:
    with pytest.raises(AccountImportError, match="Wallet address"):
        write_public_positions("not-an-address", tmp_path / "positions.json")


def test_query_builder_repeats_list_values() -> None:
    assert build_query({"slugs": ["a", "b"], "limit": 100}) == "slugs=a&slugs=b&limit=100"


def test_signed_path_includes_query() -> None:
    assert build_signed_path("/v1/orders/open", {"slugs": ["a", "b"]}) == (
        "/v1/orders/open?slugs=a&slugs=b"
    )


def test_authenticated_client_refuses_to_sign_non_get() -> None:
    client = PolymarketUSReadOnlyClient(
        key_id="key",
        secret_key="secret",
        timestamp_ms=lambda: 123,
    )

    with pytest.raises(AccountImportError, match="GET"):
        client.auth_headers("POST", "/v1/orders")


def test_authenticated_snapshot_writes_three_raw_files(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(
        "polyberg.collectors.polymarket_account.sign_ed25519_message",
        lambda secret, message: "signed",
    )
    opener = RecordingOpener({"ok": True})
    http = ReadOnlyHttpClient("https://api.polymarket.us", opener=opener)
    client = PolymarketUSReadOnlyClient(
        key_id="key",
        secret_key="secret",
        http=http,
        timestamp_ms=lambda: 123,
    )

    paths = write_authenticated_account_snapshot(tmp_path, client=client)

    assert sorted(path.name for path in paths) == [
        "balances_raw.json",
        "open_orders_raw.json",
        "positions_raw.json",
    ]
    assert all(
        json.loads(path.read_text(encoding="utf-8"))["payload"] == {"ok": True}
        for path in paths
    )
    assert all(headers["X-pm-access-key"] == "key" for headers in opener.headers)
