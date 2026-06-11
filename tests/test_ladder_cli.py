"""Tests for ladder plan CLI (offline-first — uses --live-from with fixture JSON)."""
from __future__ import annotations

import json
from pathlib import Path

import yaml

from polyberg.cli import main

# ── helpers ───────────────────────────────────────────────────────────────────

def _write_yaml(tmp_path: Path, name: str, data: dict) -> Path:
    p = tmp_path / name
    p.write_text(yaml.dump(data), encoding="utf-8")
    return p


def _write_json(tmp_path: Path, name: str, data: dict) -> Path:
    p = tmp_path / name
    p.write_text(json.dumps(data), encoding="utf-8")
    return p


def _plan_args(target: Path, live: Path, cash: str = "1000.0", extra: list | None = None) -> list:
    args = ["ladder", "plan", "--target", str(target), "--live-from", str(live), "--cash", cash]
    return args + (extra or [])


def _patch_registry(monkeypatch, registry_path: Path) -> None:
    """Redirect load_market_registry to the given test registry file."""
    import polyberg.loaders as loaders_module

    original = loaders_module.load_market_registry
    monkeypatch.setattr(
        loaders_module,
        "load_market_registry",
        lambda p=None: original(registry_path),
    )


def _minimal_registry_yaml():
    return {
        "markets": [
            {
                "market_id": "test_sell_mkt",
                "name": "Test Sell Market",
                "polymarket_url": "https://polymarket.com/event/test-sell",
                "category": "test",
                "thesis_bucket": "",
                "rule_key": "test",
                "oracle_type": "test",
                "preferred_side": "NO",
                "resolution_date": "2026-12-31",
                "notes": "",
                "yes_token_id": "token_yes_sell",
                "no_token_id": "token_no_sell",
            },
            {
                "market_id": "test_buy_mkt",
                "name": "Test Buy Market",
                "polymarket_url": "https://polymarket.com/event/test-buy",
                "category": "test",
                "thesis_bucket": "",
                "rule_key": "test",
                "oracle_type": "test",
                "preferred_side": "NO",
                "resolution_date": "2026-12-31",
                "notes": "",
                "yes_token_id": "token_yes_buy",
                "no_token_id": "token_no_buy",
            },
        ]
    }


def _target_ladders_yaml():
    return {
        "schema_version": "1",
        "matching": {"price_tolerance": 0.0005, "shares_tolerance": 1.0},
        "ladders": [
            {
                "market_id": "test_sell_mkt",
                "outcome": "NO",
                "action": "SELL",
                "rungs": [
                    {"price": 0.90, "shares": 150},
                    {"price": 0.94, "shares": 100},
                ],
                "tags": {"purpose": "cash_rebuild"},
            },
            {
                "market_id": "test_buy_mkt",
                "outcome": "NO",
                "action": "BUY",
                "rungs": [{"price": 0.72, "shares": 200}],
                "tags": {"purpose": "runner"},
            },
        ],
    }


def _empty_live_orders():
    return {"as_of": "2026-06-10T12:00:00-06:00", "source": "test", "payload": []}


def _live_orders_payload(*orders):
    return {
        "as_of": "2026-06-10T12:00:00-06:00",
        "source": "test",
        "payload": list(orders),
    }


def _clob_order(order_id, asset_id, side, price, original_size, size_matched=0.0):
    return {
        "id": order_id,
        "asset_id": asset_id,
        "side": side,
        "price": str(price),
        "original_size": str(original_size),
        "size_matched": str(size_matched),
        "outcome": "NO",
    }


# ── end-to-end: --live-from with empty book ───────────────────────────────────

def test_empty_live_book_exit_zero(tmp_path, monkeypatch):
    reg = _write_yaml(tmp_path, "market_registry.yaml", _minimal_registry_yaml())
    target = _write_yaml(tmp_path, "target_ladders.yaml", _target_ladders_yaml())
    live = _write_json(tmp_path, "live_orders.json", _empty_live_orders())
    _patch_registry(monkeypatch, reg)

    rc = main(_plan_args(target, live))
    assert rc == 0


