"""Per-market price-history orchestration.

Fetches a one-month CLOB price series per registry market, derives 1d / 1w / 1m
high-low windows, and writes a single ``context/price_history.json`` artifact
the GUI's ``readContext()`` can splice onto each ``Market``.

This is the Option-2 (Gamma-direct) path. The artifact carries the full series
so a future Option-3 cache layer can reuse this same file as the on-disk source
of truth without a second fetch shape.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Callable

from polyberg.collectors.polymarket_gamma import (
    GammaCollectorError,
    fetch_price_history,
)
from polyberg.config import get_timezone
from polyberg.loaders import load_market_registry

WINDOWS_SECONDS: dict[str, int] = {
    "d1": 24 * 3600,
    "w1": 7 * 24 * 3600,
    "m1": 30 * 24 * 3600,
}

Fetcher = Callable[[str], list[dict]]


def _windows_from_series(series: list[dict], now_ts: int) -> dict[str, dict[str, float]]:
    windows: dict[str, dict[str, float]] = {}
    for key, span in WINDOWS_SECONDS.items():
        cutoff = now_ts - span
        prices = [point["p"] for point in series if point["t"] >= cutoff]
        if not prices:
            windows[key] = {"high": 0.0, "low": 0.0}
            continue
        windows[key] = {"high": max(prices), "low": min(prices)}
    return windows


def build_price_history_artifact(
    output_path: Path,
    registry_path: Path | None = None,
    fetcher: Fetcher | None = None,
    now: datetime | None = None,
) -> Path:
    """Write the price-history artifact. Returns the output path.

    ``fetcher`` lets tests inject a deterministic series source; production code
    leaves it None to hit the real CLOB endpoint.
    """
    registry = load_market_registry(registry_path)
    if now is None:
        now = datetime.now(get_timezone())
    now_ts = int(now.timestamp())
    fetch = fetcher or (lambda token_id: fetch_price_history(token_id))

    markets_out: dict[str, dict] = {}
    skipped: list[dict[str, str]] = []
    for market in registry.markets:
        token_id = market.yes_token_id or ""
        if not token_id:
            skipped.append({"market_id": market.market_id, "reason": "missing yes_token_id"})
            continue
        try:
            series = fetch(token_id)
        except GammaCollectorError as exc:
            skipped.append({"market_id": market.market_id, "reason": str(exc)})
            continue
        markets_out[market.market_id] = {
            "yes_token_id": token_id,
            "series": series,
            "windows": _windows_from_series(series, now_ts),
        }

    payload = {
        "as_of": now.isoformat(),
        "markets": markets_out,
        "skipped": skipped,
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return output_path


def default_price_history_path(context_dir: Path) -> Path:
    return context_dir / "price_history.json"
