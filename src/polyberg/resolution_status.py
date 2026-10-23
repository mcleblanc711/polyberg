"""Per-market oracle resolution status.

Reads the live UMA / CTF resolution state for every registry market with a
``condition_id`` (Data API v2 ``/resolutions``) and writes one
``live/resolution_status.json`` artifact. Each entry carries a forward-only
``suggested_lifecycle`` (see :func:`polyberg.lifecycle.suggest_lifecycle_from_oracle`)
that the GUI offers to apply; nothing here edits the registry.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Iterable
from datetime import datetime
from pathlib import Path
from typing import Any

from polyberg.collectors.polymarket_data_v2 import fetch_resolutions
from polyberg.config import get_timezone, repo_path
from polyberg.lifecycle import suggest_lifecycle_from_oracle
from polyberg.loaders import load_market_registry

ResolutionFetcher = Callable[[Iterable[str]], dict[str, dict[str, Any]]]


def build_resolution_status_artifact(
    output_path: Path,
    registry_path: Path | None = None,
    fetcher: ResolutionFetcher | None = None,
    now: datetime | None = None,
) -> Path:
    """Write the resolution-status artifact. Returns the output path.

    ``fetcher`` lets tests inject deterministic rows; production code leaves it
    None to hit the real Data API. Transport errors propagate as
    :class:`~polyberg.collectors.polymarket_data_v2.DataApiV2Error`.
    """
    registry = load_market_registry(registry_path)
    if now is None:
        now = datetime.now(get_timezone())
    fetch = fetcher or (lambda condition_ids: fetch_resolutions(condition_ids))

    with_condition = [m for m in registry.markets if m.condition_id]
    rows = fetch([m.condition_id for m in with_condition]) if with_condition else {}

    markets_out: dict[str, dict[str, Any]] = {}
    skipped: list[dict[str, str]] = [
        {"market_id": m.market_id, "reason": "missing condition_id"}
        for m in registry.markets
        if not m.condition_id
    ]
    for market in with_condition:
        row = rows.get(market.condition_id.lower())
        if row is None:
            skipped.append({"market_id": market.market_id, "reason": "no resolution row"})
            continue
        markets_out[market.market_id] = {
            "condition_id": market.condition_id,
            "lifecycle": market.lifecycle,
            **row,
            "suggested_lifecycle": suggest_lifecycle_from_oracle(
                market.lifecycle, row["oracle_status"]
            ),
        }

    payload = {
        "as_of": now.isoformat(),
        "markets": markets_out,
        "skipped": skipped,
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return output_path


def default_resolution_status_path() -> Path:
    return repo_path("live", "resolution_status.json")
