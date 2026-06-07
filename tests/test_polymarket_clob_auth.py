from __future__ import annotations

import base64
import hashlib
import hmac

import pytest

from polyberg.collectors.polymarket_account import AccountImportError
from polyberg.collectors.polymarket_clob_auth import (
    POLY_ADDRESS_HEADER,
    POLY_API_KEY_HEADER,
    POLY_PASSPHRASE_HEADER,
    POLY_SIGNATURE_HEADER,
    POLY_TIMESTAMP_HEADER,
    ClobCredentials,
    build_hmac_signature,
    build_level_2_headers,
    load_clob_credentials_from_env,
)

# Deterministic test secret: 32 bytes of 0x01, base64url-encoded.
TEST_SECRET = base64.urlsafe_b64encode(b"\x01" * 32).decode("ascii")
TEST_WALLET = "0x1111111111111111111111111111111111111111"


def _creds() -> ClobCredentials:
    return ClobCredentials(
        address=TEST_WALLET,
        api_key="test-key",
        api_secret=TEST_SECRET,
        api_passphrase="test-passphrase",
    )


def test_build_hmac_signature_matches_manual_computation() -> None:
    # Compute the expected signature using the canonical py-clob-client algorithm.
    timestamp = 1700000000
    method = "GET"
    path = "/data/orders"
    expected_secret = base64.urlsafe_b64decode(TEST_SECRET)
    expected_message = f"{timestamp}{method}{path}".encode()
    expected_digest = hmac.new(expected_secret, expected_message, hashlib.sha256).digest()
    expected = base64.urlsafe_b64encode(expected_digest).decode("utf-8")

    actual = build_hmac_signature(TEST_SECRET, timestamp, method, path)

    assert actual == expected


def test_build_hmac_signature_includes_body_with_single_quote_substitution() -> None:
    # The reference client coerces single quotes to double quotes inside the
    # body before signing so Python dict reprs and JS JSON.stringify outputs
    # agree on the byte stream.
    timestamp = 1700000000
    body_python_repr = "{'foo': 'bar'}"
    body_json_normalized = '{"foo": "bar"}'

    sig_from_repr = build_hmac_signature(
        TEST_SECRET, timestamp, "GET", "/some/path", body_python_repr
    )
    sig_from_json = build_hmac_signature(
        TEST_SECRET, timestamp, "GET", "/some/path", body_json_normalized
    )

    assert sig_from_repr == sig_from_json


def test_build_hmac_signature_rejects_invalid_secret() -> None:
    with pytest.raises(AccountImportError, match="base64url"):
        build_hmac_signature("!!!not valid base64!!!", 1700000000, "GET", "/data/orders")


def test_build_level_2_headers_returns_all_five_with_frozen_clock() -> None:
    headers = build_level_2_headers(
        _creds(),
        method="GET",
        request_path="/data/orders",
        timestamp_seconds=lambda: 1700000000,
    )
    assert set(headers) == {
        POLY_ADDRESS_HEADER,
        POLY_SIGNATURE_HEADER,
        POLY_TIMESTAMP_HEADER,
        POLY_API_KEY_HEADER,
        POLY_PASSPHRASE_HEADER,
    }
    assert headers[POLY_ADDRESS_HEADER] == TEST_WALLET
    assert headers[POLY_TIMESTAMP_HEADER] == "1700000000"
    assert headers[POLY_API_KEY_HEADER] == "test-key"
    assert headers[POLY_PASSPHRASE_HEADER] == "test-passphrase"
    assert headers[POLY_SIGNATURE_HEADER] == build_hmac_signature(
        TEST_SECRET, 1700000000, "GET", "/data/orders"
    )


def test_build_level_2_headers_uppercases_method_before_signing() -> None:
    upper = build_level_2_headers(
        _creds(), method="GET", request_path="/x", timestamp_seconds=lambda: 1
    )
    lower = build_level_2_headers(
        _creds(), method="get", request_path="/x", timestamp_seconds=lambda: 1
    )
    assert upper[POLY_SIGNATURE_HEADER] == lower[POLY_SIGNATURE_HEADER]


def test_build_level_2_headers_rejects_non_get() -> None:
    with pytest.raises(AccountImportError, match="GET"):
        build_level_2_headers(_creds(), method="POST", request_path="/data/orders")


def test_clob_credentials_validates_wallet_address() -> None:
    with pytest.raises(AccountImportError, match="Wallet address"):
        ClobCredentials(
            address="not-an-address",
            api_key="k",
            api_secret=TEST_SECRET,
            api_passphrase="p",
        )


def test_clob_credentials_rejects_empty_fields() -> None:
    with pytest.raises(AccountImportError, match="api_key"):
        ClobCredentials(
            address=TEST_WALLET, api_key="", api_secret=TEST_SECRET, api_passphrase="p"
        )


def test_load_clob_credentials_from_env_happy_path() -> None:
    creds = load_clob_credentials_from_env(
        env={
            "POLYMARKET_CLOB_SIGNER_ADDRESS": TEST_WALLET,
            "POLYMARKET_CLOB_API_KEY": "k",
            "POLYMARKET_CLOB_SECRET": TEST_SECRET,
            "POLYMARKET_CLOB_PASSPHRASE": "p",
        }
    )
    assert creds.address == TEST_WALLET
    assert creds.api_key == "k"


def test_load_clob_credentials_from_env_lists_every_missing_var() -> None:
    with pytest.raises(AccountImportError) as exc:
        load_clob_credentials_from_env(env={})
    msg = str(exc.value)
    for name in (
        "POLYMARKET_CLOB_SIGNER_ADDRESS",
        "POLYMARKET_CLOB_API_KEY",
        "POLYMARKET_CLOB_SECRET",
        "POLYMARKET_CLOB_PASSPHRASE",
    ):
        assert name in msg
