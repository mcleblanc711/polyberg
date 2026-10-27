"""Public outcome price history: Data API v2 first, the CLOB series as fallback."""

from __future__ import annotations

from urllib.parse import urlencode

from polyberg.collectors.polymarket_gamma import GammaCollectorError, fetch_price_history
from polyberg.http import HttpReadError, ReadOnlyHttpClient
from polyberg.research.models import HistorySpan, PricePoint
from polyberg.research.public import CLOB, DATA, PublicDataError, price

# Grain-aligned buckets keep each span near 250–350 points; TTLs bound refetching.
SPANS: dict[str, tuple[int, int]] = {
    "1d": (300, 5 * 60),
    "1w": (1800, 30 * 60),
    "1m": (10800, 2 * 3600),
    "max": (43200, 12 * 3600),
}
MAX_PAGES = 20


def _pages(client: ReadOnlyHttpClient, params: dict) -> list:
    rows, page = [], dict(params)
    for _ in range(MAX_PAGES):
        raw = client.get_json("/v2/prices-history", params=page)
        if not isinstance(raw, dict) or not isinstance(raw.get("data"), list):
            raise PublicDataError("Malformed public price history")
        rows.extend(raw["data"])
        pagination = raw.get("pagination")
        cursor = pagination.get("next_cursor") if isinstance(pagination, dict) else None
        if not (isinstance(pagination, dict) and pagination.get("has_more") is True):
            return rows
        if not isinstance(cursor, str) or not cursor:
            return rows
        # v2 rejects a cursor sent without the original window parameters.
        page = {**params, "cursor": cursor}
    raise PublicDataError("Public price history exceeded the page limit")


def _points(rows: list, resolution: int | None = None) -> tuple[list[PricePoint], list[str]]:
    points, malformed = {}, False
    for row in rows:
        if not isinstance(row, dict):
            malformed = True
            continue
        t, p = row.get("timestamp", row.get("t")), price(row.get("price", row.get("p")))
        r = resolution if resolution is not None else row.get("resolution_seconds")
        if type(t) is not int or t < 0 or p is None or type(r) is not int or r < 0:
            malformed = True
            continue
        points[t] = PricePoint(t=t, p=p, r=r)
    warnings = ["Malformed price history points omitted"] if malformed else []
    return [points[t] for t in sorted(points)], warnings


def fetch_series(
    data: ReadOnlyHttpClient, clob: ReadOnlyHttpClient, asset_id: str, span: HistorySpan
) -> tuple[list[PricePoint], str, list[str]]:
    """Return (points, supplying URL, warnings) for one outcome asset.

    Both services are keyed by the asset the CLOB quotes use; for v1 markets that is the
    CTF token ID (verified live 2026-10-27). No v2-protocol market was listed then.
    """
    if span not in SPANS:
        raise ValueError("Unsupported price history span")
    bucket = SPANS[span][0]
    params = {"token_id": asset_id, "interval": span, "bucket_seconds": bucket}
    try:
        rows = _pages(data, params)
        if not rows:
            # An explicit bucket the store cannot fill is served empty; let the server choose.
            params.pop("bucket_seconds")
            rows = _pages(data, params)
        points, warnings = _points(rows)
        return points, f"{DATA}/v2/prices-history?{urlencode(params)}", warnings
    except (HttpReadError, PublicDataError, OSError, TimeoutError):
        pass
    fidelity = bucket // 60
    try:
        rows = fetch_price_history(asset_id, interval=span, fidelity=fidelity, http=clob)
    except (GammaCollectorError, HttpReadError, OSError, TimeoutError) as exc:
        raise PublicDataError("Public price history unavailable") from exc
    points, warnings = _points(rows, resolution=bucket)
    query = urlencode({"market": asset_id, "interval": span, "fidelity": fidelity})
    return points, f"{CLOB}/prices-history?{query}", warnings
