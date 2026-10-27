"""Hermetic public research workflows, persistence, provenance and isolation."""

from __future__ import annotations

import copy
import io
import json
import sqlite3
import subprocess
import sys
from pathlib import Path

import jsonschema
import pytest
from pydantic import ValidationError

from polyberg.cli import main
from polyberg.http import HttpReadError
from polyberg.research import storage
from polyberg.research.models import (
    Discovery,
    ResearchPacket,
    Source,
    canonical,
    digest,
)
from polyberg.research.packets import export_packet, freeze, load_frozen, render, verify_export
from polyberg.research.public import (
    PublicClient,
    PublicDataError,
    normalize_event,
    normalize_market,
)
from polyberg.research.service import Request, dispatch
from polyberg.research.storage import Store
from polyberg.research.workspace import Workspace

AT = "2026-10-26T12:00:00+00:00"
RULES = "  Synthetic market rules.\r\n\nResolve using the fictional Observatory print.  \n"
SENTINEL = "SYNTHETIC_ACCOUNT_SECRET_DO_NOT_EXPORT_7391"


def raw_market(mid="900001", **overrides):
    raw = {
        "id": mid,
        "slug": f"synthetic-{mid}",
        "question": f"Synthetic question {mid}?",
        "conditionId": "0x" + f"{int(mid):064x}",
        "questionID": f"question-{mid}",
        "active": True,
        "closed": False,
        "version": "v1",
        "outcomes": '["Above", "Below"]',
        "clobTokenIds": f'["{mid}10", "{mid}11"]',
        "outcomePrices": '["0.3", "0.65"]',
        "startDate": "2026-10-01T00:00:00Z",
        "endDate": "2026-11-01T00:00:00Z",
        "description": RULES,
        "resolutionSource": "https://example.invalid/observatory",
    }
    raw.update(overrides)
    return raw


def raw_event():
    return {
        "id": "700001",
        "slug": "synthetic-week",
        "title": "Synthetic weekly distribution",
        "description": "Event description is not contract rules.",
        "markets": [
            raw_market(),
            raw_market("900002", endDate="2026-11-08T00:00:00Z"),
            raw_market(
                "900003",
                outcomes='["Band A", "Band B", "Band C"]',
                clobTokenIds='["90000310", "90000311", "90000312"]',
                outcomePrices='["0.1", null, "0.4"]',
            ),
        ],
    }


def history_rows(count=3, start=1793000000, step=1800):
    return [
        {
            "timestamp": start + i * step,
            "price": round(0.3 + i / 100, 4),
            "resolution_seconds": step,
        }
        for i in range(count)
    ]


class FakeHttp:
    def __init__(self, *, event=None, clob=False, data=False):
        self.event = event or raw_event()
        self.clob = clob
        self.data = data
        self.calls = []
        self.fail = set()
        self.store = None

    def get_json(self, path, params=None, headers=None):
        if self.store:
            assert not self.store.db.in_transaction, "Network called in a transaction"
        self.calls.append((path, params))
        key = (path, (params or {}).get("token_id"))
        if path in self.fail or key in self.fail:
            raise HttpReadError(SENTINEL)
        if self.clob:
            if path == "/book":
                return {
                    "asset_id": params["token_id"],
                    "timestamp": "1793016000000",
                    "bids": [{"price": ".1"}, {"price": ".29"}, {"price": ".2"}],
                    "asks": [{"price": ".8"}, {"price": ".31"}, {"price": ".5"}],
                    "last_trade_price": ".99",
                    "owner": SENTINEL,
                    "my_resting": [{"account": SENTINEL}],
                }
            if path == "/midpoint":
                return {"mid": ".30", "portfolio": {"wallet": SENTINEL}}
            if path == "/last-trade-price":
                return {"price": ".28", "balance": SENTINEL}
            if path == "/prices-history":
                return {"history": [{"t": 1793000000, "p": 0.25}, {"t": 1793003600, "p": 0.27}]}
            raise AssertionError(f"Unexpected public endpoint: {path}")
        if self.data:
            if path == "/v2/oi":
                conditions = params["condition"].split(",")
                rows = [{"condition_id": c, "value": 1000.0 + i} for i, c in enumerate(conditions)]
                return {"data": rows, "account": SENTINEL}
            if path == "/v2/prices-history":
                return {"data": history_rows(), "pagination": {"has_more": False}}
            raise AssertionError(f"Unexpected public endpoint: {path}")
        if path == "/public-search":
            return {"events": [copy.deepcopy(self.event)], "account": SENTINEL}
        if path.startswith("/events"):
            return [copy.deepcopy(self.event)] if path == "/events" else copy.deepcopy(self.event)
        if path.startswith("/markets"):
            markets = copy.deepcopy(self.event["markets"])
            for m in markets:
                m["events"] = [
                    {
                        "id": self.event["id"],
                        "slug": self.event["slug"],
                        "title": self.event["title"],
                    }
                ]
            if path != "/markets":
                return next((m for m in markets if m["id"] == path.split("/")[-1]), [])
            if params and "slug" in params:
                return [m for m in markets if m["slug"] == params["slug"]]
            return [m for m in markets if m["conditionId"] == params["condition_ids"]]
        raise AssertionError(f"Unexpected public endpoint: {path}")


