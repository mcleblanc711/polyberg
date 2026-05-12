"""Read-only Polymarket CLOB user-orders fetcher (L2-authenticated).

Wraps the CLOB's ``GET /data/orders`` endpoint with the L2 HMAC scheme so
polyberg can pull the wallet's open orders without holding a private key.
The pre-minted (api_key, api_secret, api_passphrase) triple plus the wallet
address are the only inputs; the user mints these out-of-band (e.g. with
``py-clob-client``'s ``create_or_derive_api_creds`` on a trusted machine)
and drops them into ``.env``.

Polyberg never signs anything except GETs against this endpoint — there is
no order-placement, cancellation, or modification path in this module.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from typing import Any

from polyberg.collectors.polymarket_account import (
    AccountImportError,
    ReadOnlyHttpClient,
)
from polyberg.collectors.polymarket_clob_auth import (
    CLOB_API_BASE_URL,
    END_CURSOR,
    START_CURSOR,
    ClobCredentials,
    build_level_2_headers,
)
from polyberg.config import get_timezone

ORDERS_PATH = "/data/orders"
USER_AGENT = "polyberg/0.1 (+https://github.com/mcleblanc711/polyberg)"


def fetch_open_orders(
    creds: ClobCredentials,
    market: str | None = None,
    asset_id: str | None = None,
    order_id: str | None = None,
    http: ReadOnlyHttpClient | None = None,
    timestamp_seconds: Callable[[], int] | None = None,
    max_pages: int = 50,
) -> list[dict[str, Any]]:
    """Fetch all open orders for the wallet behind ``creds``.

    Paginates by ``next_cursor`` until the CLOB returns the ``END_CURSOR``
    sentinel. ``max_pages`` is a safety stop in case a buggy server never
    sentinels — at 200 orders/page that's already an order of magnitude
    above any realistic single-wallet portfolio.
    """
    client = http or ReadOnlyHttpClient(CLOB_API_BASE_URL)
    accumulator: list[dict[str, Any]] = []
    cursor = START_CURSOR
    # py-clob-client signs the bare path once and reuses the same headers
    # across every paginated page — the cursor lives only in the query
    # string and isn't bound to the signature. Match that behavior so a
    # captured request is byte-identical to what the reference client
    # would emit.
    headers = build_level_2_headers(
        creds,
        method="GET",
        request_path=ORDERS_PATH,
        timestamp_seconds=timestamp_seconds,
    )
    headers["User-Agent"] = USER_AGENT
    headers["Accept"] = "application/json"
    for _ in range(max_pages):
        params: dict[str, Any] = {"next_cursor": cursor}
        if market:
            params["market"] = market
        if asset_id:
            params["asset_id"] = asset_id
        if order_id:
            params["id"] = order_id
        raw = client.get_json(ORDERS_PATH, params=params, headers=headers)
        if not isinstance(raw, dict):
            raise AccountImportError(
                f"Unexpected /data/orders response shape (not an object): {type(raw).__name__}"
            )
        data = raw.get("data", [])
        if not isinstance(data, list):
            raise AccountImportError(
                "Unexpected /data/orders response: 'data' field is not a list"
            )
        accumulator.extend(d for d in data if isinstance(d, dict))
        next_cursor = raw.get("next_cursor")
        if not isinstance(next_cursor, str) or next_cursor == END_CURSOR:
            return accumulator
        cursor = next_cursor
    raise AccountImportError(
        f"CLOB /data/orders did not paginate to end after {max_pages} pages — "
        "aborting to avoid runaway"
    )


def write_clob_open_orders(
    creds: ClobCredentials,
    output_path: Path,
    http: ReadOnlyHttpClient | None = None,
    timestamp_seconds: Callable[[], int] | None = None,
    now: datetime | None = None,
) -> Path:
    """Fetch every open order and write the raw payload to ``output_path``.

    Mirrors the shape produced by
    :func:`polyberg.collectors.polymarket_account.write_public_positions`
    so the GUI's account-import reader can pick it up via the same
    ``payload``-keyed JSON convention.
    """
    payload = fetch_open_orders(
        creds, http=http, timestamp_seconds=timestamp_seconds
    )
    if now is None:
        now = datetime.now(get_timezone())
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(
            {
                "as_of": now.isoformat(),
                "source": "polymarket_clob_open_orders",
                "wallet_address": creds.address,
                "payload": payload,
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    return output_path
