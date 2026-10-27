"""Market-viewer additions: price history, activity, open interest, book depth, rules changes."""

from __future__ import annotations

import json
import sqlite3

import pytest
from pydantic import ValidationError
from test_research import AT, SENTINEL, FakeHttp, history_rows, raw_market

from polyberg.cli import main
from polyberg.research import history, storage
from polyberg.research import workspace as workspace_module
from polyberg.research.packets import freeze, render
from polyberg.research.public import PublicClient, PublicDataError, normalize_market
from polyberg.research.service import Request, dispatch
from polyberg.research.storage import Store
from polyberg.research.workspace import Workspace


def fakes():
    return FakeHttp(), FakeHttp(clob=True), FakeHttp(data=True)


@pytest.fixture
def viewer(tmp_path):
    with Store(tmp_path / "viewer.sqlite3") as store:
        gamma, clob, data = fakes()
        gamma.store = clob.store = data.store = store
        yield Workspace(store, PublicClient(gamma, clob, data))


def calls(http, path):
    return [params for called, params in http.calls if called == path]


class PagedData:
    """Data API double serving explicit pages; records every request."""

    def __init__(self, pages):
        self.pages, self.calls = list(pages), []

    def get_json(self, path, params=None, headers=None):
        self.calls.append((path, dict(params or {})))
        return self.pages.pop(0) if len(self.pages) > 1 else self.pages[0]


def page(rows, cursor=None):
    return {"data": rows, "pagination": {"has_more": cursor is not None, "next_cursor": cursor}}


# Activity and open interest


def test_activity_parses_numeric_strings_and_keeps_invalid_values_missing():
    raw = raw_market(
        volumeNum=None,
        volume="12.5",
        volume24hr=3,
        volume1wk=True,
        liquidity="not a number",
        oneDayPriceChange=-0.05,
        oneWeekPriceChange=4,
        spread="0.02",
    )
    activity = normalize_market(raw, AT).activity
    assert activity.volume_total == 12.5
    assert activity.volume_24h == 3.0
    assert activity.volume_1w is None
    assert activity.liquidity is None
    assert activity.price_change_1d == -0.05
    assert activity.price_change_1w is None
    assert activity.spread == 0.02
    assert activity.open_interest is None
    assert activity.source_urls == ["https://gamma-api.polymarket.com/markets/900001"]


def test_follow_stores_activity_with_one_batched_open_interest_read(viewer):
    w = viewer
    for raw in w.public.gamma.event["markets"]:
        raw.update(volumeNum=1500.0, volume24hr=25.5, liquidityNum=300.0, spread=0.01)
    w.follow("event:synthetic-week")
    requests = calls(w.public.data, "/v2/oi")
    assert len(requests) == 1
    assert len(requests[0]["condition"].split(",")) == 3
    activity = w.activity("900001")
    assert activity.volume_total == 1500.0
    assert activity.liquidity == 300.0
    assert activity.open_interest is not None and activity.open_interest >= 1000
    assert activity.open_interest_retrieved_at
    assert any(
        url.startswith("https://data-api.polymarket.com/v2/oi?") for url in activity.source_urls
    )
    with pytest.raises(sqlite3.IntegrityError, match="Immutable"):
        w.db.execute("DELETE FROM market_activity")


def test_open_interest_batches_twenty_conditions_per_request():
    data = FakeHttp(data=True)
    markets = [normalize_market(raw_market(str(900100 + i)), AT) for i in range(45)]
    PublicClient(FakeHttp(), FakeHttp(clob=True), data).collect_open_interest(markets)
    sizes = [len(p["condition"].split(",")) for p in calls(data, "/v2/oi")]
    assert sizes == [20, 20, 5]
    assert all(m.activity.open_interest is not None for m in markets)


def test_open_interest_failure_is_a_warning_not_a_failed_refresh(viewer):
    w = viewer
    w.follow("market:900001")
    w.public.data.fail.add("/v2/oi")
    assert w.refresh(["900001"]) == {"refreshed": ["900001"], "failed": []}
    activity = w.activity("900001")
    assert activity.open_interest is None
    assert "Public open interest unavailable" in activity.warnings
    latest = w.store.one("SELECT status FROM refresh_attempts ORDER BY attempt_id DESC LIMIT 1")
    assert latest["status"] == "success"


