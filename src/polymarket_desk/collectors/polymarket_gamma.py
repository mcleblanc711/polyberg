"""Read-only Polymarket Gamma research collector.

This module is intentionally limited to public, unauthenticated research data.
It does not place orders, cancel orders, authenticate wallets, sign messages, or
drive a browser.
"""

from __future__ import annotations


def fetch_event_by_slug(slug: str) -> dict:
    raise NotImplementedError(
        f"Read-only Gamma event fetch is not implemented yet for slug {slug!r}."
    )


def fetch_market_by_slug(slug: str) -> dict:
    raise NotImplementedError(
        f"Read-only Gamma market fetch is not implemented yet for slug {slug!r}."
    )


def normalize_gamma_market(raw: dict) -> dict:
    return {
        "market_id": raw.get("id") or raw.get("conditionId"),
        "question": raw.get("question") or raw.get("title"),
        "slug": raw.get("slug"),
        "condition_id": raw.get("conditionId"),
        "tokens": raw.get("tokens") or raw.get("outcomes"),
    }
