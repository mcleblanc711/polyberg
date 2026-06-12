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
        "timestamp": raw.get("timestamp"),
        "last_trade_price": raw.get("last_trade_price"),
        "tick_size": raw.get("tick_size"),
        "min_order_size": raw.get("min_order_size"),
    }


def fetch_clob_market(condition_id: str, http: ReadOnlyHttpClient | None = None) -> dict:
    """Fetch a CLOB V2 market by condition_id; returns market dict with tokens list.

    Each token entry has at minimum ``token_id`` and ``outcome`` fields.  Use
    ``outcome_by_token_id`` to resolve a held token to its outcome label.

    Raises :class:`ClobCollectorError` on transport or unexpected shape.
    """
    if not condition_id:
        raise ClobCollectorError("Missing condition_id for CLOB market fetch")
    client = http or ReadOnlyHttpClient(CLOB_API_BASE_URL)
    try:
        raw = client.get_json(f"/markets/{condition_id}", headers=_HEADERS)
    except AccountImportError as exc:
        raise ClobCollectorError(str(exc)) from exc
    if not isinstance(raw, dict):
        raise ClobCollectorError(
            f"Unexpected CLOB market response shape for condition_id {condition_id}"
        )
    return raw


def outcome_by_token_id(market_data: dict, token_id: str) -> str | None:
    """Return the outcome label for a specific token_id within a CLOB market response.

    Returns None if the token is not found in the tokens list.
    """
    for token in market_data.get("tokens") or []:
        if not isinstance(token, dict):
            continue
        if str(token.get("token_id") or "") == str(token_id):
            outcome = token.get("outcome")
            return str(outcome) if outcome is not None else None
    return None
