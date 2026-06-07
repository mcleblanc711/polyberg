from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from polyberg.collectors.polymarket_account import AccountImportError
from polyberg.collectors.polymarket_clob import (
    CLOB_API_BASE_URL,
    ClobCollectorError,
    fetch_midpoint,
    fetch_order_book,
    fetch_spread,
    normalize_order_book,
)
from polyberg.snapshots import (
    _book_best_ask,
    _book_best_bid,
    _book_top_depth,
    build_market_snapshot,
)

# ---------------------------------------------------------------------------
# Fake HTTP infrastructure (mirrors test_price_history.py pattern)
# ---------------------------------------------------------------------------


class FakeResponse:
    def __init__(self, payload: object) -> None:
        self.payload = payload

    def __enter__(self) -> FakeResponse:
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def read(self) -> bytes:
        return json.dumps(self.payload).encode("utf-8")


class RecordingOpener:
    """Returns a fixed payload for every request and records URLs called."""

    def __init__(self, payload: object) -> None:
        self.payload = payload
        self.urls: list[str] = []

    def __call__(self, request, timeout: float):
        self.urls.append(request.full_url)
        return FakeResponse(self.payload)


class PerPathOpener:
    """Returns different payloads keyed by URL path prefix."""

    def __init__(self, routes: dict[str, object]) -> None:
        self.routes = routes  # e.g. {"/midpoint": {...}, "/book": {...}}
        self.urls: list[str] = []

    def __call__(self, request, timeout: float):
        self.urls.append(request.full_url)
        for path, payload in self.routes.items():
            if path in request.full_url:
                return FakeResponse(payload)
        raise AccountImportError(f"No route for {request.full_url}")


# ---------------------------------------------------------------------------
# fetch_midpoint
# ---------------------------------------------------------------------------


def test_fetch_midpoint_returns_mid() -> None:
    opener = RecordingOpener({"mid": "0.52"})
    from polyberg.collectors.polymarket_account import ReadOnlyHttpClient

    client = ReadOnlyHttpClient(CLOB_API_BASE_URL, opener=opener)
    result = fetch_midpoint("tok-yes", http=client)
    assert result == {"mid": "0.52"}
    assert "/midpoint" in opener.urls[0]
    assert "token_id=tok-yes" in opener.urls[0]


def test_fetch_midpoint_rejects_blank_token() -> None:
    with pytest.raises(ClobCollectorError, match="token_id"):
        fetch_midpoint("")


def test_fetch_midpoint_rejects_missing_mid_key() -> None:
    from polyberg.collectors.polymarket_account import ReadOnlyHttpClient

    client = ReadOnlyHttpClient(CLOB_API_BASE_URL, opener=RecordingOpener({"other": 1}))
    with pytest.raises(ClobCollectorError, match="midpoint response shape"):
        fetch_midpoint("tok-yes", http=client)


def test_fetch_midpoint_wraps_http_error() -> None:
    class BoomClient:
        def get_json(self, *_a, **_kw):
            raise AccountImportError("HTTP 503")

    with pytest.raises(ClobCollectorError, match="HTTP 503"):
        fetch_midpoint("tok-yes", http=BoomClient())  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# fetch_spread
# ---------------------------------------------------------------------------


def test_fetch_spread_returns_spread() -> None:
    from polyberg.collectors.polymarket_account import ReadOnlyHttpClient

    opener = RecordingOpener({"spread": "0.04"})
    client = ReadOnlyHttpClient(CLOB_API_BASE_URL, opener=opener)
    result = fetch_spread("tok-yes", http=client)
    assert result == {"spread": "0.04"}
    assert "/spread" in opener.urls[0]


def test_fetch_spread_rejects_blank_token() -> None:
    with pytest.raises(ClobCollectorError, match="token_id"):
        fetch_spread("")


# ---------------------------------------------------------------------------
# fetch_order_book
# ---------------------------------------------------------------------------