def test_empty_live_book_output_has_plan_and_preflight(tmp_path, monkeypatch, capsys):
    reg = _write_yaml(tmp_path, "market_registry.yaml", _minimal_registry_yaml())
    target = _write_yaml(tmp_path, "target_ladders.yaml", _target_ladders_yaml())
    live = _write_json(tmp_path, "live_orders.json", _empty_live_orders())
    _patch_registry(monkeypatch, reg)

    rc = main(_plan_args(target, live))
    assert rc == 0
    out = capsys.readouterr().out
    assert "### PLACE" in out
    assert "Pre-flight" in out or "PRE-FLIGHT" in out
    assert "3 place" in out  # 2 sell rungs + 1 buy rung


def test_partial_overlap_plan(tmp_path, monkeypatch, capsys):
    reg = _write_yaml(tmp_path, "market_registry.yaml", _minimal_registry_yaml())
    target = _write_yaml(tmp_path, "target_ladders.yaml", _target_ladders_yaml())
    live_payload = _live_orders_payload(
        _clob_order("ord_s1", "token_no_sell", "SELL", 0.90, 150),
    )
    live = _write_json(tmp_path, "live_orders.json", live_payload)
    _patch_registry(monkeypatch, reg)

    rc = main(_plan_args(target, live))
    assert rc == 0
    out = capsys.readouterr().out
    assert "### KEEP" in out
    assert "### PLACE" in out


# ── validation failure → exit 2 ───────────────────────────────────────────────

def test_sell_cap_validation_fail_exit_2(tmp_path, monkeypatch):
    reg = _write_yaml(tmp_path, "market_registry.yaml", _minimal_registry_yaml())
    bad_targets = {
        "schema_version": "1",
        "matching": {"price_tolerance": 0.0005, "shares_tolerance": 1.0},
        "ladders": [{
            "market_id": "test_sell_mkt",
            "outcome": "NO",
            "action": "SELL",
            "rungs": [{"price": 0.97, "shares": 100}],  # > 0.96 → sell-cap fail
        }],
    }
    target = _write_yaml(tmp_path, "target_ladders.yaml", bad_targets)
    live = _write_json(tmp_path, "live_orders.json", _empty_live_orders())
    _patch_registry(monkeypatch, reg)

    rc = main(_plan_args(target, live))
    assert rc == 2


def test_validation_fail_no_plan_table(tmp_path, monkeypatch, capsys):
    reg = _write_yaml(tmp_path, "market_registry.yaml", _minimal_registry_yaml())
    bad_targets = {
        "schema_version": "1",
        "matching": {"price_tolerance": 0.0005, "shares_tolerance": 1.0},
        "ladders": [{
            "market_id": "test_sell_mkt",
            "outcome": "NO",
            "action": "SELL",
            "rungs": [{"price": 0.97, "shares": 100}],
        }],
    }
    target = _write_yaml(tmp_path, "target_ladders.yaml", bad_targets)
    live = _write_json(tmp_path, "live_orders.json", _empty_live_orders())
    _patch_registry(monkeypatch, reg)

    main(_plan_args(target, live))
    out, err = capsys.readouterr()
    assert "### CANCEL" not in out
    assert "### PLACE" not in out
    assert "[hard fail]" in err
    assert "[sell-cap]" in err


# ── pre-flight in output ──────────────────────────────────────────────────────

def test_preflight_in_output_when_empty_book(tmp_path, monkeypatch, capsys):
    reg = _write_yaml(tmp_path, "market_registry.yaml", _minimal_registry_yaml())
    target = _write_yaml(tmp_path, "target_ladders.yaml", _target_ladders_yaml())
    live = _write_json(tmp_path, "live_orders.json", _empty_live_orders())
    _patch_registry(monkeypatch, reg)

    main(_plan_args(target, live))
    out = capsys.readouterr().out
    assert "balance-allowance/update" in out


# ── ladder execute ────────────────────────────────────────────────────────────

