"""Tests for the read-only order book fetcher (polyberg.books)."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from io import BytesIO
from urllib.error import HTTPError

import pytest
import yaml

from polyberg.books import (
    BookUnavailableError,
    MarketBooks,
    build_ladder,
    build_side_book,
    fetch_all_books,
    fetch_book_with_retry,
    fetch_market_books,
    filter_books_markdown,
    load_token_map,
    render_books_markdown,
    write_books_json,
    write_session_starter,
)
from polyberg.collectors.polymarket_account import ReadOnlyHttpClient
from polyberg.models import Market, OpenOrders

NOW = datetime(2026, 6, 11, 9, 0, 0, tzinfo=UTC)


class FakeResponse:
    def __init__(self, payload: object) -> None:
        self.payload = payload

    def __enter__(self) -> FakeResponse:
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def read(self) -> bytes:
        return json.dumps(self.payload).encode("utf-8")


class ScriptedOpener:
    """Opener that serves a queued list of responses, one per request.

    An Exception instance in the queue is raised instead of returned, so
    HTTP error paths (404, 429, 5xx) can be scripted in order.
    """

    def __init__(self, responses: list[object]) -> None:
        self._responses = list(responses)
        self.urls: list[str] = []

    def __call__(self, request, timeout):
        self.urls.append(request.full_url)
        if not self._responses:
            raise AssertionError("Opener exhausted — unexpected extra request")
        item = self._responses.pop(0)
        if isinstance(item, Exception):
            raise item
        return FakeResponse(item)


def _http_error(code: int) -> HTTPError:
    return HTTPError("https://clob.local/book", code, f"status {code}", None, BytesIO(b""))


def _book(bids: list[tuple[float, float]], asks: list[tuple[float, float]], **extra) -> dict:
    payload = {
        "bids": [{"price": str(p), "size": str(s)} for p, s in bids],
        "asks": [{"price": str(p), "size": str(s)} for p, s in asks],
        "asset_id": "token",
    }
    payload.update(extra)
    return payload


def _no_sleep(_: float) -> None:
    return None


def _market(**overrides) -> Market:
    base = dict(
        market_id="hormuz_test",
        name="Hormuz test market",
        polymarket_url="https://polymarket.com/event/hormuz-test",
        category="core_hormuz",
        rule_key="hormuz_portwatch_7dma",
        oracle_type="IMF Portwatch data",
        preferred_side="NO",
        resolution_date="2026-06-30",
        notes="",
        condition_id="0xc0ffee",
        yes_token_id="111",
        no_token_id="222",
        data_collection={"fetch_orderbook": True},
    )
    base.update(overrides)
    return Market.model_validate(base)


def _empty_orders() -> OpenOrders:
    return OpenOrders.model_validate(
        {"as_of": "2026-06-11T08:00:00+00:00", "buy_orders": [], "sell_orders": []}
    )


# --- (a) normal two-sided book -------------------------------------------------


def test_two_sided_book_summary_and_cumulative() -> None:
    book = _book(
        bids=[(0.48, 300), (0.50, 100), (0.49, 200)],  # unsorted on purpose
        asks=[(0.54, 250), (0.52, 150), (0.53, 100)],
        last_trade_price="0.51",
        tick_size="0.01",
    )
    side = build_side_book("tok", book, my_bids=[], my_asks=[])

    assert side.best_bid == 0.50
    assert side.best_ask == 0.52
    assert side.spread == pytest.approx(0.02)
    assert side.midpoint == pytest.approx(0.51)
    assert side.last_trade_price == pytest.approx(0.51)
    assert side.tick_size == "0.01"

    assert [level.price for level in side.bids] == [0.50, 0.49, 0.48]
    assert [level.price for level in side.asks] == [0.52, 0.53, 0.54]
    assert side.bids[-1].cum_shares == pytest.approx(600)
    assert side.bids[-1].cum_notional == pytest.approx(0.50 * 100 + 0.49 * 200 + 0.48 * 300)
    assert side.asks[-1].cum_shares == pytest.approx(500)

    bid_notional = 0.50 * 100 + 0.49 * 200 + 0.48 * 300
    ask_notional = 0.52 * 150 + 0.53 * 100 + 0.54 * 250
    assert side.book_imbalance == pytest.approx(
        bid_notional / (bid_notional + ask_notional), abs=1e-4
    )


def test_ladder_truncates_to_depth() -> None:
    bids = [(round(0.50 - i * 0.01, 2), 10.0) for i in range(15)]
    ladder, beyond, missing = build_ladder(
        [{"price": str(p), "size": str(s)} for p, s in bids], "bids", [], depth=10
    )
    assert len(ladder) == 10
    assert beyond == []
    assert missing == []
    # cumulative keeps counting through the ladder
    assert ladder[-1].cum_shares == pytest.approx(100)


# --- (b) empty side -------------------------------------------------------------


def test_empty_ask_side() -> None:
    book = _book(bids=[(0.40, 50)], asks=[])
    side = build_side_book("tok", book, my_bids=[], my_asks=[])
    assert side.best_bid == 0.40
    assert side.best_ask is None
    assert side.spread is None
    assert side.midpoint is None
    assert side.book_imbalance == pytest.approx(1.0)
    assert side.asks == []


def test_fully_empty_book_imbalance_is_none() -> None:
    side = build_side_book("tok", _book(bids=[], asks=[]), my_bids=[], my_asks=[])
    assert side.book_imbalance is None
    assert side.best_bid is None and side.best_ask is None


# --- (c) 429 retry path ----------------------------------------------------------


def test_retry_on_429_then_success() -> None:
    opener = ScriptedOpener([_http_error(429), _http_error(429), _book([(0.5, 10)], [(0.6, 5)])])
    http = ReadOnlyHttpClient("https://clob.local", opener=opener)
    sleeps: list[float] = []

    book = fetch_book_with_retry("tok", http=http, sleep=sleeps.append)

    assert book["bids"]
    assert sleeps == [0.5, 1.0]
    assert len(opener.urls) == 3


def test_retry_on_500_exhaustion_raises() -> None:
    opener = ScriptedOpener([_http_error(500)] * 4)
    http = ReadOnlyHttpClient("https://clob.local", opener=opener)
    sleeps: list[float] = []

    with pytest.raises(BookUnavailableError, match="HTTP 500"):
        fetch_book_with_retry("tok", http=http, sleep=sleeps.append)
    assert sleeps == [0.5, 1.0, 2.0]


def test_404_does_not_retry() -> None:
    opener = ScriptedOpener([_http_error(404)])
    http = ReadOnlyHttpClient("https://clob.local", opener=opener)

    with pytest.raises(BookUnavailableError, match="HTTP 404"):
        fetch_book_with_retry("tok", http=http, sleep=_no_sleep)
    assert len(opener.urls) == 1


# --- (d) my-order queue-position arithmetic --------------------------------------


def test_queue_position_partial_level() -> None:
    raw = [{"price": "0.50", "size": "100"}, {"price": "0.49", "size": "200"}]
    ladder, _, _ = build_ladder(raw, "bids", my_orders=[(0.49, 50)])
    level = ladder[1]
    assert level.my_resting is True
    assert level.my_shares == 50
    # 100 shares at strictly-better 0.50, plus the 150 non-mine at my level
    assert level.approx_shares_ahead == pytest.approx(250)
    assert ladder[0].my_resting is False


def test_queue_position_my_order_is_entire_level() -> None:
    raw = [{"price": "0.50", "size": "100"}, {"price": "0.49", "size": "200"}]
    ladder, _, _ = build_ladder(raw, "bids", my_orders=[(0.49, 200)])
    level = ladder[1]
    assert level.my_resting is True
    # nothing else at my level: only the strictly-better 100 ahead
    assert level.approx_shares_ahead == pytest.approx(100)


def test_queue_position_asks_better_is_lower_price() -> None:
    raw = [{"price": "0.55", "size": "80"}, {"price": "0.56", "size": "120"}]
    ladder, _, _ = build_ladder(raw, "asks", my_orders=[(0.56, 120)])
    assert ladder[0].price == 0.55
    assert ladder[1].approx_shares_ahead == pytest.approx(80)


def test_my_order_beyond_depth_still_reported() -> None:
    raw = [{"price": str(round(0.50 - i * 0.01, 2)), "size": "10"} for i in range(12)]
    ladder, beyond, _ = build_ladder(raw, "bids", my_orders=[(0.39, 10)], depth=10)
    assert len(ladder) == 10
    assert beyond == [
        {"side": "BID", "price": 0.39, "my_shares": 10.0, "approx_shares_ahead": pytest.approx(110)}
    ]


def test_my_order_not_in_book_is_flagged() -> None:
    raw = [{"price": "0.50", "size": "100"}]
    ladder, beyond, missing = build_ladder(raw, "bids", my_orders=[(0.45, 30)])
    assert beyond == []
    assert missing == [{"price": 0.45, "my_shares": 30.0}]
    assert not any(level.my_resting for level in ladder)


def test_my_orders_mapped_to_correct_outcome_book(tmp_path) -> None:
    """A NO buy rests on the NO token's bid side, not on the YES book."""
    orders = OpenOrders.model_validate(
        {
            "as_of": "2026-06-11T08:00:00+00:00",
            "buy_orders": [
                {"market_id": "hormuz_test", "side": "NO", "price": 0.50, "shares": 10}
            ],
            "sell_orders": [
                {"market_id": "hormuz_test", "side": "NO", "price": 0.85, "shares": 25}
            ],
        }
    )
    yes_book = _book(bids=[(0.50, 40)], asks=[(0.85, 60)])
    no_book = _book(bids=[(0.50, 40)], asks=[(0.85, 60)])
    opener = ScriptedOpener([yes_book, no_book])
    http = ReadOnlyHttpClient("https://clob.local", opener=opener)

    result = fetch_market_books(
        _market(), orders, token_map={}, now_fn=lambda: NOW, http=http, sleep=_no_sleep
    )

    assert result.status == "ok"
    assert not any(level.my_resting for level in result.sides["YES"].bids)
    assert not any(level.my_resting for level in result.sides["YES"].asks)
    no_side = result.sides["NO"]
    assert no_side.bids[0].my_resting is True
    assert no_side.bids[0].approx_shares_ahead == pytest.approx(30)  # 40 - my 10
    assert no_side.asks[0].my_resting is True
    assert no_side.asks[0].approx_shares_ahead == pytest.approx(35)  # 60 - my 25


