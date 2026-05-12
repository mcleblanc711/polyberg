from __future__ import annotations

import json
from datetime import datetime, timezone
from decimal import Decimal
from urllib.error import HTTPError, URLError

import pytest

from polyberg.collectors.polymarket_account import AccountImportError
from polyberg.collectors.polygon_rpc import (
    PolygonRpcError,
    USDC_E_CONTRACT,
    _balance_of_calldata,
    fetch_usdc_balance,
    write_usdc_balance,
)


class FakeResponse:
    def __init__(self, payload: object) -> None:
        self.payload = payload

    def __enter__(self) -> "FakeResponse":
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def read(self) -> bytes:
        return json.dumps(self.payload).encode("utf-8")


class RecordingOpener:
    def __init__(self, payload: object) -> None:
        self.payload = payload
        self.urls: list[str] = []
        self.bodies: list[dict] = []
        self.methods: list[str] = []

    def __call__(self, request, timeout: float):
        self.urls.append(request.full_url)
        self.methods.append(request.get_method())
        if request.data is not None:
            self.bodies.append(json.loads(request.data.decode("utf-8")))
        return FakeResponse(self.payload)


def test_fetch_usdc_balance_happy_path() -> None:
    # 100.500000 USDC → 100_500_000 raw → hex 0x5fdaa80
    opener = RecordingOpener({"jsonrpc": "2.0", "id": 1, "result": hex(100_500_000)})
    wallet = "0x1111111111111111111111111111111111111111"

    balance = fetch_usdc_balance(wallet, rpc_url="https://rpc.local", opener=opener)

    assert balance == Decimal("100.5")
    assert opener.urls == ["https://rpc.local"]
    assert opener.methods == ["POST"]
    body = opener.bodies[0]
    assert body["method"] == "eth_call"
    assert body["params"][1] == "latest"
    call = body["params"][0]
    assert call["to"] == USDC_E_CONTRACT
    assert call["data"] == _balance_of_calldata(wallet)


def test_fetch_usdc_balance_returns_zero_for_empty_wallet() -> None:
    opener = RecordingOpener({"jsonrpc": "2.0", "id": 1, "result": "0x0"})
    balance = fetch_usdc_balance(
        "0x2222222222222222222222222222222222222222",
        rpc_url="https://rpc.local",
        opener=opener,
    )
    assert balance == Decimal("0")


def test_fetch_usdc_balance_rejects_malformed_address() -> None:
    with pytest.raises(AccountImportError, match="Wallet address"):
        fetch_usdc_balance("not-an-address")


def test_fetch_usdc_balance_raises_on_rpc_error_body() -> None:
    opener = RecordingOpener(
        {"jsonrpc": "2.0", "id": 1, "error": {"code": -32000, "message": "execution reverted"}}
    )
    with pytest.raises(PolygonRpcError, match="execution reverted"):
        fetch_usdc_balance(
            "0x3333333333333333333333333333333333333333",
            rpc_url="https://rpc.local",
            opener=opener,
        )


def test_fetch_usdc_balance_raises_on_unexpected_result_shape() -> None:
    opener = RecordingOpener({"jsonrpc": "2.0", "id": 1, "result": 12345})
    with pytest.raises(PolygonRpcError, match="result shape"):
        fetch_usdc_balance(
            "0x4444444444444444444444444444444444444444",
            rpc_url="https://rpc.local",
            opener=opener,
        )


def test_fetch_usdc_balance_wraps_http_error() -> None:
    def raising_opener(request, timeout):
        raise HTTPError(request.full_url, 503, "Service Unavailable", {}, None)

    with pytest.raises(PolygonRpcError, match="HTTP 503"):
        fetch_usdc_balance(
            "0x5555555555555555555555555555555555555555",
            rpc_url="https://rpc.local",
            opener=raising_opener,
        )


def test_fetch_usdc_balance_wraps_url_error() -> None:
    def raising_opener(request, timeout):
        raise URLError("name resolution failed")

    with pytest.raises(PolygonRpcError, match="Unable to reach"):
        fetch_usdc_balance(
            "0x6666666666666666666666666666666666666666",
            rpc_url="https://rpc.local",
            opener=raising_opener,
        )


def test_balance_of_calldata_pads_address_to_32_bytes() -> None:
    calldata = _balance_of_calldata("0x1111111111111111111111111111111111111111")
    assert calldata.startswith("0x70a08231")
    # 4-byte selector + "0x" prefix + 24 hex chars of zero padding + 40 hex chars of address.
    assert calldata == "0x70a08231" + "0" * 24 + "1" * 40
    assert len(calldata) == 2 + 8 + 64


def test_balance_of_calldata_handles_mixed_case_address() -> None:
    mixed = "0xAaBbCcDdEeFf00112233445566778899AaBbCcDd"
    calldata = _balance_of_calldata(mixed)
    assert calldata.endswith(mixed.lower().removeprefix("0x"))


def test_write_usdc_balance_writes_sibling_json(tmp_path) -> None:
    opener = RecordingOpener({"jsonrpc": "2.0", "id": 1, "result": hex(2_500_000)})
    output = tmp_path / "account" / "usdc_balance.json"
    wallet = "0x7777777777777777777777777777777777777777"
    frozen = datetime(2026, 5, 11, 12, 0, 0, tzinfo=timezone.utc)

    path = write_usdc_balance(
        wallet,
        output,
        rpc_url="https://rpc.local",
        opener=opener,
        now=frozen,
    )

    assert path == output
    data = json.loads(output.read_text(encoding="utf-8"))
    assert data["source"] == "polygon_rpc_usdc_balance"
    assert data["wallet_address"] == wallet
    assert data["rpc_url"] == "https://rpc.local"
    assert data["token_contract"] == USDC_E_CONTRACT
    assert Decimal(data["balance_usdc"]) == Decimal("2.5")
    assert data["as_of"] == frozen.isoformat()