@pytest.fixture
def workspace(tmp_path):
    with Store(tmp_path / "research.sqlite3") as store:
        gamma, clob, data = FakeHttp(), FakeHttp(clob=True), FakeHttp(data=True)
        gamma.store = clob.store = data.store = store
        yield Workspace(store, PublicClient(gamma, clob, data))


def test_empty_init_and_reopen_without_imports(tmp_path, monkeypatch, capsys):
    path = tmp_path / "research.sqlite3"
    monkeypatch.setenv("POLYBERG_RESEARCH_DB", str(path))
    assert main(["research", "init"]) == 0
    assert json.loads(capsys.readouterr().out)["projects"][0]["name"] == "default"
    with Store(path) as store:
        assert store.all("SELECT * FROM markets") == []
        assert store.db.execute("PRAGMA foreign_keys").fetchone()[0] == 1
        assert store.db.execute("PRAGMA busy_timeout").fetchone()[0] == 5000
        before = path.stat().st_mtime_ns
    with Store(path):
        assert path.stat().st_mtime_ns == before


def test_complete_public_url_note_packet_persistence(workspace, tmp_path):
    w = workspace
    ids = w.follow("https://polymarket.com/event/synthetic-week/synthetic-900001?utm=ignored")
    assert ids == ["900001"]
    assert w.follow("https://polymarket.com/event/synthetic-week/synthetic-900001") == ids
    assert len(w.select()) == 1
    entry = w.add_entry(
        ids[0],
        "observation",
        "Synthetic observation",
        [Source(url="https://example.invalid/evidence", published_at=AT, observed_at=AT)],
    )
    assert w.show(ids[0]).entries[0].verified_at is None
    w.verify_entry(entry)
    w.add_entry(ids[0], "model_interpretation", "Synthetic model hypothesis", [])
    w.set_status(ids[0], "researching")
    w.tags(ids[0], ["weekly", "weekly", "evidence"])
    frozen = freeze(w, market=ids[0], generated_at=AT)
    files = render(frozen)
    exported = export_packet(w, frozen, tmp_path / "exports")
    assert set(files) == {"canonical.json", "shared.md", "gpt.md", "claude.md"}
    assert verify_export(Path(exported["directory"]))["snapshot_sha256"] == frozen.snapshot_sha256
    with Store(w.store.path) as reopened:
        other = Workspace(reopened)
        assert other.show(ids[0]).entries[0].verified_at
        assert other.show(ids[0]).tags == ["evidence", "weekly"]
        assert render(load_frozen(other, frozen.packet_id)) == files
    assert w.store.one("SELECT count(*) AS n FROM market_snapshots")["n"] == 2
    assert w.store.one("SELECT count(*) AS n FROM rules_versions")["n"] == 1
    assert len(w.rules_history(ids[0])[0].observations) == 2


