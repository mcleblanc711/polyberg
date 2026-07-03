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

# Fields a human can change on an existing entry. The Gamma-sourced identifiers
# (condition_id, token IDs, resolution_date, event_slug, polymarket_url) and the
# market_id itself are locked — re-add the market to re-fetch those.
EDITABLE_FIELDS = (
    "name",
    "category",
    "thesis_bucket",
    "rule_key",
    "oracle_type",
    "preferred_side",
    "risk_flags",
    "notes",
)


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


def market_display_name(candidate: dict, market: dict) -> str:
    """Distinguishing registry name for one market within an event.

    A single-outcome event uses its title verbatim. A multi-bracket event
    (">25 ships", "26-50 ships", ...) shares one title across every bracket, so
    the title alone would label every entry identically and collide the
    auto-suggested ``market_id``. Qualify it with the per-bracket question.
    """
    event_title = (candidate.get("name") or "").strip()
    question = (market.get("question") or "").strip()
    multi = len(candidate.get("markets") or []) > 1
    if multi and question and question != event_title:
        return f"{event_title} — {question}" if event_title else question
    return event_title or question or ""


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
        name=market_display_name(candidate, market) or market_id,
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
        neg_risk=candidate.get("neg_risk"),
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


_MARKET_ID_KEY_RE = re.compile(r"^\s*-?\s*market_id:\s*['\"]?([a-z0-9_]+)['\"]?\s*$")


def _find_entry_span(lines: list[str], indent: int, market_id: str) -> tuple[int, int] | None:
    """Locate the ``[start, end)`` line span of the entry with ``market_id``.

    Item boundaries are the ``markets:`` list-dash lines at ``indent`` (nested
    list items like ``risk_flags`` sit deeper, so they never match). Each item's
    identity is its first ``market_id:`` key.
    """
    prefix = " " * indent + "- "
    starts = [i for i, ln in enumerate(lines) if ln.startswith(prefix)]
    for idx, start in enumerate(starts):
        end = starts[idx + 1] if idx + 1 < len(starts) else len(lines)
        for ln in lines[start:end]:
            match = _MARKET_ID_KEY_RE.match(ln)
            if not match:
                continue
            if match.group(1) == market_id:
                return (start, end)
            break  # this item's id isn't the target; move to the next item
    return None


def _load_registry(path: Path) -> tuple[str, MarketRegistry]:
    body = path.read_text(encoding="utf-8")
    return body, MarketRegistry(**(yaml.safe_load(body) or {}))


def get_editable_fields(market_id: str, path: Path | None = None) -> dict:
    """Return one entry's editable fields (plus locked identifiers for display).

    Powers the GUI edit modal's pre-fill via ``registry-update --preview``.
    """
    target = path or registry_path()
    _, registry = _load_registry(target)
    current = next((m for m in registry.markets if m.market_id == market_id), None)
    if current is None:
        raise RegistryEditError(f"market_id {market_id!r} not found in the registry")
    fields = {name: getattr(current, name) for name in EDITABLE_FIELDS}
    fields.update(
        market_id=current.market_id,
        condition_id=current.condition_id,
        polymarket_url=current.polymarket_url,
        resolution_date=current.resolution_date,
    )
    return fields


def update_market_entry(market_id: str, updates: dict, path: Path | None = None) -> Path:
    """Rewrite the editable fields of an existing entry in place.

    Only :data:`EDITABLE_FIELDS` may change; identifiers stay locked. The merged
    entry is re-validated through ``Market`` and the whole file re-parsed before
    anything is written, and only the target entry's text block is rewritten so
    the rest of the hand-maintained file is left byte-for-byte intact.
    """
    invalid = sorted(set(updates) - set(EDITABLE_FIELDS))
    if invalid:
        raise RegistryEditError(f"Fields are not editable: {', '.join(invalid)}")
    target = path or registry_path()
    body, registry = _load_registry(target)
    current = next((m for m in registry.markets if m.market_id == market_id), None)
    if current is None:
        raise RegistryEditError(f"market_id {market_id!r} not found in the registry")
    merged = Market(**{**current.model_dump(), **updates})  # re-validate (e.g. preferred_side)

    lines = body.splitlines(keepends=True)
    indent = _detect_list_indent(body)
    span = _find_entry_span(lines, indent, market_id)
    if span is None:
        raise RegistryEditError(f"Could not locate the text block for {market_id!r} to rewrite")
    start, end = span
    lines[start:end] = [_entry_to_yaml_block(merged, indent)]
    new_body = "".join(lines)
    MarketRegistry(**(yaml.safe_load(new_body) or {}))  # guard before write
    target.write_text(new_body, encoding="utf-8")
    return target


def delete_market_entry(market_id: str, path: Path | None = None) -> Path:
    """Remove an existing entry, leaving the rest of the file untouched."""
    target = path or registry_path()
    body, registry = _load_registry(target)
    if market_id not in registry.market_ids:
        raise RegistryEditError(f"market_id {market_id!r} not found in the registry")

    lines = body.splitlines(keepends=True)
    indent = _detect_list_indent(body)
    span = _find_entry_span(lines, indent, market_id)
    if span is None:
        raise RegistryEditError(f"Could not locate the text block for {market_id!r} to delete")
    start, end = span
    del lines[start:end]
    new_body = "".join(lines)
    # Removing the last entry leaves a bare "markets:" (parses to None, not []),
    # which fails MarketRegistry. Normalize to an explicit empty list.
    if (yaml.safe_load(new_body) or {}).get("markets") is None:
        new_body = "markets: []\n"
    MarketRegistry(**(yaml.safe_load(new_body) or {}))  # guard before write
    target.write_text(new_body, encoding="utf-8")
    return target