# --- stale-cache guard ------------------------------------------------------------


def test_stale_token_reresolved_once_then_succeeds() -> None:
    fresh_yes = _book(bids=[(0.4, 10)], asks=[(0.6, 10)])
    fresh_no = _book(bids=[(0.4, 10)], asks=[(0.6, 10)])
    opener = ScriptedOpener(
        [
            _http_error(404),  # stale YES token
            _http_error(404),  # stale NO token
            {  # GET /markets/{condition_id}
                "tokens": [
                    {"token_id": "999", "outcome": "Yes"},
                    {"token_id": "888", "outcome": "No"},
                ]
            },
            fresh_yes,
            fresh_no,
        ]
    )
    http = ReadOnlyHttpClient("https://clob.local", opener=opener)
    token_map: dict[str, dict[str, str]] = {}

    result = fetch_market_books(
        _market(), _empty_orders(), token_map, now_fn=lambda: NOW, http=http, sleep=_no_sleep
    )

    assert result.status == "ok"
    assert result.sides["YES"].token_id == "999"
    assert result.sides["NO"].token_id == "888"
    assert token_map["hormuz_test"]["yes_token_id"] == "999"
    assert any("/markets/0xc0ffee" in url for url in opener.urls)


def test_stale_token_failure_after_reresolve_is_unavailable() -> None:
    opener = ScriptedOpener(
        [
            _http_error(404),
            _http_error(404),
            {
                "tokens": [
                    {"token_id": "999", "outcome": "Yes"},
                    {"token_id": "888", "outcome": "No"},
                ]
            },
            _http_error(404),
            _http_error(404),
        ]
    )
    http = ReadOnlyHttpClient("https://clob.local", opener=opener)

    result = fetch_market_books(
        _market(), _empty_orders(), {}, now_fn=lambda: NOW, http=http, sleep=_no_sleep
    )

    assert result.status == "unavailable"
    assert "after re-resolve" in (result.error or "")


