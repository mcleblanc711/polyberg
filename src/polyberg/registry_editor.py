"""Add markets to ``context/market_registry.yaml`` from a Polymarket slug.

This is the engine behind the GUI "Add Market" flow and the ``registry-add``
CLI command. Polymarket Gamma auto-fills the *identifier* fields
(``condition_id``, the two token IDs, name, resolution date, event slug); the
caller supplies the *judgment* fields (``preferred_side``, ``rule_key``,
``oracle_type``, ``category``, ...) that require a human decision.

New entries are appended as a text block so existing registry formatting is left
untouched (a full load/dump round-trip would churn every line). Re-adding an
existing ``market_id`` is rejected — editing existing entries is out of scope.
"""

from __future__ import annotations

import re
from pathlib import Path

import yaml

from polyberg.collectors.polymarket_account import ReadOnlyHttpClient
from polyberg.collectors.polymarket_gamma import (
    GammaCollectorError,
    fetch_event_by_slug,
    normalize_gamma_event,
)
from polyberg.config import repo_path
from polyberg.models import DataCollection, Market, MarketRegistry

_EVENT_PATH_RE = re.compile(r"/(?:event|market)/([^/?#]+)")


class RegistryEditError(RuntimeError):
    pass


def slug_from_url(url_or_slug: str) -> str:
    """Accept a full Polymarket URL or a bare slug and return the slug."""
    value = (url_or_slug or "").strip()
    if not value:
        raise RegistryEditError("Empty Polymarket URL or slug")
    if "polymarket.com" in value or value.startswith("http"):
        match = _EVENT_PATH_RE.search(value)
        if not match:
            raise RegistryEditError(f"Could not extract an event slug from {url_or_slug!r}")
        return match.group(1)
    # Bare slug: tolerate an accidental trailing slash / query fragment.
    return value.split("?", 1)[0].rstrip("/")


def fetch_candidate(url_or_slug: str, http: ReadOnlyHttpClient | None = None) -> dict:
    """Return the normalized Gamma event (header + markets) for a URL/slug."""
    slug = slug_from_url(url_or_slug)
    try:
        event = fetch_event_by_slug(slug, http=http)
    except GammaCollectorError as exc:
        raise RegistryEditError(str(exc)) from exc
    normalized = normalize_gamma_event(event)
    if not normalized["markets"]:
        raise RegistryEditError(f"Gamma event {slug!r} has no tradable markets")
    return normalized


def suggest_market_id(name: str) -> str:
    """Derive a registry-legal market_id ([a-z0-9_]) suggestion from a name."""
    cleaned = re.sub(r"[^a-z0-9]+", "_", (name or "").lower()).strip("_")
    return cleaned or "new_market"


def select_market(candidate: dict, index: int = 0) -> dict:
    markets = candidate["markets"]
    if index < 0 or index >= len(markets):
        raise RegistryEditError(
            f"market index {index} out of range (event has {len(markets)} market(s))"
        )
    return markets[index]


def build_market(
    candidate: dict,
    *,
    market_id: str,
    category: str,
    rule_key: str,
    oracle_type: str,
    preferred_side: str,
    thesis_bucket: str = "",
    notes: str = "",
    risk_flags: list[str] | None = None,
    rule_risk: dict | None = None,
    market_index: int = 0,
) -> Market:
    """Merge auto-filled identifiers with caller-supplied judgment fields.

    Validation runs through the ``Market`` model, so a bad ``preferred_side`` or
    a malformed ``market_id`` fails here rather than producing a broken entry.
    """
    market = select_market(candidate, market_index)
    return Market(
        market_id=market_id,
        name=candidate["name"] or market.get("question") or market_id,
        polymarket_url=candidate["polymarket_url"] or "",
        category=category,
        thesis_bucket=thesis_bucket,
        rule_key=rule_key,
        oracle_type=oracle_type,
        preferred_side=preferred_side,  # type: ignore[arg-type]  # validated by model
        risk_flags=risk_flags or [],
        resolution_date=market["resolution_date"],  # type: ignore[arg-type]
        notes=notes,
        event_slug=candidate["event_slug"],
        condition_id=market["condition_id"],
        yes_token_id=market["yes_token_id"],
        no_token_id=market["no_token_id"],
        data_collection=DataCollection(
            fetch_gamma=True, fetch_clob=True, fetch_orderbook=True
        ),
        rule_risk=rule_risk,  # type: ignore[arg-type]  # validated by model
    )


def registry_path(context_dir: Path | None = None) -> Path:
    if context_dir is not None:
        return context_dir / "market_registry.yaml"
    return repo_path("context", "market_registry.yaml")


def _detect_list_indent(body: str, default: int = 2) -> int:
    """Find how far existing ``markets:`` list items are indented.

    The hand-maintained registry indents items two spaces; ``yaml.safe_dump``
    output indents them zero. Matching the existing file avoids a mixed-indent
    YAML parse error on append.
    """
    in_markets = False
    for line in body.splitlines():
        stripped = line.strip()
        if not in_markets:
            if stripped.startswith("markets:"):
                in_markets = True
            continue
        if stripped.startswith("- "):
            return len(line) - len(line.lstrip())
    return default


def _entry_to_yaml_block(entry: Market, indent: int) -> str:
    """Render one validated entry as a YAML list item at the given indent."""
    data = entry.model_dump(exclude_none=True)
    dumped = yaml.safe_dump([data], sort_keys=False, allow_unicode=True, default_flow_style=False)
    # safe_dump emits the item at column 0 ("- key:"); re-indent to match the file.
    pad = " " * indent
    return "".join(f"{pad}{line}\n" for line in dumped.splitlines())


def upsert_market_entry(entry: Market, path: Path | None = None) -> Path:
    """Append a new market entry, rejecting duplicate market_ids.

    Validates the resulting file by re-parsing it through ``MarketRegistry`` so a
    bad append is caught before it can break the packet builder.
    """
    target = path or registry_path()
    existing = MarketRegistry(**(yaml.safe_load(target.read_text(encoding="utf-8")) or {}))
    if entry.market_id in existing.market_ids:
        raise RegistryEditError(
            f"market_id {entry.market_id!r} already exists in the registry "
            "(editing existing entries is not supported yet)"
        )
    body = target.read_text(encoding="utf-8")
    if not body.endswith("\n"):
        body += "\n"
    body += _entry_to_yaml_block(entry, _detect_list_indent(body))
    # Re-parse before writing so a malformed append never lands on disk.
    MarketRegistry(**(yaml.safe_load(body) or {}))
    target.write_text(body, encoding="utf-8")
    return target
