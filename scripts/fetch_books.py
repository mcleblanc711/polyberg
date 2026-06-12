#!/usr/bin/env python3
"""Fetch live Polymarket CLOB order book depth for registry markets.

Thin wrapper around ``polyberg fetch-books`` so the fetcher can run without an
installed entry point: ``python scripts/fetch_books.py [--markets a,b] [--depth N]``.

Read-only: public GET endpoints only — no keys, no signing, no order placement.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from polyberg.cli import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main(["fetch-books", *sys.argv[1:]]))