def _execute_args(target: Path, live: Path, log: Path, cash: str = "1000.0") -> list:
    return [
        "ladder", "execute",
        "--target", str(target),
        "--live-from", str(live),
        "--cash", cash,
        "--log", str(log),
    ]


def test_execute_nothing_to_do_when_live_matches_target(tmp_path, monkeypatch, capsys):
    reg = _write_yaml(tmp_path, "market_registry.yaml", _minimal_registry_yaml())
    target = _write_yaml(tmp_path, "target_ladders.yaml", _target_ladders_yaml())
    live_payload = _live_orders_payload(
        _clob_order("ord_s1", "token_no_sell", "SELL", 0.90, 150),
        _clob_order("ord_s2", "token_no_sell", "SELL", 0.94, 100),
        _clob_order("ord_b1", "token_no_buy", "BUY", 0.72, 200),
    )
    live = _write_json(tmp_path, "live_orders.json", live_payload)
    _patch_registry(monkeypatch, reg)

    rc = main(_execute_args(target, live, tmp_path / "log.jsonl"))
    assert rc == 0
    assert "Nothing to execute" in capsys.readouterr().out
    assert not (tmp_path / "log.jsonl").exists()


def test_execute_validation_fail_exit_2(tmp_path, monkeypatch):
    reg = _write_yaml(tmp_path, "market_registry.yaml", _minimal_registry_yaml())
    bad_targets = {
        "schema_version": "1",
        "matching": {"price_tolerance": 0.0005, "shares_tolerance": 1.0},
        "ladders": [{
            "market_id": "test_sell_mkt",
            "outcome": "NO",
            "action": "SELL",
            "rungs": [{"price": 0.97, "shares": 100}],
        }],
    }
    target = _write_yaml(tmp_path, "target_ladders.yaml", bad_targets)
    live = _write_json(tmp_path, "live_orders.json", _empty_live_orders())
    _patch_registry(monkeypatch, reg)

    rc = main(_execute_args(target, live, tmp_path / "log.jsonl"))
    assert rc == 2


def test_execute_missing_creds_exit_1(tmp_path, monkeypatch):
    import polyberg.cli as cli_module
    from polyberg.collectors.polymarket_account import AccountImportError

    reg = _write_yaml(tmp_path, "market_registry.yaml", _minimal_registry_yaml())
    target = _write_yaml(tmp_path, "target_ladders.yaml", _target_ladders_yaml())
    live = _write_json(tmp_path, "live_orders.json", _empty_live_orders())
    _patch_registry(monkeypatch, reg)

    def _raise(env=None):
        raise AccountImportError("Missing CLOB credentials in environment: all of them")

    monkeypatch.setattr(cli_module, "load_clob_credentials_from_env", _raise)

    rc = main(_execute_args(target, live, tmp_path / "log.jsonl"))
    assert rc == 1


def test_no_paste_suppresses_paste_block(tmp_path, monkeypatch, capsys):
    reg = _write_yaml(tmp_path, "market_registry.yaml", _minimal_registry_yaml())
    target = _write_yaml(tmp_path, "target_ladders.yaml", _target_ladders_yaml())
    live = _write_json(tmp_path, "live_orders.json", _empty_live_orders())
    _patch_registry(monkeypatch, reg)

    main(_plan_args(target, live, extra=["--no-paste"]))
    out = capsys.readouterr().out
    assert "PLACE|" not in out


# ── ladder plan --json (GUI seam) ─────────────────────────────────────────────

def test_plan_json_emits_structured_plan(tmp_path, monkeypatch, capsys):
    reg = _write_yaml(tmp_path, "market_registry.yaml", _minimal_registry_yaml())
    target = _write_yaml(tmp_path, "target_ladders.yaml", _target_ladders_yaml())
    live = _write_json(tmp_path, "live_orders.json", _empty_live_orders())
    _patch_registry(monkeypatch, reg)

    rc = main(_plan_args(target, live, extra=["--json"]))
    assert rc == 0
    out = capsys.readouterr().out
    doc = json.loads(out)
    assert doc["ok"] is True
    plan = doc["plan"]
    assert plan["summary"]["place"] == 3
    assert plan["preflight"]  # empty book + places → preflight required
    # stable indices + paste lines per action
    assert all("idx" in p and p["paste"].startswith("PLACE|") for p in plan["place"])


