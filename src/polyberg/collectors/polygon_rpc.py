"""Read-only Polygon RPC client for on-chain USDC balance lookups.

Used to populate ``cash_available`` in the canonical Portfolio when the
unauthenticated data-api positions importer can't provide it. Hits a public
Polygon RPC with ``eth_call`` to USDC.e's ``balanceOf(address)`` and converts
the returned uint256 to a Decimal in dollars.

No private keys, no signing, no mutations. The JSON-RPC contract used here
needs POST, so the GET-only :class:`ReadOnlyHttpClient` is not reused;
instead this module hand-rolls a minimal POST helper.
"""

from __future__ import annotations

import json
import os
from collections.abc import Callable
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from polyberg.collectors.polymarket_account import validate_wallet_address
from polyberg.config import get_timezone

DEFAULT_POLYGON_RPC_URL = "https://polygon.drpc.org"
# USDC.e (bridged) on Polygon — the token Polymarket proxy wallets hold.
USDC_E_CONTRACT = "0x2791Bca1f2de4661ED88A30C99A7a9449Aa84174"
USDC_DECIMALS = 6
USER_AGENT = "polyberg/0.1 (+https://github.com/mcleblanc711/polyberg)"

JsonOpener = Callable[..., Any]


class PolygonRpcError(RuntimeError):
    pass


def fetch_usdc_balance(
    wallet_address: str,
    rpc_url: str | None = None,
    opener: JsonOpener = urlopen,
    timeout: float = 30.0,
) -> Decimal:
    """Return the USDC.e balance of ``wallet_address`` on Polygon, in dollars.

    Calls ``balanceOf(address)`` on the USDC.e contract via JSON-RPC
    ``eth_call``. Returns a :class:`Decimal` so cent-level precision is
    preserved end-to-end. Raises :class:`PolygonRpcError` on network,
    protocol, or shape errors.
    """
    validate_wallet_address(wallet_address)
    url = rpc_url or os.environ.get("POLYGON_RPC_URL", DEFAULT_POLYGON_RPC_URL)
    calldata = _balance_of_calldata(wallet_address)
    request_body = {
        "jsonrpc": "2.0",
        "method": "eth_call",
        "params": [
            {"to": USDC_E_CONTRACT, "data": calldata},
            "latest",
        ],
        "id": 1,
    }
    request = Request(
        url,
        data=json.dumps(request_body).encode("utf-8"),
        headers={
            "User-Agent": USER_AGENT,
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
        method="POST",
    )
    try:
        with opener(request, timeout=timeout) as response:
            raw = response.read()
    except HTTPError as exc:
        raise PolygonRpcError(f"HTTP {exc.code} from Polygon RPC at {url}") from exc
    except URLError as exc:
        raise PolygonRpcError(f"Unable to reach Polygon RPC at {url}: {exc.reason}") from exc

    try:
        body = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise PolygonRpcError(f"Invalid JSON response from Polygon RPC at {url}") from exc

    if not isinstance(body, dict):
        raise PolygonRpcError(f"Unexpected JSON-RPC response shape from {url}")
    if "error" in body and body["error"] is not None:
        err = body["error"]
        message = err.get("message", "unknown") if isinstance(err, dict) else str(err)
        raise PolygonRpcError(f"Polygon RPC error: {message}")
    result = body.get("result")
    if not isinstance(result, str) or not result.startswith("0x"):
        raise PolygonRpcError(f"Unexpected eth_call result shape from {url}: {result!r}")
    return _hex_to_usdc(result)


def _balance_of_calldata(wallet_address: str) -> str:
    """ABI-encode a ``balanceOf(address)`` call.

    Selector ``0x70a08231`` is the first four bytes of
    ``keccak256("balanceOf(address)")``; the argument is the address padded
    to 32 bytes left-zero-padded.
    """
    address_hex = wallet_address.lower().removeprefix("0x")
    return "0x70a08231" + address_hex.rjust(64, "0")


def _hex_to_usdc(result: str) -> Decimal:
    raw_int = int(result, 16)
    return Decimal(raw_int) / (Decimal(10) ** USDC_DECIMALS)


def write_usdc_balance(
    wallet_address: str,
    output_path: Path,
    rpc_url: str | None = None,
    opener: JsonOpener = urlopen,
    now: datetime | None = None,
) -> Path:
    """Fetch the wallet's USDC.e balance and write a sibling JSON artifact.

    Mirrors :func:`polyberg.collectors.polymarket_account.write_public_positions`
    so the GUI's account import flow can drop both files into the same directory
    on a single run.
    """
    balance = fetch_usdc_balance(wallet_address, rpc_url=rpc_url, opener=opener)
    resolved_url = rpc_url or os.environ.get("POLYGON_RPC_URL", DEFAULT_POLYGON_RPC_URL)
    if now is None:
        now = datetime.now(get_timezone())
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(
            {
                "as_of": now.isoformat(),
                "source": "polygon_rpc_usdc_balance",
                "wallet_address": wallet_address,
                "rpc_url": resolved_url,
                "token_contract": USDC_E_CONTRACT,
                "balance_usdc": str(balance),
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    return output_path
