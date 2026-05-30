from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from polyberg.collectors.polymarket_account import ReadOnlyHttpClient
from polyberg.collectors.polymarket_clob import (
    ClobCollectorError,
    fetch_midpoint,
    fetch_order_book,
)
from polyberg.config import get_timezone, windows_safe_timestamp
from polyberg.loaders import LoaderError, load_market_registry
from polyberg.models import MarketSnapshot, MarketSnapshotEntry


def build_market_snapshot(
    output_path: Path,
    registry_path: Path | None = None,
    now: datetime | None = None,
    http: ReadOnlyHttpClient | None = None,
) -> Path:
    registry = load_market_registry(registry_path)
    if now is None:
        now = datetime.now(get_timezone())
    elif now.tzinfo is None or now.utcoffset() is None:
        now = now.replace(tzinfo=get_timezone())

    entries = []
    for market in registry.markets:
        missing_info: list[str] = []
        if not market.yes_token_id:
            missing_info.append("missing yes_token_id")
        if not market.no_token_id:
            missing_info.append("missing no_token_id")

        if missing_info:
            entries.append(
                MarketSnapshotEntry(
                    market_id=market.market_id,
                    liquidity_warning=True,
                    missing_info=missing_info,
                )
            )
            continue

        yes_price: float | None = None
        no_price: float | None = None
        best_bid_yes: float | None = None
        best_ask_yes: float | None = None
        best_bid_no: float | None = None
        best_ask_no: float | None = None
        spread: float | None = None
        orderbook_depth_top: float | None = None

        try:
            mid = fetch_midpoint(market.yes_token_id, http=http)
            yes_price = _safe_float(mid.get("mid"))
        except ClobCollectorError as exc:
            missing_info.append(f"yes midpoint: {exc}")

        try:
            mid_no = fetch_midpoint(market.no_token_id, http=http)
            no_price = _safe_float(mid_no.get("mid"))
        except ClobCollectorError as exc:
            if yes_price is not None:
                no_price = round(1.0 - yes_price, 6)
            else:
                missing_info.append(f"no midpoint: {exc}")

        try:
            book = fetch_order_book(market.yes_token_id, http=http)
            best_bid_yes = _book_best_bid(book)
            best_ask_yes = _book_best_ask(book)
            orderbook_depth_top = _book_top_depth(book)
            if best_bid_yes is not None and best_ask_yes is not None:
                spread = round(best_ask_yes - best_bid_yes, 6)
                best_bid_no = round(1.0 - best_ask_yes, 6)
                best_ask_no = round(1.0 - best_bid_yes, 6)
        except ClobCollectorError as exc:
            missing_info.append(f"order book: {exc}")

        entries.append(
            MarketSnapshotEntry(
                market_id=market.market_id,
                yes_price=yes_price,
                no_price=no_price,
                best_bid_yes=best_bid_yes,
                best_ask_yes=best_ask_yes,
                best_bid_no=best_bid_no,
                best_ask_no=best_ask_no,
                spread=spread,
                orderbook_depth_top=orderbook_depth_top,
                liquidity_warning=bool(missing_info),
                missing_info=missing_info,
            )
        )

    snapshot = MarketSnapshot(as_of=now, markets=entries)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(snapshot.model_dump_json(indent=2), encoding="utf-8")
    return output_path


def _safe_float(val: object) -> float | None:
    try:
        return float(val)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None


def _book_best_bid(book: dict) -> float | None:
    bids = book.get("bids", [])
    if not bids:
        return None
    try:
        return float(bids[0]["price"])
    except (KeyError, ValueError, TypeError):
        return None


def _book_best_ask(book: dict) -> float | None:
    asks = book.get("asks", [])
    if not asks:
        return None
    try:
        return float(asks[0]["price"])
    except (KeyError, ValueError, TypeError):
        return None


def _book_top_depth(book: dict) -> float | None:
    bids = book.get("bids", [])
    asks = book.get("asks", [])
    try:
        bid_size = float(bids[0]["size"]) if bids else 0.0
        ask_size = float(asks[0]["size"]) if asks else 0.0
        return bid_size + ask_size
    except (KeyError, ValueError, TypeError):
        return None


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