def test_empty_both_sides_triggers_reresolve() -> None:
    empty = _book(bids=[], asks=[])
    live = _book(bids=[(0.4, 5)], asks=[(0.6, 5)])
    opener = ScriptedOpener(
        [
            empty,  # YES empty -> stale suspicion
            live,  # NO fine
            {
                "tokens": [
                    {"token_id": "999", "outcome": "Yes"},
                    {"token_id": "888", "outcome": "No"},
                ]
            },
            live,  # fresh YES token works
        ]
    )
    http = ReadOnlyHttpClient("https://clob.local", opener=opener)

    result = fetch_market_books(
        _market(), _empty_orders(), {}, now_fn=lambda: NOW, http=http, sleep=_no_sleep
    )
    assert result.status == "ok"
    assert result.sides["YES"].token_id == "999"


# --- per-market failure isolation --------------------------------------------------


def test_one_market_failing_does_not_kill_the_run(tmp_path) -> None:
    registry = {
        "markets": [
            json.loads(_market(market_id="m_ok", condition_id=None).model_dump_json()),
            json.loads(
                _market(
                    market_id="m_bad",
                    condition_id=None,
                    yes_token_id="333",
                    no_token_id="444",
                ).model_dump_json()
            ),
        ]
    }
    registry_path = tmp_path / "market_registry.yaml"
    registry_path.write_text(yaml.safe_dump(registry), encoding="utf-8")
    orders_path = tmp_path / "open_orders.yaml"
    orders_path.write_text(
        yaml.safe_dump(
            {"as_of": "2026-06-11T08:00:00+00:00", "buy_orders": [], "sell_orders": []}
        ),
        encoding="utf-8",
    )

    live = _book(bids=[(0.4, 5)], asks=[(0.6, 5)])
    opener = ScriptedOpener([live, live, _http_error(404), _http_error(404)])
    http = ReadOnlyHttpClient("https://clob.local", opener=opener)

    results = fetch_all_books(
        registry_path=registry_path,
        open_orders_path=orders_path,
        token_map_path=tmp_path / "token_map.json",
        http=http,
        sleep=_no_sleep,
        now_fn=lambda: NOW,
    )

    by_id = {r.market_id: r for r in results}
    assert by_id["m_ok"].status == "ok"
    assert by_id["m_bad"].status == "unavailable"


