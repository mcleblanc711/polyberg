"""Read-only Polymarket CLOB collateral-balance fetcher (L2-authenticated).

Wraps the CLOB's ``GET /balance-allowance`` endpoint with the L2 HMAC scheme
so polyberg can read the wallet's available collateral (USDC) without
holding a private key. The pre-minted (api_key, api_secret, api_passphrase)
triple plus the signer EOA are the only inputs.

This replaced an earlier on-chain ``balanceOf`` check against the Polymarket
proxy wallet — that check is structurally always zero for Polymarket users
because cash sits inside Polymarket's collateral pool, not at the proxy
address. ``/balance-allowance`` is the canonical source.

Polyberg never signs anything except GETs against this endpoint.

Signature type
--------------

Polymarket's funder address is derived from ``signer_address +
signature_type``. The default is ``1`` (POLY_PROXY — the standard
Polymarket-managed proxy). Override with ``POLYMARKET_CLOB_SIGNATURE_TYPE``
in the environment if your account uses a different proxy type:

    0 — EOA (the signer's own address; rare for trading accounts)
    1 — POLY_PROXY (Polymarket-managed proxy, EIP-1167 minimal proxy)
    2 — POLY_GNOSIS_SAFE (Gnosis-Safe-style proxy)

The wrong signature_type returns ``balance: "0"`` because the server looks
up funds at a different funder address — silently wrong, not an error.
"""

from __future__ import annotations

import json
import os
from collections.abc import Callable
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

from polyberg.collectors.polymarket_account import (
    AccountImportError,
    ReadOnlyHttpClient,
)
from polyberg.collectors.polymarket_clob_auth import (
    CLOB_API_BASE_URL,
    ClobCredentials,
    build_level_2_headers,
)
from polyberg.config import get_timezone

BALANCE_ALLOWANCE_PATH = "/balance-allowance"
COLLATERAL_ASSET_TYPE = "COLLATERAL"
DEFAULT_SIGNATURE_TYPE = 1
USDC_DECIMALS = 6
USER_AGENT = "polyberg/0.1 (+https://github.com/mcleblanc711/polyberg)"


def _resolve_signature_type(
    signature_type: int | None,
    env: dict[str, str] | None = None,
) -> int:
    if signature_type is not None:
        return int(signature_type)
    source = env if env is not None else os.environ
    raw = source.get("POLYMARKET_CLOB_SIGNATURE_TYPE")
    if raw is None or raw == "":
        return DEFAULT_SIGNATURE_TYPE
    try:
        return int(raw)
    except ValueError as exc:
        raise AccountImportError(
            f"POLYMARKET_CLOB_SIGNATURE_TYPE must be an integer, got {raw!r}"
        ) from exc


def fetch_collateral_balance(
    creds: ClobCredentials,
    signature_type: int | None = None,
    http: ReadOnlyHttpClient | None = None,
    timestamp_seconds: Callable[[], int] | None = None,
    env: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Fetch the wallet's COLLATERAL balance from the CLOB.

    Returns the raw response payload (``{"balance": "<uint256>", "allowances":
    {<addr>: "<uint256>", ...}}``). Use :func:`balance_to_decimal_usdc` to
    convert ``balance`` to dollars.
    """
    sig_type = _resolve_signature_type(signature_type, env=env)
    client = http or ReadOnlyHttpClient(CLOB_API_BASE_URL)
    headers = build_level_2_headers(
        creds,
        method="GET",
        request_path=BALANCE_ALLOWANCE_PATH,
        timestamp_seconds=timestamp_seconds,
    )
    headers["User-Agent"] = USER_AGENT
    headers["Accept"] = "application/json"
    raw = client.get_json(
        BALANCE_ALLOWANCE_PATH,
        params={
            "asset_type": COLLATERAL_ASSET_TYPE,
            "signature_type": sig_type,
        },
        headers=headers,
    )
    if not isinstance(raw, dict):
        raise AccountImportError(
            f"Unexpected /balance-allowance response shape (not an object): {type(raw).__name__}"
        )
    if "balance" not in raw:
        raise AccountImportError(
            "Unexpected /balance-allowance response: missing 'balance' field"
        )
    return raw


def balance_to_decimal_usdc(raw_balance: object) -> Decimal:
    """Convert a uint256 balance string to a USDC Decimal (6 decimals)."""
    try:
        as_int = int(str(raw_balance))
    except (TypeError, ValueError) as exc:
        raise AccountImportError(
            f"Invalid balance value from /balance-allowance: {raw_balance!r}"
        ) from exc
    return Decimal(as_int) / (Decimal(10) ** USDC_DECIMALS)


def write_clob_balance(
    creds: ClobCredentials,
    output_path: Path,
    signature_type: int | None = None,
    http: ReadOnlyHttpClient | None = None,
    timestamp_seconds: Callable[[], int] | None = None,
    now: datetime | None = None,
    env: dict[str, str] | None = None,
) -> Path:
    """Fetch the wallet's collateral balance and write a sibling JSON artifact.

    The output file uses the ``balance_usdc`` field name so
    :func:`polyberg.account_normalizer.read_usdc_balance` can read it
    transparently as the canonical cash source for ``promote-positions``.
    """
    sig_type = _resolve_signature_type(signature_type, env=env)
    payload = fetch_collateral_balance(
        creds,
        signature_type=sig_type,
        http=http,
        timestamp_seconds=timestamp_seconds,
    )
    balance_decimal = balance_to_decimal_usdc(payload["balance"])
    if now is None:
        now = datetime.now(get_timezone())
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(
            {
                "as_of": now.isoformat(),
                "source": "polymarket_clob_balance_allowance",
                "wallet_address": creds.address,
                "signature_type": sig_type,
                "balance_usdc": str(balance_decimal),
                "raw": payload,
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    return output_path