@pytest.mark.parametrize(
    "reference",
    [
        "900001",
        "market:900001",
        "market:synthetic-900001",
        "https://polymarket.com/market/synthetic-900001",
        "https://www.polymarket.com/event/synthetic-week/synthetic-900001/",
        "condition:0x" + f"{900001:064x}",
    ],
)
def test_resolves_public_identities(workspace, reference):
    result = workspace.public.resolve(reference)
    market = result.markets[0].identification
    assert market.market_id == "900001"
    assert market.event_id == "700001"
    assert market.question_id == "question-900001"
    assert market.outcomes[0].label == "Above"
    assert market.outcomes[0].asset_id == "90000110"


@pytest.mark.parametrize(
    "reference",
    [
        "https://polymarket.com.evil.invalid/event/test",
        "https://evil.invalid/market/test",
        "https://polymarket.com/account/test",
        "https://polymarket.com/event/test/a/b",
        "http://polymarket.com/event/test",
        "https://user:secret@polymarket.com/event/test",
        "0x" + "1" * 64,
        "condition:0x1234",
        "event:../etc",
        "wallet:123",
    ],
)
def test_rejects_untyped_or_invalid_references(workspace, reference):
    with pytest.raises(PublicDataError):
        workspace.public.resolve(reference)


def test_ambiguous_slugs_require_selection(workspace):
    workspace.public.gamma.event["markets"][0]["slug"] = "synthetic-week"
    with pytest.raises(PublicDataError, match="Ambiguous"):
        workspace.public.resolve("synthetic-week")
    assert len(workspace.public.resolve("event:synthetic-week").markets) == 3


def test_all_event_contracts_outcomes_and_missing_child_collection(workspace):
    w = workspace
    w.follow("https://polymarket.com/event/synthetic-week/synthetic-900001")
    packet = freeze(w, event="700001", generated_at=AT).packet
    assert len(packet.markets) == 3
    assert len(packet.markets[2].identification.outcomes) == 3
    assert packet.markets[2].snapshot is None
    assert any("Child contracts not collected" in warning for warning in packet.warnings)
    w.follow("event:synthetic-week")
    packet = freeze(w, event="700001", generated_at=AT).packet
    assert all(m.snapshot for m in packet.markets)
    assert len({m.identification.trading_end for m in packet.markets}) == 2
    assert packet.markets[2].snapshot.quotes[1].displayed_price is None
    assert sum(q.displayed_price or 0 for q in packet.markets[2].snapshot.quotes) == 0.5
    assert all(not m.rules.annotations for m in packet.markets)


def test_v2_protocol_chooses_positions_without_personal_api(workspace):
    raw = raw_market(version="v2", positionIds=["777", "778"])
    normalized = normalize_market(raw, AT)
    assert normalized.identification.outcomes[0].token_id == "90000110"
    assert normalized.identification.outcomes[0].asset_id == "777"
    workspace.public.collect_quotes(normalized)
    assert all(call[1]["token_id"] in {"777", "778"} for call in workspace.public.clob.calls)
    unknown = normalize_market(raw_market(version="v3"), AT)
    assert all(o.asset_id is None for o in unknown.identification.outcomes)
    missing = normalize_market(raw_market(version="v2", positionIds=None), AT)
    assert all(o.asset_id is None for o in missing.identification.outcomes)


def test_unsorted_books_separate_prices_and_failures(workspace):
    w = workspace
    w.public.clob.fail.add(("/midpoint", "90000111"))
    w.follow("market:900001")
    quotes = w.show("900001").snapshot.quotes
    assert quotes[0].best_bid == 0.29
    assert quotes[0].best_ask == 0.31
    assert quotes[0].displayed_price == 0.3
    assert quotes[0].midpoint == 0.3
    assert quotes[0].last_trade == 0.28  # Does not use book's .99 or a complementary price.
    assert quotes[1].midpoint is None
    assert quotes[1].best_bid == 0.29
    assert quotes[1].displayed_price == 0.65
    assert any("midpoint unavailable" in s for s in quotes[1].warnings)


