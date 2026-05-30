"""Read-only Polymarket CLOB research collector.

This module is intentionally limited to public, unauthenticated research data.
It does not create orders, cancel orders, authenticate wallets, use private keys,
sign messages, or drive a browser.
"""

from __future__ import annotations

from polyberg.collectors.polymarket_account import (
    AccountImportError,
    ReadOnlyHttpClient,
)

CLOB_API_BASE_URL = "https://clob.polymarket.com"
USER_AGENT = "polyberg/0.1 (+https://github.com/mcleblanc711/polyberg)"

_HEADERS = {"User-Agent": USER_AGENT, "Accept": "application/json"}


class ClobCollectorError(RuntimeError):
    pass


def fetch_order_book(token_id: str, http: ReadOnlyHttpClient | None = None) -> dict:
    if not token_id:
        raise ClobCollectorError("Missing token_id for order book fetch")
    client = http or ReadOnlyHttpClient(CLOB_API_BASE_URL)
    try:
        raw = client.get_json("/book", params={"token_id": token_id}, headers=_HEADERS)
    except AccountImportError as exc:
        raise ClobCollectorError(str(exc)) from exc
    if not isinstance(raw, dict):
        raise ClobCollectorError(
            f"Unexpected order book response shape (not an object) for token {token_id}"
        )
    return normalize_order_book(raw)


def fetch_midpoint(token_id: str, http: ReadOnlyHttpClient | None = None) -> dict:
    if not token_id:
        raise ClobCollectorError("Missing token_id for midpoint fetch")
    client = http or ReadOnlyHttpClient(CLOB_API_BASE_URL)
    try:
        raw = client.get_json("/midpoint", params={"token_id": token_id}, headers=_HEADERS)
    except AccountImportError as exc:
        raise ClobCollectorError(str(exc)) from exc
    if not isinstance(raw, dict) or "mid" not in raw:
        raise ClobCollectorError(
            f"Unexpected midpoint response shape for token {token_id}: {raw!r}"
        )
    return raw


def fetch_spread(token_id: str, http: ReadOnlyHttpClient | None = None) -> dict:
    if not token_id:
        raise ClobCollectorError("Missing token_id for spread fetch")
    client = http or ReadOnlyHttpClient(CLOB_API_BASE_URL)
    try:
        raw = client.get_json("/spread", params={"token_id": token_id}, headers=_HEADERS)
    except AccountImportError as exc:
        raise ClobCollectorError(str(exc)) from exc
    if not isinstance(raw, dict) or "spread" not in raw:
        raise ClobCollectorError(
            f"Unexpected spread response shape for token {token_id}: {raw!r}"
        )
    return raw


def normalize_order_book(raw: dict) -> dict:
    return {
        "bids": raw.get("bids", []),
        "asks": raw.get("asks", []),
        "asset_id": raw.get("asset_id") or raw.get("token_id"),
    }
