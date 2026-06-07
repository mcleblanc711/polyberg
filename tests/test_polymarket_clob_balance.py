from __future__ import annotations

import base64
import json
from datetime import UTC, datetime
from decimal import Decimal
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
from polyberg.collectors.polymarket_clob_balance import (
    BALANCE_ALLOWANCE_PATH,
    DEFAULT_SIGNATURE_TYPE,
    balance_to_decimal_usdc,
    fetch_collateral_balance,
    write_clob_balance,
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


def test_fetch_collateral_balance_returns_payload() -> None:
    opener = ScriptedOpener(
        [{"balance": "25986514", "allowances": {"0xabc": "1000000"}}]
    )
    http = _make_http(opener)

    payload = fetch_collateral_balance(
        _creds(), http=http, timestamp_seconds=lambda: 1700000000
    )

    assert payload["balance"] == "25986514"
    assert payload["allowances"] == {"0xabc": "1000000"}


def test_fetch_collateral_balance_default_signature_type_is_one() -> None:
    opener = ScriptedOpener([{"balance": "0", "allowances": {}}])
    http = _make_http(opener)

    fetch_collateral_balance(
        _creds(), http=http, timestamp_seconds=lambda: 1700000000, env={}
    )

    url = opener.urls[0]
    assert "asset_type=COLLATERAL" in url
    assert f"signature_type={DEFAULT_SIGNATURE_TYPE}" in url


def test_fetch_collateral_balance_signature_type_env_override() -> None:
    opener = ScriptedOpener([{"balance": "0", "allowances": {}}])
    http = _make_http(opener)

    fetch_collateral_balance(
        _creds(),
        http=http,
        timestamp_seconds=lambda: 1700000000,
        env={"POLYMARKET_CLOB_SIGNATURE_TYPE": "2"},
    )

    assert "signature_type=2" in opener.urls[0]


def test_fetch_collateral_balance_explicit_signature_type_wins() -> None:
    opener = ScriptedOpener([{"balance": "0", "allowances": {}}])
    http = _make_http(opener)

    fetch_collateral_balance(
        _creds(),
        signature_type=0,
        http=http,
        timestamp_seconds=lambda: 1700000000,
        env={"POLYMARKET_CLOB_SIGNATURE_TYPE": "2"},
    )

    assert "signature_type=0" in opener.urls[0]


def test_fetch_collateral_balance_signs_bare_path_only() -> None:
    opener = ScriptedOpener([{"balance": "0", "allowances": {}}])
    http = _make_http(opener)

    fetch_collateral_balance(
        _creds(), http=http, timestamp_seconds=lambda: 1700000000
    )

    headers = {k.lower(): v for k, v in opener.headers[0].items()}
    expected_sig = build_hmac_signature(
        TEST_SECRET, 1700000000, "GET", BALANCE_ALLOWANCE_PATH
    )
    assert headers["poly_signature"] == expected_sig
    assert headers["poly_address"] == TEST_WALLET


def test_fetch_collateral_balance_raises_on_non_dict_response() -> None:
    opener = ScriptedOpener([[1, 2, 3]])
    http = _make_http(opener)

    with pytest.raises(AccountImportError, match="not an object"):
        fetch_collateral_balance(
            _creds(), http=http, timestamp_seconds=lambda: 1700000000
        )


def test_fetch_collateral_balance_raises_when_balance_field_missing() -> None:
    opener = ScriptedOpener([{"allowances": {}}])
    http = _make_http(opener)

    with pytest.raises(AccountImportError, match="missing 'balance' field"):
        fetch_collateral_balance(
            _creds(), http=http, timestamp_seconds=lambda: 1700000000
        )


def test_fetch_collateral_balance_rejects_non_integer_env_signature_type() -> None:
    opener = ScriptedOpener([{"balance": "0", "allowances": {}}])
    http = _make_http(opener)

    with pytest.raises(AccountImportError, match="POLYMARKET_CLOB_SIGNATURE_TYPE"):
        fetch_collateral_balance(
            _creds(),
            http=http,
            timestamp_seconds=lambda: 1700000000,
            env={"POLYMARKET_CLOB_SIGNATURE_TYPE": "not-an-int"},
        )


def test_balance_to_decimal_usdc_converts_uint256_to_dollars() -> None:
    assert balance_to_decimal_usdc("25986514") == Decimal("25.986514")
    assert balance_to_decimal_usdc("0") == Decimal("0")
    assert balance_to_decimal_usdc("1000000") == Decimal("1")


def test_balance_to_decimal_usdc_rejects_non_numeric() -> None:
    with pytest.raises(AccountImportError, match="Invalid balance"):
        balance_to_decimal_usdc("not-a-number")


def test_write_clob_balance_writes_artifact(tmp_path: Path) -> None:
    opener = ScriptedOpener(
        [{"balance": "25986514", "allowances": {"0xabc": "1000000"}}]
    )
    http = _make_http(opener)
    output = tmp_path / "account" / "usdc_balance.json"
    frozen = datetime(2026, 5, 14, 12, 0, 0, tzinfo=UTC)

    path = write_clob_balance(
        _creds(),
        output,
        http=http,
        timestamp_seconds=lambda: 1700000000,
        now=frozen,
    )

    assert path == output
    doc = json.loads(output.read_text(encoding="utf-8"))
    assert doc["source"] == "polymarket_clob_balance_allowance"
    assert doc["wallet_address"] == TEST_WALLET
    assert doc["signature_type"] == DEFAULT_SIGNATURE_TYPE
    assert doc["balance_usdc"] == "25.986514"
    assert doc["as_of"] == frozen.isoformat()
    assert doc["raw"]["balance"] == "25986514"
    assert doc["raw"]["allowances"] == {"0xabc": "1000000"}