def test_failed_refresh_retains_snapshot_timestamp_and_history(workspace):
    w = workspace
    w.follow("event:synthetic-week")
    before = w.show("900001")
    w.public.gamma.fail.add("/markets/900001")
    result = w.refresh(["900001", "900002"])
    assert result == {"refreshed": ["900002"], "failed": ["900001"]}
    after = w.show("900001")
    assert before.last_success_at == after.last_success_at
    assert before.snapshot == after.snapshot
    assert "failed" in after.warnings[0]
    assert SENTINEL not in canonical(freeze(w, generated_at=AT))


def test_partial_book_failure_retains_actual_old_timestamp(workspace):
    w = workspace
    w.follow("market:900001")
    before = w.show("900001").snapshot.quotes[0]
    w.public.clob.fail.add(("/book", "90000110"))
    w.refresh(["900001"])
    after = w.show("900001").snapshot.quotes[0]
    assert after.book_retrieved_at == before.book_retrieved_at
    assert after.best_bid == before.best_bid
    assert "Historical" in " ".join(after.warnings)
    assert (
        w.store.one("SELECT status FROM refresh_attempts ORDER BY attempt_id DESC")["status"]
        == "partial"
    )


def test_rules_verbatim_versions_metadata_observations_and_review(workspace):
    w = workspace
    w.follow("market:900001")
    first = w.rules_history("900001")[0]
    assert first.text == RULES
    assert first.text_sha256 == digest(RULES)
    w.annotate(
        "900001",
        first.rules_version_id,
        "measurement_period",
        "Fictional week one",
        "https://example.invalid/rules",
    )
    w.public.gamma.event["markets"][0]["description"] = RULES + "Changed deadline."
    w.refresh(["900001"])
    versions = w.rules_history("900001")
    assert len(versions) == 2
    assert versions[0].annotations[0].needs_review
    assert w.show("900001").annotations_for_review
    assert w.show("900001").rules.annotations == []
    w.public.gamma.event["markets"][0]["resolutionSource"] = "https://example.invalid/new-source"
    w.refresh(["900001"])
    assert len(w.rules_history("900001")) == 3
    w.public.gamma.event["markets"][0]["description"] = None
    w.refresh(["900001"])
    assert w.show("900001").rules is None
    assert len(w.rules_history("900001")) == 3
    assert (
        w.store.one("SELECT rules_version_id FROM rules_observations ORDER BY observation_id DESC")[
            "rules_version_id"
        ]
        is None
    )


def test_projects_archive_unfollow_sources_verification_and_history(workspace):
    w = workspace
    w.follow("market:900001")
    w.create_project("Observatory")
    w.membership("900001", "Observatory")
    w.membership("900001", "Observatory")
    w.set_status("900001", "monitoring")
    w.set_status("900001", "archived")
    assert w.select() == []
    w.unarchive("900001")
    assert w.show("900001").status == "monitoring"
    eid = w.add_entry("900001", "observation", "Unsourced", [])
    with pytest.raises(ValueError, match="source references"):
        w.verify_entry(eid)
    model = w.add_entry(
        "900001", "model_interpretation", "Model", [Source(url="https://example.invalid")]
    )
    with pytest.raises(ValueError, match="Only source-supported observations"):
        w.verify_entry(model)
    w.set_followed("900001", False)
    assert w.select() == []
    assert w.select(project="Observatory") == ["900001"]
    assert len(w.show("900001").entries) == 2
    assert w.store.one("SELECT count(*) n FROM workspace_history")["n"] >= 8
    with pytest.raises(ValueError, match="Unknown research project"):
        w.membership("900001", "unknown")


