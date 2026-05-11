"""Read-only Polymarket Gamma / CLOB research collector.

This module is intentionally limited to public, unauthenticated research data.
It does not place orders, cancel orders, authenticate wallets, sign messages, or
drive a browser.
"""

from __future__ import annotations

from polyberg.collectors.polymarket_account import (
    AccountImportError,
    ReadOnlyHttpClient,
)

CLOB_API_BASE_URL = "https://clob.polymarket.com"
USER_AGENT = "polyberg/0.1 (+https://github.com/mcleblanc711/polyberg)"


class GammaCollectorError(RuntimeError):
    pass


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


def fetch_price_history(
    token_id: str,
    interval: str = "1m",
    fidelity: int = 60,
    http: ReadOnlyHttpClient | None = None,
) -> list[dict]:
    """Fetch a Polymarket CLOB price-history series for a single token.

    Returns a list of ``{"t": unix_seconds, "p": mark}`` dicts in ascending
    timestamp order, as the upstream API returns them. Empty list if the API
    returns no data.

    Raises :class:`GammaCollectorError` on transport or shape errors.
    """
    if not token_id:
        raise GammaCollectorError("Missing CLOB token_id for price-history fetch")
    client = http or ReadOnlyHttpClient(CLOB_API_BASE_URL)
    try:
        raw = client.get_json(
            "/prices-history",
            params={"market": token_id, "interval": interval, "fidelity": fidelity},
            headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
        )
    except AccountImportError as exc:
        raise GammaCollectorError(str(exc)) from exc
    if not isinstance(raw, dict):
        raise GammaCollectorError(
            f"Unexpected price-history response shape (not an object) for token {token_id}"
        )
    history = raw.get("history", [])
    if not isinstance(history, list):
        raise GammaCollectorError(
            f"Unexpected price-history.history shape (not a list) for token {token_id}"
        )
    cleaned: list[dict] = []
    for point in history:
        if not isinstance(point, dict):
            continue
        t = point.get("t")
        p = point.get("p")
        if not isinstance(t, (int, float)) or not isinstance(p, (int, float)):
            continue
        cleaned.append({"t": int(t), "p": float(p)})
    return cleaned
