"""Read-only Polymarket geoblock check.

``GET https://polymarket.com/api/geoblock`` reports whether Polymarket accepts
orders from the requesting IP, plus the country and region it geolocates to.
Polymarket's docs ask builders to check it before any trading. This module is
GET-only: it does not create orders, cancel orders, authenticate, sign
messages, or drive a browser.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from polyberg.collectors.polymarket_account import (
    AccountImportError,
    ReadOnlyHttpClient,
)
from polyberg.config import get_timezone, repo_path

# The check lives on the main website, not the API hosts.
POLYMARKET_WEB_BASE_URL = "https://polymarket.com"
GEOBLOCK_PATH = "/api/geoblock"
USER_AGENT = "polyberg/0.1 (+https://github.com/mcleblanc711/polyberg)"

_HEADERS = {"User-Agent": USER_AGENT, "Accept": "application/json"}


class GeoblockError(RuntimeError):
    pass


def fetch_geoblock(http: ReadOnlyHttpClient | None = None) -> dict[str, Any]:
    """Return ``{"blocked", "country", "region"}`` for this machine's public IP.

    The response's ``ip`` field is deliberately dropped: the flag only needs
    the location, and the artifact should not record the address.
    """
    client = http or ReadOnlyHttpClient(POLYMARKET_WEB_BASE_URL)
    try:
        raw = client.get_json(GEOBLOCK_PATH, headers=_HEADERS)
    except AccountImportError as exc:
        raise GeoblockError(str(exc)) from exc
    if not isinstance(raw, dict) or not isinstance(raw.get("blocked"), bool):
        raise GeoblockError(f"Unexpected geoblock response shape: {raw!r}"[:300])
    return {
        "blocked": raw["blocked"],
        "country": str(raw.get("country") or "").upper(),
        "region": str(raw.get("region") or "").upper(),
    }


def write_geo_status(
    output_path: Path,
    http: ReadOnlyHttpClient | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Run the geoblock check and write it as JSON. Returns the payload."""
    if now is None:
        now = datetime.now(get_timezone())
    payload = {
        "as_of": now.isoformat(),
        "source": POLYMARKET_WEB_BASE_URL + GEOBLOCK_PATH,
        **fetch_geoblock(http),
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return payload


def default_geo_status_path() -> Path:
    return repo_path("live", "geo_status.json")
