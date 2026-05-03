"""Read-only Polymarket CLOB research collector.

This module is intentionally limited to public, unauthenticated research data.
It does not create orders, cancel orders, authenticate wallets, use private keys,
sign messages, or drive a browser.
"""

from __future__ import annotations


def fetch_order_book(token_id: str) -> dict:
    raise NotImplementedError(
        f"Read-only CLOB order book fetch is not implemented yet for token {token_id!r}."
    )


def fetch_midpoint(token_id: str) -> dict:
    raise NotImplementedError(
        f"Read-only CLOB midpoint fetch is not implemented yet for token {token_id!r}."
    )


def fetch_spread(token_id: str) -> dict:
    raise NotImplementedError(
        f"Read-only CLOB spread fetch is not implemented yet for token {token_id!r}."
    )


def normalize_order_book(raw: dict) -> dict:
    return {
        "bids": raw.get("bids", []),
        "asks": raw.get("asks", []),
        "asset_id": raw.get("asset_id") or raw.get("token_id"),
    }
