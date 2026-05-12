"""Polymarket CLOB Level-2 (HMAC) auth helpers — read-only.

The CLOB exposes per-user resources (open orders, fills, balances of L2 API
keys, etc.) behind an HMAC scheme. Per the official py-clob-client
implementation:

* Sign string: ``str(timestamp) + str(method) + str(request_path) + body?``
  where ``timestamp`` is Unix **seconds** (not ms) and ``body`` is appended
  only when non-empty (the python client also replaces single quotes with
  double quotes inside the body to match the JS serialization, which we
  preserve so signatures match what py-clob-client would generate).
* Secret: base64url-decoded before HMAC.
* Algorithm: HMAC-SHA256.
* Signature: base64url-encoded digest, no padding stripping.
* Headers: ``POLY_ADDRESS``, ``POLY_SIGNATURE``, ``POLY_TIMESTAMP``,
  ``POLY_API_KEY``, ``POLY_PASSPHRASE``.

Polyberg only ever uses these headers with GET requests — we read user-scoped
data via L2 auth but never sign anything that creates, cancels, or modifies
orders. The wallet's private key is **not** required at any point; only the
pre-minted (key, secret, passphrase) triple plus the wallet address.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import os
import time
from collections.abc import Callable
from dataclasses import dataclass

from polyberg.collectors.polymarket_account import (
    AccountImportError,
    validate_wallet_address,
)

CLOB_API_BASE_URL = "https://clob.polymarket.com"

POLY_ADDRESS_HEADER = "POLY_ADDRESS"
POLY_SIGNATURE_HEADER = "POLY_SIGNATURE"
POLY_TIMESTAMP_HEADER = "POLY_TIMESTAMP"
POLY_API_KEY_HEADER = "POLY_API_KEY"
POLY_PASSPHRASE_HEADER = "POLY_PASSPHRASE"

END_CURSOR = "LTE="
START_CURSOR = "MA=="


@dataclass(frozen=True)
class ClobCredentials:
    """The pre-minted L2 triple plus the EOA that signed for them.

    ``address`` is the **EOA / signer address** (the externally-owned account
    derived from the private key that signed the EIP-712 message to mint
    these credentials) — NOT the proxy wallet that holds funds. The CLOB
    registers the api_key against the EOA and rejects requests that send a
    mismatched ``POLY_ADDRESS`` header.

    Mint creds out-of-band using py-clob-client's
    ``create_or_derive_api_creds`` on a trusted machine, then paste the
    four values (api_key, secret, passphrase, signer EOA) into ``.env``.
    Polyberg never touches a private key.
    """

    address: str
    api_key: str
    api_secret: str
    api_passphrase: str

    def __post_init__(self) -> None:
        validate_wallet_address(self.address)
        for field_name in ("api_key", "api_secret", "api_passphrase"):
            value = getattr(self, field_name)
            if not isinstance(value, str) or not value:
                raise AccountImportError(f"Missing CLOB credential: {field_name}")


def load_clob_credentials_from_env(
    env: dict[str, str] | None = None,
) -> ClobCredentials:
    """Read the four required env vars and return a :class:`ClobCredentials`.

    The address loaded here is the **signer EOA** (the address derived from
    the private key that minted these creds), not the proxy wallet that
    holds funds. See :class:`ClobCredentials` for the why.

    Raises :class:`AccountImportError` listing every missing variable, so a
    user setting up creds for the first time sees the full picture at once
    instead of one error at a time.
    """
    source = env if env is not None else os.environ
    address = source.get("POLYMARKET_CLOB_SIGNER_ADDRESS", "")
    api_key = source.get("POLYMARKET_CLOB_API_KEY", "")
    api_secret = source.get("POLYMARKET_CLOB_SECRET", "")
    api_passphrase = source.get("POLYMARKET_CLOB_PASSPHRASE", "")
    missing = [
        name
        for name, value in (
            ("POLYMARKET_CLOB_SIGNER_ADDRESS", address),
            ("POLYMARKET_CLOB_API_KEY", api_key),
            ("POLYMARKET_CLOB_SECRET", api_secret),
            ("POLYMARKET_CLOB_PASSPHRASE", api_passphrase),
        )
        if not value
    ]
    if missing:
        raise AccountImportError(
            "Missing CLOB credentials in environment: " + ", ".join(missing)
        )
    return ClobCredentials(
        address=address,
        api_key=api_key,
        api_secret=api_secret,
        api_passphrase=api_passphrase,
    )


def build_hmac_signature(
    secret: str,
    timestamp: int,
    method: str,
    request_path: str,
    body: str | None = None,
) -> str:
    """Return the URL-safe base64 HMAC-SHA256 signature.

    Matches py-clob-client's ``build_hmac_signature`` exactly so signatures
    remain interchangeable with the reference client.
    """
    try:
        base64_secret = base64.urlsafe_b64decode(secret)
    except (ValueError, base64.binascii.Error) as exc:
        raise AccountImportError("Invalid CLOB api_secret (not valid base64url)") from exc
    message = f"{timestamp}{method}{request_path}"
    if body:
        message += body.replace("'", '"')
    digest = hmac.new(base64_secret, message.encode("utf-8"), hashlib.sha256).digest()
    return base64.urlsafe_b64encode(digest).decode("utf-8")


def build_level_2_headers(
    creds: ClobCredentials,
    method: str,
    request_path: str,
    body: str | None = None,
    timestamp_seconds: Callable[[], int] | None = None,
) -> dict[str, str]:
    """Return the five POLY_* headers for an L2-authenticated GET.

    ``timestamp_seconds`` lets tests inject a frozen clock for deterministic
    signature output.
    """
    if method.upper() != "GET":
        raise AccountImportError("CLOB L2 auth helper only signs GET requests")
    now_seconds = timestamp_seconds() if timestamp_seconds else int(time.time())
    signature = build_hmac_signature(
        creds.api_secret,
        now_seconds,
        method.upper(),
        request_path,
        body,
    )
    return {
        POLY_ADDRESS_HEADER: creds.address,
        POLY_SIGNATURE_HEADER: signature,
        POLY_TIMESTAMP_HEADER: str(now_seconds),
        POLY_API_KEY_HEADER: creds.api_key,
        POLY_PASSPHRASE_HEADER: creds.api_passphrase,
    }
