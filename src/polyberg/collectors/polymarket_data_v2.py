"""Read-only Polymarket Data API v2 research collector.

Data API v2 (``https://data-api.polymarket.com/v2``, launched 2026-09-04)
wraps every payload in a ``{"data": ...}`` envelope and pages with an opaque
``next_cursor``; v1 is frozen. This module is limited to public,
unauthenticated GET reads. It does not create orders, cancel orders,
authenticate wallets, sign messages, or drive a browser.
"""

from __future__ import annotations

from collections.abc import Iterable
from decimal import Decimal, InvalidOperation
from typing import Any

from polyberg.collectors.polymarket_account import (
    AccountImportError,
    ReadOnlyHttpClient,
)

DATA_API_V2_BASE_URL = "https://data-api.polymarket.com/v2"
USER_AGENT = "polyberg/0.1 (+https://github.com/mcleblanc711/polyberg)"

_HEADERS = {"User-Agent": USER_AGENT, "Accept": "application/json"}

# /v2/resolutions accepts at most 20 distinct comma-separated condition ids.
RESOLUTIONS_BATCH_SIZE = 20
# UMA's "no price yet" sentinel on proposed/settled price strings.
_UMA_UNSET_PRICE = Decimal(69)
# UMA YES_OR_NO prices are 18-decimal fixed point: 1e18 == YES, 0 == NO.
_UMA_SCALE = Decimal(10) ** 18


class DataApiV2Error(RuntimeError):
    pass


def _get(client: ReadOnlyHttpClient, path: str, params: dict[str, Any]) -> Any:
    try:
        return client.get_json(path, params=params, headers=_HEADERS)
    except AccountImportError as exc:
        raise DataApiV2Error(str(exc)) from exc


def _rows(raw: Any, path: str) -> list[dict[str, Any]]:
    """Unwrap the v2 ``{"data": [...]}`` envelope, dropping non-object rows."""
    if not isinstance(raw, dict):
        raise DataApiV2Error(
            f"Unexpected v2 {path} response shape (not an object): {type(raw).__name__}"
        )
    data = raw.get("data")
    if not isinstance(data, list):
        raise DataApiV2Error(f"Unexpected v2 {path} response: 'data' is not a list")
    return [row for row in data if isinstance(row, dict)]


def _get_all_pages(
    client: ReadOnlyHttpClient,
    path: str,
    params: dict[str, Any],
    max_pages: int,
) -> list[dict[str, Any]]:
    """Follow ``pagination.next_cursor`` until ``has_more`` is false.

    The cursor does not replace the query: v2 rejects a cursor-only request,
    so every page resends the original params alongside it.
    """
    rows: list[dict[str, Any]] = []
    page_params = dict(params)
    for _ in range(max_pages):
        raw = _get(client, path, page_params)
        rows.extend(_rows(raw, path))
        pagination = raw.get("pagination")
        if not isinstance(pagination, dict) or not pagination.get("has_more"):
            return rows
        cursor = pagination.get("next_cursor")
        if not isinstance(cursor, str) or not cursor:
            return rows
        page_params = {**params, "cursor": cursor}
    raise DataApiV2Error(
        f"v2 {path} did not paginate to end after {max_pages} pages — "
        "aborting to avoid runaway"
    )


def fetch_prices_history_v2(
    token_id: str,
    interval: str = "1m",
    bucket_seconds: int = 3600,
    http: ReadOnlyHttpClient | None = None,
    max_pages: int = 20,
) -> list[dict]:
    """Fetch a token's price series from ``GET /v2/prices-history``.

    Returns ``{"t": unix_seconds, "p": price}`` dicts oldest-first — the same
    contract as the CLOB-hosted route — so callers do not change. ``interval``
    uses the CLOB vocabulary (``1m`` is one month); ``bucket_seconds`` is
    served exactly as asked (60…86400).
    """
    if not token_id:
        raise DataApiV2Error("Missing CLOB token_id for v2 price-history fetch")
    client = http or ReadOnlyHttpClient(DATA_API_V2_BASE_URL)
    rows = _get_all_pages(
        client,
        "/prices-history",
        {"token_id": token_id, "interval": interval, "bucket_seconds": bucket_seconds},
        max_pages,
    )
    cleaned: list[dict] = []
    for row in rows:
        t = row.get("timestamp")
        p = row.get("price")
        if not isinstance(t, (int, float)) or not isinstance(p, (int, float)):
            continue
        cleaned.append({"t": int(t), "p": float(p)})
    return cleaned


def _uma_outcome(raw_price: Any) -> str | None:
    """Map a UMA price string to YES / NO / 50-50; None when unset or absent."""
    if raw_price is None or raw_price == "":
        return None
    try:
        value = Decimal(str(raw_price))
    except InvalidOperation:
        return None
    if value == _UMA_UNSET_PRICE:
        return None
    if value > 1:
        value = value / _UMA_SCALE
    if value == 1:
        return "YES"
    if value == 0:
        return "NO"
    if value == Decimal("0.5"):
        return "50-50"
    return f"{value:f}"


def _payout_outcome(payouts: Any) -> str | None:
    """``payouts`` is ``[outcome0, outcome1]`` micro-USDC per share (Yes, No)."""
    if not isinstance(payouts, list) or len(payouts) != 2:
        return None
    yes, no = payouts
    if not isinstance(yes, int) or not isinstance(no, int):
        return None
    if yes > no:
        return "YES"
    if no > yes:
        return "NO"
    return "50-50"


def normalize_resolution(row: dict[str, Any]) -> dict[str, Any]:
    status = str(row.get("status") or "unknown")
    settled = _payout_outcome(row.get("payouts"))
    if settled is None and status == "resolved":
        settled = _uma_outcome(row.get("price"))
    return {
        "oracle_status": status,
        "was_disputed": bool(row.get("was_disputed")),
        "extended_review": bool(row.get("extended_review")),
        "proposed_outcome": _uma_outcome(row.get("proposed_price")),
        "settled_outcome": settled,
        "resolved_at": row.get("resolved_at"),
        "expected_settlement_time": row.get("expected_settlement_time"),
    }


def fetch_resolutions(
    condition_ids: Iterable[str],
    http: ReadOnlyHttpClient | None = None,
) -> dict[str, dict[str, Any]]:
    """Fetch oracle resolution state from ``GET /v2/resolutions``.

    Returns normalized rows keyed by lowercased condition id. Conditions the
    API has no row for are simply absent. When a condition has several rows,
    the first wins: the API orders them native V2, then UMA, then CTF.
    """
    unique = list(dict.fromkeys(cid.lower() for cid in condition_ids if cid))
    client = http or ReadOnlyHttpClient(DATA_API_V2_BASE_URL)
    out: dict[str, dict[str, Any]] = {}
    for start in range(0, len(unique), RESOLUTIONS_BATCH_SIZE):
        batch = unique[start : start + RESOLUTIONS_BATCH_SIZE]
        raw = _get(client, "/resolutions", {"condition": ",".join(batch)})
        for row in _rows(raw, "/resolutions"):
            condition_id = str(row.get("condition_id") or "").lower()
            if condition_id and condition_id not in out:
                out[condition_id] = normalize_resolution(row)
    return out
