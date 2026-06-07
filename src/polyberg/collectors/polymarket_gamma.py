"""Read-only Polymarket Gamma / CLOB research collector.

This module is intentionally limited to public, unauthenticated research data.
It does not place orders, cancel orders, authenticate wallets, sign messages, or
drive a browser.
"""

from __future__ import annotations

import json

from polyberg.collectors.polymarket_account import (
    AccountImportError,
    ReadOnlyHttpClient,
)

CLOB_API_BASE_URL = "https://clob.polymarket.com"
GAMMA_API_BASE_URL = "https://gamma-api.polymarket.com"
USER_AGENT = "polyberg/0.1 (+https://github.com/mcleblanc711/polyberg)"

_GAMMA_HEADERS = {"User-Agent": USER_AGENT, "Accept": "application/json"}


class GammaCollectorError(RuntimeError):
    pass


def fetch_event_by_slug(slug: str, http: ReadOnlyHttpClient | None = None) -> dict:
    """Fetch a single Polymarket Gamma event by its slug.

    The Gamma ``/events`` endpoint returns a list; we take the first match.
    Raises :class:`GammaCollectorError` if the slug resolves to nothing.
    """
    if not slug:
        raise GammaCollectorError("Missing slug for Gamma event fetch")
    client = http or ReadOnlyHttpClient(GAMMA_API_BASE_URL)
    try:
        raw = client.get_json("/events", params={"slug": slug}, headers=_GAMMA_HEADERS)
    except AccountImportError as exc:
        raise GammaCollectorError(str(exc)) from exc
    if not isinstance(raw, list) or not raw:
        raise GammaCollectorError(f"No Gamma event found for slug {slug!r}")
    event = raw[0]
    if not isinstance(event, dict):
        raise GammaCollectorError(f"Unexpected Gamma event shape for slug {slug!r}")
    return event


def fetch_market_by_slug(slug: str, http: ReadOnlyHttpClient | None = None) -> dict:
    """Fetch a single Polymarket Gamma market by its slug."""
    if not slug:
        raise GammaCollectorError("Missing slug for Gamma market fetch")
    client = http or ReadOnlyHttpClient(GAMMA_API_BASE_URL)
    try:
        raw = client.get_json("/markets", params={"slug": slug}, headers=_GAMMA_HEADERS)
    except AccountImportError as exc:
        raise GammaCollectorError(str(exc)) from exc
    if not isinstance(raw, list) or not raw:
        raise GammaCollectorError(f"No Gamma market found for slug {slug!r}")
    market = raw[0]
    if not isinstance(market, dict):
        raise GammaCollectorError(f"Unexpected Gamma market shape for slug {slug!r}")
    return market


def _parse_json_array(value: object) -> list | None:
    """Gamma returns ``clobTokenIds``/``outcomes`` as JSON-encoded strings."""
    if isinstance(value, list):
        return value
    if isinstance(value, str) and value.strip():
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            return None
        return parsed if isinstance(parsed, list) else None
    return None


def _date_part(value: object) -> str | None:
    if isinstance(value, str) and value:
        return value.split("T")[0]
    return None


def normalize_gamma_market(raw: dict) -> dict:
    """Map a Gamma market dict to registry-ready identifier fields.

    Token IDs are matched to outcomes by label ("Yes"/"No") so we don't rely on
    positional order; falls back to positional [yes, no] if labels aren't the
    binary pair.
    """
    tokens = _parse_json_array(raw.get("clobTokenIds")) or []
    outcomes = _parse_json_array(raw.get("outcomes")) or []
    yes_token: str | None = None
    no_token: str | None = None
    for idx, label in enumerate(outcomes):
        if idx >= len(tokens):
            break
        normalized = str(label).strip().lower()
        if normalized == "yes":
            yes_token = str(tokens[idx])
        elif normalized == "no":
            no_token = str(tokens[idx])
    if yes_token is None and no_token is None and len(tokens) >= 2:
        yes_token, no_token = str(tokens[0]), str(tokens[1])
    return {
        "question": raw.get("question") or raw.get("title"),
        "market_slug": raw.get("slug"),
        "condition_id": raw.get("conditionId"),
        "yes_token_id": yes_token,
        "no_token_id": no_token,
        "outcomes": outcomes,
        "resolution_date": _date_part(raw.get("endDate")),
    }


def normalize_gamma_event(event: dict) -> dict:
    """Map a Gamma event into an event-level header plus normalized markets."""
    event_slug = event.get("slug")
    title = event.get("title")
    markets_raw = event.get("markets") or []
    markets: list[dict] = []
    for market in markets_raw:
        if not isinstance(market, dict):
            continue
        normalized = normalize_gamma_market(market)
        if normalized["resolution_date"] is None:
            normalized["resolution_date"] = _date_part(event.get("endDate"))
        if not normalized["question"]:
            normalized["question"] = title
        markets.append(normalized)
    return {
        "event_slug": event_slug,
        "name": title,
        "polymarket_url": f"https://polymarket.com/event/{event_slug}" if event_slug else None,
        "markets": markets,
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