def test_relationship_direction_symmetry_and_comparison(workspace):
    w = workspace
    w.follow("event:synthetic-week")
    w.relate("900002", "900001", "correlated", "Shared fictional drivers")
    w.relate("900001", "900002", "correlated", "Revised explanation")
    w.relate("900002", "900001", "implication", "Explicit direction")
    relationships = w.show("900001").relationships
    assert len(relationships) == 2
    assert relationships[0].from_market == "900001"
    assert relationships[1].from_market == "900002"
    result = dispatch(w, Request(operation="compare", market="900001", other_market="900002"))
    assert len(result["packet"]["markets"]) == 2
    assert "Revised explanation" in result["contents"]["shared.md"]
    assert "Explicit direction" in result["contents"]["shared.md"]


def test_frozen_render_is_byte_identical_after_workspace_changes(workspace, tmp_path, monkeypatch):
    w = workspace
    w.follow("market:900001")
    frozen = freeze(w, generated_at=AT)
    files = render(frozen)
    gpt_body = (
        files["gpt.md"]
        .split("<!-- BEGIN SHARED EVIDENCE -->\n")[1]
        .split("<!-- END SHARED EVIDENCE -->")[0]
    )
    claude_body = (
        files["claude.md"]
        .split("<!-- BEGIN SHARED EVIDENCE -->\n")[1]
        .split("<!-- END SHARED EVIDENCE -->")[0]
    )
    assert gpt_body == claude_body == files["shared.md"]
    w.add_entry("900001", "question", "Later question", [])
    monkeypatch.setenv("POLYBERG_MAX_CONTEXT_AGE_HOURS", "1")
    assert render(load_frozen(w, frozen.packet_id)) == files
    exported = export_packet(w, frozen, tmp_path / "export")
    assert export_packet(w, frozen, tmp_path / "export") == exported
    path = Path(exported["directory"])
    (path / "claude.md").write_text("incomplete")
    with pytest.raises(ValueError, match="Incomplete"):
        verify_export(path)
    with pytest.raises(ValueError):
        export_packet(w, frozen, tmp_path / "export")


def test_freshness_future_missing_invalid_and_stale(workspace):
    w = workspace
    for mid, timestamp in [
        ("900001", "2026-10-20T00:00:00Z"),
        ("900002", "2099-01-01T00:00:00Z"),
        ("900003", "not-a-timestamp"),
    ]:
        w.ingest(Discovery(markets=[normalize_market(raw_market(mid), timestamp)]), follow=True)
    packet = freeze(w, generated_at=AT).packet
    assert any("stale" in s for s in packet.markets[0].warnings)
    assert any("future" in s for s in packet.markets[1].warnings)
    assert any("invalid" in s for s in packet.markets[2].warnings)
    assert any("missing" in s for s in packet.markets[0].warnings)
    assert packet.max_age_hours == 36
    assert all(not m.rules.annotations for m in packet.markets)


def test_sqlite_migration_rollback_future_and_foreign_keys(tmp_path, monkeypatch):
    path = tmp_path / "rollback.sqlite3"
    monkeypatch.setattr(storage, "MIGRATIONS", [(1, "CREATE TABLE probe(id INTEGER); BROKEN SQL;")])
    with pytest.raises(sqlite3.OperationalError):
        Store(path)
    with sqlite3.connect(path) as conn:
        assert conn.execute("PRAGMA user_version").fetchone()[0] == 0
        assert conn.execute("SELECT name FROM sqlite_master WHERE name='probe'").fetchone() is None
        conn.execute("PRAGMA user_version = 99")
    with pytest.raises(ValueError, match="newer"):
        Store(path)


def test_transaction_rolls_back_failed_ingest(workspace):
    w = workspace
    w.follow("market:900001")
    before = w.store.one("SELECT count(*) n FROM market_snapshots")["n"]
    bad = normalize_market(raw_market("900002"), AT)
    bad.quotes[0].outcome_id = "not-a-real-outcome"
    with pytest.raises(sqlite3.IntegrityError):
        w.ingest(Discovery(markets=[bad]))
    assert w.store.one("SELECT 1 FROM markets WHERE market_id='900002'") is None
    assert w.store.one("SELECT count(*) n FROM market_snapshots")["n"] == before


