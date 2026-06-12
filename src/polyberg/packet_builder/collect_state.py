from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from polyberg.config import get_timezone, repo_path
from polyberg.loaders import (
    context_path,
    load_live_state,
    load_market_registry,
    load_market_snapshot,
    load_open_orders,
    load_portfolio,
    read_text_file,
)
from polyberg.models import (
    LiveState,
    MarketRegistry,
    MarketSnapshot,
    OpenOrders,
    Portfolio,
)


@dataclass(frozen=True)
class PacketState:
    """Raw, validated factual state shared by every packet renderer.

    This is the single collection point for local files. Model-specific packets
    (GPT, Claude) and the legacy packet all derive from the same PacketState so
    the factual data never forks — only formatting does.
    """

    now: datetime
    registry: MarketRegistry
    live_state: LiveState
    portfolio: Portfolio
    open_orders: OpenOrders
    snapshot: MarketSnapshot | None
    catalysts_markdown: str
    # live/order_books.{json,md} from `polyberg fetch-books`; None when not run.
    order_books: dict | None = None
    order_books_markdown: str | None = None


def load_order_books(books_dir: Path | None = None) -> tuple[dict | None, str | None]:
    """Read live order book artifacts if `polyberg fetch-books` has produced them.

    Missing or malformed files are not an error — the packet simply reports
    that no live books are available.
    """
    directory = books_dir or repo_path("live")
    books_json: dict | None = None
    books_md: str | None = None
    try:
        parsed = json.loads((directory / "order_books.json").read_text(encoding="utf-8"))
        if isinstance(parsed, dict):
            books_json = parsed
    except (OSError, json.JSONDecodeError):
        pass
    try:
        books_md = (directory / "order_books.md").read_text(encoding="utf-8")
    except OSError:
        pass
    return books_json, books_md


def collect_packet_state(
    now: datetime | None = None,
    context_dir: Path | None = None,
    snapshot_path: Path | None = None,
    books_dir: Path | None = None,
) -> PacketState:
    registry = load_market_registry(context_path(context_dir, "market_registry.yaml"))
    live_state = load_live_state(context_path(context_dir, "live_state.yaml"), registry=registry)
    portfolio = load_portfolio(
        context_path(context_dir, "portfolio_current.yaml"),
        registry=registry,
    )
    open_orders = load_open_orders(
        context_path(context_dir, "open_orders.yaml"), registry=registry
    )
    snapshot = load_market_snapshot(snapshot_path) if snapshot_path else None
    catalysts_markdown = read_text_file(context_path(context_dir, "recent_catalysts.md"))
    # Books default to the repo live/ dir only for default-context builds;
    # custom context_dir callers (tests, sandboxes) must opt in via books_dir
    # so they stay hermetic.
    if books_dir is not None or context_dir is None:
        order_books, order_books_markdown = load_order_books(books_dir)
    else:
        order_books, order_books_markdown = None, None

    if now is None:
        now = datetime.now(get_timezone())

    return PacketState(
        now=now,
        registry=registry,
        live_state=live_state,
        portfolio=portfolio,
        open_orders=open_orders,
        snapshot=snapshot,
        catalysts_markdown=catalysts_markdown,
        order_books=order_books,
        order_books_markdown=order_books_markdown,
    )
