"""Tests for import-account-snapshot credential routing (US vs international)."""
from __future__ import annotations

import argparse
from pathlib import Path

import pytest

import polyberg.cli as cli
from polyberg.collectors.polymarket_account import AccountImportError

US_KEY_VARS = ("POLYMARKET_US_API_KEY_ID", "POLYMARKET_US_SECRET_KEY")


@pytest.fixture()
def args(tmp_path: Path) -> argparse.Namespace:
    return argparse.Namespace(output_dir=tmp_path)


@pytest.fixture()
def no_us_keys(monkeypatch) -> None:
    for name in US_KEY_VARS:
        monkeypatch.delenv(name, raising=False)


def _fake_creds() -> object:
    return object()


def test_us_keys_take_the_us_path(monkeypatch, args, tmp_path):
    monkeypatch.setenv("POLYMARKET_US_API_KEY_ID", "key")
    written = tmp_path / "positions_raw.json"
    monkeypatch.setattr(
        cli, "write_authenticated_account_snapshot", lambda output_dir: [written]
    )
    assert cli.command_import_account_snapshot(args) == 0


def test_international_fallback_writes_all_three(monkeypatch, no_us_keys, args, tmp_path):
    monkeypatch.setenv("POLYMARKET_PROXY_WALLET", "0x" + "a" * 40)
    calls: list[str] = []
    monkeypatch.setattr(cli, "load_clob_credentials_from_env", _fake_creds)
    monkeypatch.setattr(
        cli,
        "write_public_positions",
        lambda wallet, path: calls.append("positions") or path,
    )
    monkeypatch.setattr(
        cli,
        "write_clob_open_orders",
        lambda creds, path: calls.append("orders") or path,
    )
    monkeypatch.setattr(
        cli, "write_clob_balance", lambda creds, path: calls.append("balance") or path
    )

    assert cli.command_import_account_snapshot(args) == 0
    assert calls == ["positions", "orders", "balance"]


def test_no_credentials_at_all_fails_with_pointer(monkeypatch, no_us_keys, args, capsys):
    def raise_missing() -> object:
        raise AccountImportError("Missing CLOB credentials in environment: ...")

    monkeypatch.setattr(cli, "load_clob_credentials_from_env", raise_missing)
    assert cli.command_import_account_snapshot(args) == 1
    err = capsys.readouterr().err
    assert "POLYMARKET_US_API_KEY_ID" in err
    assert "CLOB" in err


def test_partial_failure_still_succeeds_with_skip_notes(
    monkeypatch, no_us_keys, args, capsys
):
    monkeypatch.setenv("POLYMARKET_PROXY_WALLET", "0x" + "a" * 40)
    monkeypatch.setattr(cli, "load_clob_credentials_from_env", _fake_creds)
    monkeypatch.setattr(cli, "write_public_positions", lambda wallet, path: path)
    monkeypatch.setattr(cli, "write_clob_open_orders", lambda creds, path: path)

    def balance_fails(creds, path):
        raise AccountImportError("HTTP 500 while reading /balance-allowance")

    monkeypatch.setattr(cli, "write_clob_balance", balance_fails)

    assert cli.command_import_account_snapshot(args) == 0
    err = capsys.readouterr().err
    assert "[skip] balance" in err


def test_missing_wallet_skips_positions_only(monkeypatch, no_us_keys, args, capsys):
    monkeypatch.delenv("POLYMARKET_PROXY_WALLET", raising=False)
    monkeypatch.setattr(cli, "_resolve_proxy_wallet", lambda: "")
    monkeypatch.setattr(cli, "load_clob_credentials_from_env", _fake_creds)
    monkeypatch.setattr(cli, "write_clob_open_orders", lambda creds, path: path)
    monkeypatch.setattr(cli, "write_clob_balance", lambda creds, path: path)

    assert cli.command_import_account_snapshot(args) == 0
    err = capsys.readouterr().err
    assert "[skip] positions" in err
    assert "live_state.local.yaml" in err


def test_resolve_proxy_wallet_prefers_env(monkeypatch):
    monkeypatch.setenv("POLYMARKET_PROXY_WALLET", "0x" + "b" * 40)
    assert cli._resolve_proxy_wallet() == "0x" + "b" * 40