def test_allowlists_drop_injected_account_objects_and_diagnostics(
    workspace, tmp_path, capsys, monkeypatch
):
    w = workspace
    upstream = w.public.gamma.event
    injected = {"wallet": SENTINEL, "positions": [{"balance": SENTINEL}], "open_orders": SENTINEL}
    upstream.update(injected)
    for raw in upstream["markets"]:
        raw.update(injected)
        raw["metadata"] = {"nested": [injected]}
    w.follow("event:synthetic-week")
    frozen = freeze(w, generated_at=AT)
    for content in render(frozen).values():
        assert SENTINEL not in content
        for forbidden in ['"wallet"', '"positions"', '"open_orders"', '"my_resting"', '"balance"']:
            assert forbidden not in content
    assert SENTINEL not in w.store.path.read_bytes().decode("utf-8", errors="replace")
    with pytest.raises(ValidationError):
        Request.model_validate({"operation": "list", "wallet": SENTINEL})
    monkeypatch.setattr(
        sys, "stdin", io.StringIO(json.dumps({"operation": "legacy", "wallet": SENTINEL}))
    )
    assert main(["--db", str(tmp_path / "rpc.sqlite3"), "research", "rpc"]) == 1
    assert SENTINEL not in capsys.readouterr().out


def test_schema_matches_and_strict_nested_validation(workspace):
    workspace.follow("market:900001")
    payload = freeze(workspace, generated_at=AT).packet.model_dump()
    schema = json.loads(Path("schemas/research_packet.schema.json").read_text())
    jsonschema.Draft202012Validator(schema).validate(payload)
    assert schema == ResearchPacket.model_json_schema()
    payload["markets"][0]["identification"]["outcomes"][0]["wallet"] = SENTINEL
    with pytest.raises(ValidationError):
        ResearchPacket.model_validate(payload)
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(payload, schema)


def test_fresh_process_blocks_account_imports_and_credential_loads(tmp_path):
    script = r"""
import importlib.abc, os, runpy, sys
class DenyLegacy(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        blocked = ("polyberg.collectors.polymarket_account",
                   "polyberg.collectors.polymarket_clob_auth", "polyberg.loaders",
                   "polyberg.legacy_cli", "polyberg.packet_builder", "cryptography")
        if fullname.startswith(blocked):
            raise AssertionError("Research reached a legacy import")
sys.meta_path.insert(0, DenyLegacy())
for key in list(os.environ):
    if key.startswith(("POLYMARKET_", "CLOB_", "POLY_")): del os.environ[key]
from polyberg import config
config.load_repo_dotenv = lambda *a, **kw: (_ for _ in ()).throw(AssertionError("dotenv reached"))
fixtures = runpy.run_path("tests/test_research.py")
from polyberg.research.public import PublicClient
from polyberg.research import workspace
workspace.PublicClient = lambda: PublicClient(fixtures["FakeHttp"](),
    fixtures["FakeHttp"](clob=True), fixtures["FakeHttp"](data=True))
from polyberg.cli import main
commands = [["research", "init"], ["research", "search", "synthetic"],
 ["research", "follow", "https://polymarket.com/event/synthetic-week/synthetic-900001"],
 ["research", "note", "900001", "Synthetic sourced observation",
  "--source", "https://example.invalid/source"],
 ["research", "verify", "1"],
 ["packet", "build", "--market", "900001", "--output-dir", sys.argv[2]]]
for command in commands:
    assert main(["--db", sys.argv[1], *command]) == 0
assert not any(name.startswith("polyberg.collectors.polymarket_account") for name in sys.modules)
"""
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            script,
            str(tmp_path / "isolated.sqlite3"),
            str(tmp_path / "exports"),
        ],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    assert "Synthetic sourced observation" in result.stdout
    assert SENTINEL not in result.stdout


def test_closed_market_missing_rules_does_not_use_event_description(workspace):
    w = workspace
    raw = w.public.gamma.event["markets"][0]
    raw.update({"closed": True, "active": False, "description": None})
    w.public.clob.fail.update({"/book", "/midpoint", "/last-trade-price"})
    w.follow("event:synthetic-week")
    market = w.show("900001")
    assert market.identification.lifecycle == "closed"
    assert market.rules is None
    assert market.snapshot.quotes[0].best_bid is None
    assert any("rules unavailable" in warning for warning in market.snapshot.warnings)
    assert w.events()[0].description == "Event description is not contract rules."