def test_plan_json_hard_fail_emits_error_object(tmp_path, monkeypatch, capsys):
    reg = _write_yaml(tmp_path, "market_registry.yaml", _minimal_registry_yaml())
    bad_targets = {
        "schema_version": "1",
        "matching": {"price_tolerance": 0.0005, "shares_tolerance": 1.0},
        "ladders": [{
            "market_id": "test_sell_mkt",
            "outcome": "NO",
            "action": "SELL",
            "rungs": [{"price": 0.97, "shares": 100}],
        }],
    }
    target = _write_yaml(tmp_path, "target_ladders.yaml", bad_targets)
    live = _write_json(tmp_path, "live_orders.json", _empty_live_orders())
    _patch_registry(monkeypatch, reg)

    rc = main(_plan_args(target, live, extra=["--json"]))
    assert rc == 2
    out, err = capsys.readouterr()
    assert json.loads(out) == {"ok": False, "exit_code": 2}
    assert "[hard fail]" in err  # GUI parses these for the banner


# ── ladder record-manual ──────────────────────────────────────────────────────

def test_record_manual_appends_confirmed_entry(tmp_path):
    log = tmp_path / "log.jsonl"
    rc = main([
        "ladder", "record-manual",
        "--market", "test_buy_mkt",
        "--outcome", "NO",
        "--side", "BUY",
        "--price", "0.72",
        "--shares", "200",
        "--log", str(log),
    ])
    assert rc == 0
    entry = json.loads(log.read_text(encoding="utf-8").strip())
    assert entry["status"] == "manual_confirmed"
    assert entry["action"] == "PLACE"
    assert entry["market_id"] == "test_buy_mkt"
    assert entry["order_id"] is None


# ── ladder cancel ─────────────────────────────────────────────────────────────

def test_cancel_logs_ok_on_success(tmp_path, monkeypatch):
    import polyberg.cli as cli_module

    monkeypatch.setattr(cli_module, "load_clob_credentials_from_env", lambda env=None: object())
    monkeypatch.setattr(
        "polyberg.ladder.clob_cancel.cancel_order",
        lambda creds, order_id, **kw: {"canceled": [order_id]},
    )
    log = tmp_path / "log.jsonl"
    rc = main(["ladder", "cancel", "--order-id", "ord_x", "--log", str(log)])
    assert rc == 0
    entry = json.loads(log.read_text(encoding="utf-8").strip())
    assert entry["status"] == "ok"
    assert entry["order_id"] == "ord_x"


def test_cancel_logs_http_error_and_exit_1(tmp_path, monkeypatch):
    import polyberg.cli as cli_module
    from polyberg.ladder.clob_cancel import ClobCancelError

    def _boom(creds, order_id, **kw):
        raise ClobCancelError("HTTP 400", status_code=400, excerpt="bad order")

    monkeypatch.setattr(cli_module, "load_clob_credentials_from_env", lambda env=None: object())
    monkeypatch.setattr("polyberg.ladder.clob_cancel.cancel_order", _boom)
    log = tmp_path / "log.jsonl"
    rc = main(["ladder", "cancel", "--order-id", "ord_x", "--log", str(log)])
    assert rc == 1
    entry = json.loads(log.read_text(encoding="utf-8").strip())
    assert entry["status"] == "http_error"


# ── ladder preflight ──────────────────────────────────────────────────────────

def test_preflight_prints_response_json(tmp_path, monkeypatch, capsys):
    import polyberg.cli as cli_module

    monkeypatch.setattr(cli_module, "load_clob_credentials_from_env", lambda env=None: object())
    monkeypatch.setattr(
        "polyberg.ladder.executor.fire_preflight",
        lambda creds, **kw: {"balance": "1000000"},
    )
    rc = main(["ladder", "preflight"])
    assert rc == 0
    assert json.loads(capsys.readouterr().out) == {"balance": "1000000"}
