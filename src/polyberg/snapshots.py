from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from polyberg.config import get_timezone, windows_safe_timestamp
from polyberg.loaders import LoaderError, load_market_registry
from polyberg.models import MarketSnapshot, MarketSnapshotEntry


def build_market_snapshot(
    output_path: Path,
    registry_path: Path | None = None,
    now: datetime | None = None,
) -> Path:
    registry = load_market_registry(registry_path)
    if now is None:
        now = datetime.now(get_timezone())
    elif now.tzinfo is None or now.utcoffset() is None:
        now = now.replace(tzinfo=get_timezone())

    entries = []
    for market in registry.markets:
        missing_info = []
        if not market.event_slug:
            missing_info.append("missing event_slug")
        if not market.yes_token_id:
            missing_info.append("missing yes_token_id")
        if not market.no_token_id:
            missing_info.append("missing no_token_id")
        entries.append(
            MarketSnapshotEntry(
                market_id=market.market_id,
                yes_price=None,
                no_price=None,
                best_bid_yes=None,
                best_ask_yes=None,
                best_bid_no=None,
                best_ask_no=None,
                spread=None,
                orderbook_depth_top=None,
                liquidity_warning=bool(missing_info),
                missing_info=missing_info or ["read-only collector not implemented"],
            )
        )
    snapshot = MarketSnapshot(as_of=now, markets=entries)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(snapshot.model_dump_json(indent=2), encoding="utf-8")
    return output_path


def default_snapshot_path(directory: Path) -> Path:
    return directory / f"markets_{windows_safe_timestamp()}.json"


def load_snapshot_json(path: Path) -> MarketSnapshot:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise LoaderError(f"Unable to read snapshot {path}: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise LoaderError(f"Invalid JSON in snapshot {path}: {exc}") from exc
    try:
        return MarketSnapshot.model_validate(data)
    except ValidationError as exc:
        raise LoaderError(f"Validation failed for {path}:\n{exc}") from exc


def diff_snapshots(old_path: Path, new_path: Path) -> str:
    old = load_snapshot_json(old_path)
    new = load_snapshot_json(new_path)
    old_by_id = {market.market_id: market for market in old.markets}
    new_by_id = {market.market_id: market for market in new.markets}
    lines = [
        "# Market Snapshot Diff",
        f"- Old: {old.as_of.isoformat()}",
        f"- New: {new.as_of.isoformat()}",
    ]

    removed = sorted(set(old_by_id) - set(new_by_id))
    added = sorted(set(new_by_id) - set(old_by_id))
    if added:
        lines.append("- Markets added: " + ", ".join(added))
    if removed:
        lines.append("- Markets removed: " + ", ".join(removed))

    lines.extend(["", "| Market | Changes |", "| --- | --- |"])
    for market_id in sorted(set(old_by_id) & set(new_by_id)):
        changes = compare_market_snapshot(
            old_by_id[market_id].model_dump(),
            new_by_id[market_id].model_dump(),
        )
        summary = "; ".join(changes) if changes else "no material changes"
        lines.append(f"| {market_id} | {summary} |")
    return "\n".join(lines) + "\n"


def compare_market_snapshot(old: dict[str, Any], new: dict[str, Any]) -> list[str]:
    changes = []
    for field in ["yes_price", "no_price", "spread"]:
        if old.get(field) != new.get(field):
            changes.append(f"{field}: {old.get(field)} -> {new.get(field)}")
    if old.get("liquidity_warning") != new.get("liquidity_warning"):
        changes.append(
            f"liquidity_warning: {old.get('liquidity_warning')} -> {new.get('liquidity_warning')}"
        )
    if sorted(old.get("missing_info", [])) != sorted(new.get("missing_info", [])):
        changes.append("missing_info changed")
    return changes