def test_malformed_prices_books_and_unknown_shapes_are_explicit(workspace):
    w = workspace
    market = normalize_market(raw_market(outcomePrices='["nan", {"wallet": "secret"}]'), AT)
    assert all(q.displayed_price is None for q in market.quotes)
    original = w.public.clob.get_json

    def malformed(path, **kwargs):
        if path == "/book":
            return {
                "bids": [None, {"price": "nan"}, {"price": "-1"}, {"price": ".2"}],
                "asks": {"wallet": SENTINEL},
            }
        return original(path, **kwargs)

    w.public.clob.get_json = malformed
    w.public.collect_quotes(market)
    assert market.quotes[0].best_bid is None
    assert market.quotes[0].best_ask is None
    assert market.quotes[0].book_retrieved_at is None
    assert any("Malformed" in warning for warning in market.quotes[0].warnings)
    assert SENTINEL not in canonical(market)
    raw = raw_event()
    raw["markets"].append({"description": SENTINEL})
    event, markets = normalize_event(raw, AT)
    assert len(markets) == 3
    assert any("collection incomplete" in warning for warning in event.warnings)


def test_refresh_event_retains_follow_state_and_discovers_new_children(workspace):
    w = workspace
    w.follow("event:synthetic-week")
    w.set_followed("900001", False)
    w.public.gamma.event["markets"].append(raw_market("900004"))
    result = w.refresh_event("700001")
    assert result["failed"] == []
    assert "900004" in result["refreshed"]
    assert not w.show("900001").followed
    assert not w.show("900004").followed
    assert len(freeze(w, event="700001", generated_at=AT).packet.markets) == 4


def test_archive_is_idempotent(workspace):
    w = workspace
    w.follow("market:900001")
    w.set_status("900001", "researching")
    w.set_status("900001", "archived")
    w.set_status("900001", "archived")
    w.unarchive("900001")
    assert w.show("900001").status == "researching"


def test_database_enforces_immutable_snapshots_rules_and_frozen_packets(workspace):
    w = workspace
    w.follow("market:900001")
    freeze(w, generated_at=AT)
    for table in [
        "rules_versions",
        "rules_observations",
        "market_snapshots",
        "outcome_quotes",
        "packet_snapshots",
        "refresh_attempts",
    ]:
        with pytest.raises(sqlite3.IntegrityError, match="Immutable"):
            w.db.execute(f"DELETE FROM {table}")
    with pytest.raises(sqlite3.IntegrityError, match="Immutable"):
        w.db.execute("UPDATE rules_versions SET data='{}'")
    with pytest.raises(sqlite3.IntegrityError):
        w.db.execute("INSERT INTO project_markets VALUES (1, 'missing')")


def test_failed_file_publication_never_creates_complete_export(workspace, tmp_path, monkeypatch):
    w = workspace
    w.follow("market:900001")
    frozen = freeze(w, generated_at=AT)
    original = Path.write_text

    def fail_claude(path, content, **kwargs):
        if path.name == "claude.md":
            raise OSError("Simulated local write failure")
        return original(path, content, **kwargs)

    monkeypatch.setattr(Path, "write_text", fail_claude)
    with pytest.raises(OSError):
        export_packet(w, frozen, tmp_path / "exports")
    assert not (tmp_path / "exports" / frozen.packet_id).exists()
    assert w.store.all("SELECT * FROM exports") == []


def test_explicit_legacy_dispatch_and_unprefixed_account_rejection(monkeypatch):
    import polyberg.legacy_cli as legacy

    calls = []
    monkeypatch.setattr(legacy, "main", lambda args: calls.append(args) or 0)
    assert main(["legacy", "packet", "build", "--target", "all"]) == 0
    assert calls == [["packet", "build", "--target", "all"]]
    with pytest.raises(SystemExit):
        main(["import-account-snapshot"])