def test_refresh_reads_open_interest_once_for_all_selected_markets(viewer):
    w = viewer
    w.follow("event:synthetic-week")
    before = len(calls(w.public.data, "/v2/oi"))
    w.refresh(["900001", "900002", "900003"])
    assert len(calls(w.public.data, "/v2/oi")) == before + 1


def test_list_returns_activity_and_event_context_beside_packet_markets(viewer):
    w = viewer
    w.follow("event:synthetic-week")
    result = dispatch(w, Request(operation="list"))
    assert set(result["activity"]) == {"900001", "900002", "900003"}
    assert result["events"]["700001"]["description"] == "Event description is not contract rules."
    assert result["events"]["700001"]["page_url"] == "https://polymarket.com/event/synthetic-week"
    # Viewer context never enters the frozen packet contract.
    for content in render(freeze(w, generated_at=AT)).values():
        assert "open_interest" not in content
        assert "volume_24h" not in content


# Price history


def test_price_history_fetches_caches_refetches_and_prunes(viewer):
    w = viewer
    w.follow("market:900001")
    result = w.price_history("900001", "1w")
    assert [len(s.points) for s in result.series] == [3, 3]
    assert result.series[0].source_url.startswith(
        "https://data-api.polymarket.com/v2/prices-history"
    )
    assert "bucket_seconds=1800" in result.series[0].source_url
    assert len(calls(w.public.data, "/v2/prices-history")) == 2
    cached = w.price_history("900001", "1w")
    assert len(calls(w.public.data, "/v2/prices-history")) == 2
    assert cached.series[0].points == result.series[0].points
    w.price_history("900001", "1w", refetch=True)
    assert len(calls(w.public.data, "/v2/prices-history")) == 4
    rows = w.store.all("SELECT outcome_id,span FROM price_history_fetches ORDER BY outcome_id")
    assert rows == [
        {"outcome_id": "900001:0", "span": "1w"},
        {"outcome_id": "900001:1", "span": "1w"},
    ]


def test_price_history_spans_are_cached_independently(viewer):
    w = viewer
    w.follow("market:900001")
    w.price_history("900001", "1w")
    w.price_history("900001", "1d")
    buckets = {p["bucket_seconds"] for p in calls(w.public.data, "/v2/prices-history")}
    assert buckets == {300, 1800}
    assert w.store.one("SELECT count(*) n FROM price_history_fetches")["n"] == 4


def test_pagination_resends_window_with_cursor_and_sorts_points():
    data = PagedData([page(history_rows(3, start=1793005400), "c1"), page(history_rows(3))])
    points, url, warnings = history.fetch_series(data, FakeHttp(clob=True), "90000110", "1w")
    first, second = (params for _, params in data.calls)
    assert second == {**first, "cursor": "c1"}
    assert [p.t for p in points] == sorted(p.t for p in points)
    assert len(points) == 6
    assert warnings == []


def test_page_limit_falls_back_to_clob_series():
    data = PagedData([page(history_rows(1), "again")])
    points, url, _ = history.fetch_series(data, FakeHttp(clob=True), "90000110", "1w")
    assert len(data.calls) == history.MAX_PAGES
    assert url.startswith("https://clob.polymarket.com/prices-history?")
    assert "fidelity=30" in url
    assert [p.r for p in points] == [1800, 1800]


def test_empty_explicit_bucket_retries_with_server_chosen_resolution():
    data = PagedData([page([]), page(history_rows(2))])
    points, url, _ = history.fetch_series(data, FakeHttp(clob=True), "90000110", "1d")
    assert "bucket_seconds" in data.calls[0][1]
    assert "bucket_seconds" not in data.calls[1][1]
    assert "bucket_seconds" not in url
    assert len(points) == 2


def test_malformed_points_are_omitted_with_a_warning():
    rows = history_rows(2) + [
        {"timestamp": "1793000000", "price": 0.5, "resolution_seconds": 1800},
        {"timestamp": 1793009000, "price": 1.5, "resolution_seconds": 1800},
        {"timestamp": 1793009000, "price": 0.5, "resolution_seconds": True},
        ["not", "a", "point"],
    ]
    points, _, warnings = history.fetch_series(
        PagedData([page(rows)]), FakeHttp(clob=True), "90000110", "1w"
    )
    assert len(points) == 2
    assert warnings == ["Malformed price history points omitted"]