_SAMPLE_BOOK = {
    "bids": [{"price": "0.50", "size": "200"}, {"price": "0.48", "size": "100"}],
    "asks": [{"price": "0.54", "size": "150"}, {"price": "0.56", "size": "80"}],
}


def test_fetch_order_book_normalizes_response() -> None:
    from polyberg.collectors.polymarket_account import ReadOnlyHttpClient

    opener = RecordingOpener(_SAMPLE_BOOK)
    client = ReadOnlyHttpClient(CLOB_API_BASE_URL, opener=opener)
    book = fetch_order_book("tok-yes", http=client)
    assert book["bids"] == _SAMPLE_BOOK["bids"]
    assert book["asks"] == _SAMPLE_BOOK["asks"]
    assert "/book" in opener.urls[0]
    assert "token_id=tok-yes" in opener.urls[0]


def test_fetch_order_book_rejects_blank_token() -> None:
    with pytest.raises(ClobCollectorError, match="token_id"):
        fetch_order_book("")


def test_fetch_order_book_rejects_non_dict() -> None:
    from polyberg.collectors.polymarket_account import ReadOnlyHttpClient

    client = ReadOnlyHttpClient(CLOB_API_BASE_URL, opener=RecordingOpener([]))
    with pytest.raises(ClobCollectorError, match="not an object"):
        fetch_order_book("tok-yes", http=client)


# ---------------------------------------------------------------------------
# normalize_order_book
# ---------------------------------------------------------------------------


def test_normalize_order_book_picks_asset_id() -> None:
    raw = {"bids": [], "asks": [], "asset_id": "abc"}
    assert normalize_order_book(raw)["asset_id"] == "abc"


def test_normalize_order_book_falls_back_to_token_id() -> None:
    raw = {"bids": [], "asks": [], "token_id": "tok-fallback"}
    assert normalize_order_book(raw)["asset_id"] == "tok-fallback"


# ---------------------------------------------------------------------------
# Order-book helper functions
# ---------------------------------------------------------------------------


def test_book_best_bid_and_ask() -> None:
    book = normalize_order_book(_SAMPLE_BOOK)
    assert _book_best_bid(book) == pytest.approx(0.50)
    assert _book_best_ask(book) == pytest.approx(0.54)


def test_book_top_depth_sums_top_sizes() -> None:
    book = normalize_order_book(_SAMPLE_BOOK)
    assert _book_top_depth(book) == pytest.approx(350.0)  # 200 + 150


def test_book_helpers_return_none_on_empty_book() -> None:
    empty = {"bids": [], "asks": []}
    assert _book_best_bid(empty) is None
    assert _book_best_ask(empty) is None
    assert _book_top_depth(empty) == pytest.approx(0.0)


# ---------------------------------------------------------------------------
# build_market_snapshot integration
# ---------------------------------------------------------------------------

_MIDPOINT_YES = {"mid": 0.52}
_MIDPOINT_NO = {"mid": 0.48}
_BOOK_RESPONSE = {
    "bids": [{"price": "0.50", "size": "200"}],
    "asks": [{"price": "0.54", "size": "150"}],
}


def _registry_yaml(entries: list[dict]) -> str:
    lines = ["markets:"]
    for e in entries:
        yes_tok = e.get("yes_token_id", "tok-yes")
        no_tok = e.get("no_token_id", "tok-no")
        lines.extend(
            [
                f"  - market_id: {e['market_id']}",
                f"    name: {e['market_id']}",
                "    polymarket_url: https://example.invalid",
                "    category: test",
                "    rule_key: test",
                "    oracle_type: pure_data",
                '    preferred_side: "YES"',
                "    risk_flags: []",
                "    resolution_date: 2027-01-01",
                '    notes: ""',
                f'    yes_token_id: "{yes_tok}"',
                f'    no_token_id: "{no_tok}"',
            ]
        )
    return "\n".join(lines) + "\n"