def test_cli_projects_relationships_and_packet_render(workspace, monkeypatch, capsys, tmp_path):
    w = workspace
    w.follow("event:synthetic-week")
    monkeypatch.setenv("POLYBERG_RESEARCH_DB", str(w.store.path))
    commands = [
        ["research", "projects", "create", "CLI project"],
        ["research", "projects", "add", "CLI project", "900001"],
        ["research", "projects", "list"],
        ["research", "tags", "900001", "weekly", "synthetic"],
        [
            "research",
            "relate",
            "900001",
            "900002",
            "Shared synthetic source",
            "--kind",
            "correlated",
        ],
        ["research", "status", "900001", "screening"],
        ["research", "list", "--project", "CLI project"],
        ["research", "show", "900001"],
        ["research", "rules", "900001"],
        ["research", "history", "900001"],
        ["research", "compare", "900001", "900002"],
    ]
    for command in commands:
        assert main(command) == 0
        assert json.loads(capsys.readouterr().out)
    assert w.show("900001").status == "screening"
    assert w.show("900001").relationships[0].explanation == "Shared synthetic source"
    output = tmp_path / "packet-exports"
    assert main(["packet", "build", "--project", "CLI project", "--output-dir", str(output)]) == 0
    result = json.loads(capsys.readouterr().out)
    assert main(["packet", "render", result["packet_id"], "--output-dir", str(output)]) == 0
    repeated = json.loads(capsys.readouterr().out)
    assert repeated == result


def test_synthetic_examples_validate_and_match_renderers():
    for directory in Path("examples/research").iterdir():
        if not directory.is_dir():
            continue
        manifest = verify_export(directory)
        packet = ResearchPacket.model_validate_json((directory / "canonical.json").read_bytes())
        from polyberg.research.models import FrozenPacket

        frozen = FrozenPacket(
            packet_id=manifest["packet_id"],
            snapshot_sha256=manifest["snapshot_sha256"],
            packet=packet,
        )
        for filename, content in render(frozen).items():
            assert (directory / filename).read_bytes() == content.encode("utf-8")
        assert all("SYNTHETIC" in m.identification.question for m in packet.markets)


def test_rules_provenance_distinguishes_market_and_event_sources(workspace):
    w = workspace
    w.follow("market:900001")
    first = w.rules_history("900001")[0]
    assert first.api_url == "https://gamma-api.polymarket.com/markets/900001"
    assert first.page_url == "https://polymarket.com/event/synthetic-week/synthetic-900001"
    assert len(w.events()[0].contracts) == 3
    w.follow("event:synthetic-week")
    versions = w.rules_history("900001")
    assert len(versions) == 2
    assert versions[1].api_url == "https://gamma-api.polymarket.com/events?slug=synthetic-week"
    assert versions[0].text_sha256 == versions[1].text_sha256
    quote = w.show("900001").snapshot.quotes[0]
    assert versions[1].api_url in quote.source_urls


def test_unavailable_parent_is_explicit_without_losing_contract(workspace):
    w = workspace
    w.public.gamma.fail.add("/events/700001")
    assert w.follow("market:900001") == ["900001"]
    assert "Full parent event collection unavailable" in w.events()[0].warnings
    packet = freeze(w, event="700001", generated_at=AT).packet
    assert any("parent event collection unavailable" in warning for warning in packet.warnings)


def test_missing_displayed_price_retains_historical_value_and_timestamp(workspace):
    w = workspace
    w.follow("market:900001")
    before = w.show("900001").snapshot.quotes[0]
    w.public.gamma.event["markets"][0]["outcomePrices"] = '[null, "0.65"]'
    w.refresh(["900001"])
    after = w.show("900001").snapshot.quotes[0]
    assert after.displayed_price == before.displayed_price
    assert after.displayed_at == before.displayed_at
    assert any("Historical displayed_price" in warning for warning in after.warnings)
    assert any("Displayed price unavailable" in warning for warning in after.warnings)