def test_fetch_all_books_skips_resolved_markets_not_held(tmp_path) -> None:
    """The active set drives fetching: a resolved, unheld market is skipped."""
    registry = {
        "markets": [
            json.loads(_market(market_id="m_active", lifecycle="active").model_dump_json()),
            json.loads(
                _market(
                    market_id="m_resolved",
                    lifecycle="resolved",
                    yes_token_id="333",
                    no_token_id="444",
                    condition_id=None,
                ).model_dump_json()
            ),
        ]
    }
    registry_path = tmp_path / "market_registry.yaml"
    registry_path.write_text(yaml.safe_dump(registry), encoding="utf-8")
    orders_path = tmp_path / "open_orders.yaml"
    orders_path.write_text(
        yaml.safe_dump({"as_of": "2026-06-11T08:00:00+00:00", "buy_orders": [], "sell_orders": []}),
        encoding="utf-8",
    )
    # Empty portfolio so the held set adds nothing.
    portfolio_path = tmp_path / "portfolio.yaml"
    portfolio_path.write_text(
        yaml.safe_dump(
            {
                "as_of": "2026-06-11T08:00:00+00:00",
                "portfolio_value": 10.0,
                "cash_available": 10.0,
                "positions": [],
            }
        ),
        encoding="utf-8",
    )

    live = _book(bids=[(0.4, 5)], asks=[(0.6, 5)])
    # Only two responses queued: enough for m_active's YES+NO. The resolved
    # market must not be fetched, or the opener would be exhausted.
    opener = ScriptedOpener([live, live])
    http = ReadOnlyHttpClient("https://clob.local", opener=opener)

    results = fetch_all_books(
        registry_path=registry_path,
        open_orders_path=orders_path,
        token_map_path=tmp_path / "token_map.json",
        portfolio_path=portfolio_path,
        http=http,
        sleep=_no_sleep,
        now_fn=lambda: NOW,
    )

    assert [r.market_id for r in results] == ["m_active"]


def test_filter_books_markdown_drops_out_of_set_sections() -> None:
    md = (
        "- Generated: now\n"
        "- Markets with live books: a, b\n"
        "### a — NO book · fetched_at t\n- ok a\n"
        "### b — BOOK UNAVAILABLE\n- err b\n"
        "### c — NO book · fetched_at t\n- ok c\n"
    )
    out = filter_books_markdown(md, {"a"})
    assert "### a" in out
    assert "ok a" in out
    assert "### b" not in out
    assert "### c" not in out
    # Preamble (non-### lines) is preserved.
    assert "Generated: now" in out