def test_failed_refetch_serves_cache_without_writing(viewer):
    w = viewer
    w.follow("market:900001")
    w.public.data.fail.add("/v2/prices-history")
    fallback = w.price_history("900001", "1m")
    assert fallback.series[0].source_url.startswith("https://clob.polymarket.com/prices-history")
    w.public.clob.fail.add("/prices-history")
    before = w.store.all("SELECT * FROM price_history_fetches ORDER BY fetch_id")
    served = w.price_history("900001", "1m", refetch=True)
    assert w.store.all("SELECT * FROM price_history_fetches ORDER BY fetch_id") == before
    assert served.series[0].points == fallback.series[0].points
    assert any("Price history refresh failed" in x for x in served.series[0].warnings)
    assert SENTINEL not in json.dumps(served.model_dump())


def test_unavailable_history_and_missing_asset_are_explicit(viewer):
    w = viewer
    w.public.gamma.event["markets"][0]["version"] = "v9"
    w.public.gamma.event["markets"][1]["id"] = "900002"
    w.follow("market:900001")
    w.follow("market:900002")
    missing = w.price_history("900001", "1w")
    assert all("Public outcome asset ID unavailable" in s.warnings for s in missing.series)
    assert calls(w.public.data, "/v2/prices-history") == []
    w.public.data.fail.add("/v2/prices-history")
    w.public.clob.fail.add("/prices-history")
    empty = w.price_history("900002", "1w")
    assert all(s.points == [] for s in empty.series)
    assert all("Public price history unavailable" in s.warnings for s in empty.series)


def test_span_is_validated_at_every_boundary(viewer):
    viewer.follow("market:900001")
    with pytest.raises(ValidationError):
        Request.model_validate({"operation": "price_history", "market": "900001", "span": "2y"})
    with pytest.raises(ValueError, match="Unsupported"):
        viewer.price_history("900001", "2y")
    with pytest.raises(ValueError, match="not in the research workspace"):
        viewer.price_history("999999", "1w")


# Order book depth


class BookHttp(FakeHttp):
    def __init__(self, book):
        super().__init__(clob=True)
        self.book = book

    def get_json(self, path, params=None, headers=None):
        if path == "/book":
            self.calls.append((path, params))
            return {"asset_id": params["token_id"], **self.book}
        return super().get_json(path, params, headers)


def test_book_sorts_truncates_accumulates_and_never_writes(viewer):
    w = viewer
    w.follow("market:900001")
    bids = [{"price": f"0.{10 + i}", "size": "10"} for i in range(12)]
    bids += [{"price": "bad", "size": "1"}, {"price": "0.05"}]
    asks = [
        {"price": "0.40", "size": "5"},
        {"price": "0.24", "size": "2"},
        {"price": "0.30", "size": "1"},
    ]
    w.public.clob = BookHttp(
        {
            "bids": bids,
            "asks": asks,
            "tick_size": "0.01",
            "min_order_size": "5",
            "last_trade_price": "0.22",
            "timestamp": "1793016000000",
            "owner": SENTINEL,
        }
    )
    before = w.db.total_changes
    book = w.book("900001")
    assert w.db.total_changes == before
    first = book.outcomes[0]
    assert [level.price for level in first.bids] == [
        0.21,
        0.2,
        0.19,
        0.18,
        0.17,
        0.16,
        0.15,
        0.14,
        0.13,
        0.12,
    ]
    assert first.bids[-1].cumulative == 100
    assert first.bid_levels == 12
    assert [level.price for level in first.asks] == [0.24, 0.3, 0.4]
    assert [level.cumulative for level in first.asks] == [2, 3, 8]
    assert first.spread == 0.03 and first.book_midpoint == 0.225
    assert first.tick_size == 0.01 and first.min_order_size == 5
    assert "last_trade_price" not in book.model_dump()["outcomes"][0]
    assert "Malformed bids level omitted" in first.warnings
    assert "Bids level without size omitted" in first.warnings
    assert first.source_url == "https://clob.polymarket.com/book?token_id=90000110"
    assert SENTINEL not in json.dumps(book.model_dump())