def test_build_market_snapshot_happy_path(tmp_path: Path) -> None:
    reg = tmp_path / "registry.yaml"
    reg.write_text(
        _registry_yaml([{"market_id": "test_market"}]), encoding="utf-8"
    )

    routes = {
        "/midpoint": _MIDPOINT_YES,  # same response for both yes and no tokens
        "/book": _BOOK_RESPONSE,
    }
    from polyberg.collectors.polymarket_account import ReadOnlyHttpClient

    opener = PerPathOpener(routes)
    client = ReadOnlyHttpClient(CLOB_API_BASE_URL, opener=opener)

    out = tmp_path / "snap.json"
    build_market_snapshot(out, registry_path=reg, now=datetime(2026, 1, 1, tzinfo=UTC), http=client)

    payload = json.loads(out.read_text())
    markets = {m["market_id"]: m for m in payload["markets"]}
    m = markets["test_market"]

    assert m["yes_price"] == pytest.approx(0.52)
    assert m["best_bid_yes"] == pytest.approx(0.50)
    assert m["best_ask_yes"] == pytest.approx(0.54)
    assert m["spread"] == pytest.approx(0.04)
    assert m["best_bid_no"] == pytest.approx(0.46)   # 1 - 0.54
    assert m["best_ask_no"] == pytest.approx(0.50)   # 1 - 0.50
    assert m["orderbook_depth_top"] == pytest.approx(350.0)
    assert m["liquidity_warning"] is False
    assert m["missing_info"] == []


def test_build_market_snapshot_missing_token_ids(tmp_path: Path) -> None:
    reg = tmp_path / "registry.yaml"
    reg.write_text(
        _registry_yaml([{"market_id": "no_token_market", "yes_token_id": "", "no_token_id": ""}]),
        encoding="utf-8",
    )
    out = tmp_path / "snap.json"
    build_market_snapshot(out, registry_path=reg, now=datetime(2026, 1, 1, tzinfo=UTC))

    payload = json.loads(out.read_text())
    m = payload["markets"][0]
    assert m["yes_price"] is None
    assert m["liquidity_warning"] is True
    assert "missing yes_token_id" in m["missing_info"]


def test_build_market_snapshot_midpoint_failure_falls_back(tmp_path: Path) -> None:
    """Yes-midpoint failure but order book OK: prices stay None, book fields populate."""
    reg = tmp_path / "registry.yaml"
    reg.write_text(_registry_yaml([{"market_id": "flaky_mid"}]), encoding="utf-8")

    call_count = 0

    class FlakyMidClient:
        def get_json(self, path: str, **_kw):
            nonlocal call_count
            call_count += 1
            if "/midpoint" in path:
                raise AccountImportError("HTTP 429")
            return _BOOK_RESPONSE

    out = tmp_path / "snap.json"
    build_market_snapshot(
        out,
        registry_path=reg,
        now=datetime(2026, 1, 1, tzinfo=UTC),
        http=FlakyMidClient(),  # type: ignore[arg-type]
    )

    payload = json.loads(out.read_text())
    m = payload["markets"][0]
    assert m["yes_price"] is None
    assert m["best_bid_yes"] == pytest.approx(0.50)
    assert m["liquidity_warning"] is True
    assert any("midpoint" in msg for msg in m["missing_info"])


def test_build_market_snapshot_order_book_failure(tmp_path: Path) -> None:
    reg = tmp_path / "registry.yaml"
    reg.write_text(_registry_yaml([{"market_id": "no_book"}]), encoding="utf-8")

    class NoBookClient:
        def get_json(self, path: str, **_kw):
            if "/book" in path:
                raise AccountImportError("HTTP 404")
            return _MIDPOINT_YES

    out = tmp_path / "snap.json"
    build_market_snapshot(
        out,
        registry_path=reg,
        now=datetime(2026, 1, 1, tzinfo=UTC),
        http=NoBookClient(),  # type: ignore[arg-type]
    )

    payload = json.loads(out.read_text())
    m = payload["markets"][0]
    assert m["yes_price"] == pytest.approx(0.52)
    assert m["best_bid_yes"] is None
    assert m["spread"] is None
    assert m["liquidity_warning"] is True
    assert any("order book" in msg for msg in m["missing_info"])