# --- artifacts ----------------------------------------------------------------------


def _ok_result() -> MarketBooks:
    book = _book(bids=[(0.50, 100), (0.49, 200)], asks=[(0.52, 150)], last_trade_price="0.51")
    side = build_side_book("tok-no", book, my_bids=[(0.49, 50)], my_asks=[])
    return MarketBooks(
        market_id="hormuz_test",
        fetched_at=NOW.isoformat(),
        status="ok",
        preferred_side="NO",
        sides={"NO": side, "YES": build_side_book("tok-yes", book, [], [])},
    )


def _bad_result() -> MarketBooks:
    return MarketBooks(
        market_id="hormuz_dead",
        fetched_at=NOW.isoformat(),
        status="unavailable",
        preferred_side="NO",
        error="YES: HTTP 404",
    )


def test_markdown_marks_my_levels_and_unavailable_markets() -> None:
    text = render_books_markdown([_ok_result(), _bad_result()], NOW)
    assert "Markets with live books: hormuz_test" in text
    assert "BID • | 0.490" in text
    assert "≈250 shares ahead (APPROXIMATE)" in text
    assert "hormuz_dead — BOOK UNAVAILABLE — do not price orders" in text
    assert "fetched_at " + NOW.isoformat() in text


def test_json_artifact_has_per_market_fetched_at(tmp_path) -> None:
    path = write_books_json([_ok_result(), _bad_result()], tmp_path / "order_books.json", NOW)
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["markets"]["hormuz_test"]["fetched_at"] == NOW.isoformat()
    assert payload["markets"]["hormuz_dead"]["status"] == "unavailable"
    level = payload["markets"]["hormuz_test"]["sides"]["NO"]["bids"][1]
    assert level["my_resting"] is True
    assert level["approx_shares_ahead"] == pytest.approx(250)
    assert "APPROXIMATE" in payload["queue_position_note"]


def test_session_starter_field_3_filled(tmp_path) -> None:
    template = tmp_path / "template.md"
    template.write_text(
        "[3] Markets with live books: {{live_book_markets}}\nStarted {{generated_at}}\n",
        encoding="utf-8",
    )
    out = write_session_starter(
        [_ok_result(), _bad_result()],
        NOW,
        template_path=template,
        output_path=tmp_path / "session_starter.md",
    )
    text = out.read_text(encoding="utf-8")
    assert "[3] Markets with live books: hormuz_test" in text
    assert "hormuz_dead" not in text
    assert NOW.isoformat() in text


def test_token_map_round_trip(tmp_path) -> None:
    path = tmp_path / "token_map.json"
    assert load_token_map(path) == {}
    path.write_text(json.dumps({"markets": {"m": {"yes_token_id": "1"}}}), encoding="utf-8")
    assert load_token_map(path)["m"]["yes_token_id"] == "1"


# --- packet integration ----------------------------------------------------------


def test_canonical_packet_picks_up_books(tmp_path) -> None:
    from polyberg.packet_builder.collect_state import collect_packet_state
    from polyberg.packet_builder.normalize_packet_state import build_canonical_packet

    books_dir = tmp_path / "live"
    books_dir.mkdir()
    write_books_json([_ok_result(), _bad_result()], books_dir / "order_books.json", NOW)
    (books_dir / "order_books.md").write_text(
        "## Live Order Books\n\n- Markets with live books: hormuz_test\n", encoding="utf-8"
    )

    state = collect_packet_state(now=NOW, books_dir=books_dir)
    # books_for="all" keeps the fake market ids (not in the real active set) so
    # this test exercises the book-wiring path, not active-set filtering.
    canonical = build_canonical_packet(state=state, books_for="all")

    assert canonical.order_books is not None
    assert canonical.order_books["markets_with_live_books"] == ["hormuz_test"]
    # The unavailable book is surfaced in the order-book section. (Per-market
    # priceability in missing_info is keyed on registry active-set markets; these
    # fake ids aren't in the registry, so coverage of that path lives in
    # test_blocking_warnings / the priceability tests instead.)
    assert canonical.order_books["unavailable_markets"] == ["hormuz_dead"]
    assert canonical.source_timestamps["order_books"] == NOW.isoformat()
    # markdown body had its own header stripped for renderer embedding
    assert not canonical.order_books["markdown"].startswith("## Live Order Books")