def test_book_identity_mismatch_and_crossed_books_are_explicit(viewer):
    w = viewer
    w.follow("market:900001")
    w.public.clob = BookHttp({"asset_id": "somebody-else", "bids": [], "asks": []})
    mismatch = w.book("900001").outcomes[0]
    assert mismatch.bids == [] and "Public order book unavailable" in mismatch.warnings
    w.public.clob = BookHttp(
        {"bids": [{"price": "0.6", "size": "1"}], "asks": [{"price": "0.5", "size": "1"}]}
    )
    crossed = w.book("900001").outcomes[0]
    assert crossed.spread == -0.1 and "Crossed order book" in crossed.warnings


# Rules changes, CLI and storage


def test_rules_changes_report_text_diff_and_changed_fields(viewer):
    w = viewer
    w.follow("market:900001")
    raw = w.public.gamma.event["markets"][0]
    raw["description"] = raw["description"] + "Revised: fallback source added.\n"
    raw["umaResolutionStatus"] = "proposed"
    w.refresh(["900001"])
    result = dispatch(w, Request(operation="rules", market="900001"))
    (change,) = result["changes"].values()
    assert change["previous_version_id"] == result["versions"][0]["rules_version_id"]
    assert "+Revised: fallback source added." in change["text_diff"]
    assert change["fields"] == {"resolution_status": [None, "proposed"]}


def test_cli_price_history_and_book(viewer, monkeypatch, capsys):
    viewer.follow("market:900001")
    monkeypatch.setenv("POLYBERG_RESEARCH_DB", str(viewer.store.path))
    monkeypatch.setattr(workspace_module, "PublicClient", lambda: PublicClient(*fakes()))
    assert main(["research", "price-history", "900001", "--span", "1d"]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["span"] == "1d" and len(result["series"]) == 2
    assert main(["research", "book", "900001"]) == 0
    assert [o["outcome_id"] for o in json.loads(capsys.readouterr().out)["outcomes"]] == [
        "900001:0",
        "900001:1",
    ]


def test_version_one_database_upgrades_and_reopens_without_writes(tmp_path, monkeypatch):
    path = tmp_path / "v1.sqlite3"
    with monkeypatch.context() as patch:
        patch.setattr(storage, "MIGRATIONS", storage.MIGRATIONS[:1])
        Store(path).close()
    with sqlite3.connect(path) as conn:
        assert conn.execute("PRAGMA user_version").fetchone()[0] == 1
    with Store(path) as store:
        assert store.db.execute("PRAGMA user_version").fetchone()[0] == 2
        names = {r["name"] for r in store.all("SELECT name FROM sqlite_master WHERE type='table'")}
        assert {"market_activity", "price_history_fetches"} <= names
    before = path.stat().st_mtime_ns
    with Store(path):
        assert path.stat().st_mtime_ns == before


def test_failed_second_migration_rolls_back_to_version_one(tmp_path, monkeypatch):
    path = tmp_path / "broken.sqlite3"
    first = storage.MIGRATIONS[:1]
    with monkeypatch.context() as patch:
        patch.setattr(storage, "MIGRATIONS", first)
        Store(path).close()
    monkeypatch.setattr(
        storage, "MIGRATIONS", [*first, (2, "CREATE TABLE probe(id INTEGER); BROKEN;")]
    )
    with pytest.raises(sqlite3.OperationalError):
        Store(path)
    with sqlite3.connect(path) as conn:
        assert conn.execute("PRAGMA user_version").fetchone()[0] == 1
        assert conn.execute("SELECT name FROM sqlite_master WHERE name='probe'").fetchone() is None


def test_public_errors_stay_fixed_without_upstream_content():
    data = FakeHttp(data=True)
    data.fail.add("/v2/prices-history")
    clob = FakeHttp(clob=True)
    clob.fail.add("/prices-history")
    with pytest.raises(PublicDataError) as caught:
        history.fetch_series(data, clob, "90000110", "max")
    assert SENTINEL not in str(caught.value)
