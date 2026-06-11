"""Tests for ladder executor + mutating cancel client (no real HTTP)."""
from __future__ import annotations

import base64
import io
import json
from urllib.error import HTTPError

import pytest

from polyberg.collectors.polymarket_account import InvalidJsonResponseError
from polyberg.collectors.polymarket_clob_auth import (
    ClobCredentials,
    build_hmac_signature,
)
from polyberg.ladder.clob_cancel import (
    ClobCancelError,
    MutatingClobClient,
    cancel_order,
)
from polyberg.ladder.diff import CancelAction, LadderPlan, PlaceAction
from polyberg.ladder.executor import append_order_log, execute_plan, fire_preflight

FROZEN_TS = 1_700_000_000
SECRET = base64.urlsafe_b64encode(b"super-secret-hmac-key").decode("utf-8")


def _creds() -> ClobCredentials:
    return ClobCredentials(
        address="0x" + "ab" * 20,
        api_key="test-api-key",
        api_secret=SECRET,
        api_passphrase="test-passphrase",
    )


def _frozen_clock() -> int:
    return FROZEN_TS


# ── fakes ─────────────────────────────────────────────────────────────────────

class FakeResponse:
    def __init__(self, payload: dict) -> None:
        self._raw = json.dumps(payload).encode("utf-8")

    def read(self) -> bytes:
        return self._raw

    def __enter__(self):
        return self

    def __exit__(self, *exc_info) -> bool:
        return False


class ScriptedOpener:
    """Captures requests; pops one scripted result (response dict or exception) per call."""

    def __init__(self, results: list) -> None:
        self.results = list(results)
        self.requests: list = []

    def __call__(self, request, timeout=None):
        self.requests.append(request)
        result = self.results.pop(0)
        if isinstance(result, Exception):
            raise result
        return FakeResponse(result)


class FakePreflightHttp:
    """Stands in for ReadOnlyHttpClient; records get_json calls into an event list."""

    def __init__(self, events: list | None = None) -> None:
        self.events = events if events is not None else []
        self.calls: list[tuple] = []

    def get_json(self, path, params=None, headers=None):
        self.calls.append((path, params, headers))
        self.events.append(("preflight", path))
        return {"balance": "0"}


def _http_error(code: int = 400, body: bytes = b'{"error":"bad order id"}') -> HTTPError:
    return HTTPError(
        "https://clob.polymarket.com/order", code, "Bad Request", None, io.BytesIO(body)
    )


def _cancel(order_id: str = "ord_1", price: float = 0.90, shares: float = 150.0) -> CancelAction:
    return CancelAction(
        order_id=order_id,
        market_id="test_sell_mkt",
        outcome="NO",
        action="SELL",
        price=price,
        shares=shares,
        reason="not_in_target",
    )


def _place(price: float = 0.72, shares: float = 200.0) -> PlaceAction:
    return PlaceAction(
        market_id="test_buy_mkt",
        outcome="NO",
        action="BUY",
        price=price,
        shares=shares,
        purpose="runner",
    )


def _confirm_script(answers: list[str]):
    queue = list(answers)
    prompts: list[str] = []

    def confirm(prompt: str) -> str:
        prompts.append(prompt)
        return queue.pop(0)

    confirm.prompts = prompts
    return confirm


def _read_log(log_path) -> list[dict]:
    return [json.loads(line) for line in log_path.read_text(encoding="utf-8").splitlines()]


# ── cancel_order / MutatingClobClient ─────────────────────────────────────────

def test_cancel_y_sends_delete_with_correct_headers_and_body(tmp_path):
    opener = ScriptedOpener([{"canceled": ["ord_1"]}])
    client = MutatingClobClient(opener=opener)
    plan = LadderPlan(cancel=[_cancel("ord_1")])

    rc = execute_plan(
        plan,
        _creds(),
        tmp_path / "log.jsonl",
        confirm=_confirm_script(["y"]),
        cancel_client=client,
        timestamp_seconds=_frozen_clock,
    )

    assert rc == 0
    assert len(opener.requests) == 1
    request = opener.requests[0]
    assert request.get_method() == "DELETE"
    assert request.full_url == "https://clob.polymarket.com/order"
    expected_body = '{"orderID": "ord_1"}'
    assert request.data == expected_body.encode("utf-8")

    expected_signature = build_hmac_signature(
        SECRET, FROZEN_TS, "DELETE", "/order", expected_body
    )
    assert request.headers["POLY_ADDRESS"] == "0x" + "ab" * 20
    assert request.headers["POLY_SIGNATURE"] == expected_signature
    assert request.headers["POLY_TIMESTAMP"] == str(FROZEN_TS)
    assert request.headers["POLY_API_KEY"] == "test-api-key"
    assert request.headers["POLY_PASSPHRASE"] == "test-passphrase"

    entries = _read_log(tmp_path / "log.jsonl")
    assert len(entries) == 1
    assert entries[0]["status"] == "ok"
    assert entries[0]["order_id"] == "ord_1"


def test_cancel_n_makes_no_http_call_and_logs_declined(tmp_path):
    opener = ScriptedOpener([])
    plan = LadderPlan(cancel=[_cancel("ord_1")])

    rc = execute_plan(
        plan,
        _creds(),
        tmp_path / "log.jsonl",
        confirm=_confirm_script(["n"]),
        cancel_client=MutatingClobClient(opener=opener),
        timestamp_seconds=_frozen_clock,
    )

    assert rc == 0
    assert opener.requests == []
    entries = _read_log(tmp_path / "log.jsonl")
    assert entries[0]["status"] == "declined"


def test_http_error_logged_walk_continues_exit_nonzero(tmp_path, capsys):
    opener = ScriptedOpener([_http_error(), {"canceled": ["ord_2"]}])
    plan = LadderPlan(cancel=[_cancel("ord_1", price=0.90), _cancel("ord_2", price=0.94)])

    rc = execute_plan(
        plan,
        _creds(),
        tmp_path / "log.jsonl",
        confirm=_confirm_script(["y", "y"]),
        cancel_client=MutatingClobClient(opener=opener),
        timestamp_seconds=_frozen_clock,
    )

    assert rc != 0
    assert len(opener.requests) == 2  # walk continued past the failure
    entries = _read_log(tmp_path / "log.jsonl")
    assert entries[0]["status"] == "http_error"
    assert "bad order id" in entries[0]["response_excerpt"]
    assert entries[1]["status"] == "ok"
    assert "HTTP 400" in capsys.readouterr().err


def test_mutating_client_rejects_other_paths():
    client = MutatingClobClient(opener=ScriptedOpener([]))
    with pytest.raises(ClobCancelError):
        client.delete_json("/orders", "{}", {})


def test_cancel_order_raises_clob_cancel_error_on_http_error():
    opener = ScriptedOpener([_http_error(code=500, body=b"oops")])
    with pytest.raises(ClobCancelError) as excinfo:
        cancel_order(
            _creds(),
            "ord_x",
            http=MutatingClobClient(opener=opener),
            timestamp_seconds=_frozen_clock,
        )
    assert excinfo.value.status_code == 500
    assert "oops" in excinfo.value.excerpt


# ── pre-flight ────────────────────────────────────────────────────────────────

def test_preflight_get_fires_before_first_action_when_places_exist(tmp_path):
    events: list = []

    class EventOpener(ScriptedOpener):
        def __call__(self, request, timeout=None):
            events.append(("delete", request.full_url))
            return super().__call__(request, timeout)

    opener = EventOpener([{"canceled": ["ord_1"]}])
    preflight = FakePreflightHttp(events)
    plan = LadderPlan(cancel=[_cancel("ord_1")], place=[_place()])

    rc = execute_plan(
        plan,
        _creds(),
        tmp_path / "log.jsonl",
        confirm=_confirm_script(["y", "y"]),
        cancel_client=MutatingClobClient(opener=opener),
        preflight_http=preflight,
        timestamp_seconds=_frozen_clock,
    )

    assert rc == 0
    assert events[0] == ("preflight", "/balance-allowance/update")
    assert events[1][0] == "delete"


def test_no_preflight_when_no_places(tmp_path):
    preflight = FakePreflightHttp()
    plan = LadderPlan(cancel=[_cancel("ord_1")])

    execute_plan(
        plan,
        _creds(),
        tmp_path / "log.jsonl",
        confirm=_confirm_script(["n"]),
        cancel_client=MutatingClobClient(opener=ScriptedOpener([])),
        preflight_http=preflight,
        timestamp_seconds=_frozen_clock,
    )

    assert preflight.calls == []


def test_fire_preflight_params_and_path():
    preflight = FakePreflightHttp()
    fire_preflight(_creds(), http=preflight, timestamp_seconds=_frozen_clock, env={})
    path, params, headers = preflight.calls[0]
    assert path == "/balance-allowance/update"
    assert params == {"asset_type": "COLLATERAL", "signature_type": 1}
    assert headers["POLY_TIMESTAMP"] == str(FROZEN_TS)


def test_fire_preflight_tolerates_non_json_200_body():
    """The live endpoint returns an empty/plain-text body on HTTP 200 — that
    must count as a successful pre-flight, not a failure."""

    class NonJsonHttp(FakePreflightHttp):
        def get_json(self, path, params=None, headers=None):
            super().get_json(path, params, headers)
            raise InvalidJsonResponseError("Invalid JSON response from url", raw_text="OK")

    result = fire_preflight(
        _creds(), http=NonJsonHttp(), timestamp_seconds=_frozen_clock, env={}
    )
    assert result == "OK"


def test_execute_plan_preflight_ok_on_non_json_body(tmp_path, capsys):
    class NonJsonHttp(FakePreflightHttp):
        def get_json(self, path, params=None, headers=None):
            super().get_json(path, params, headers)
            raise InvalidJsonResponseError("Invalid JSON response from url", raw_text="")

    plan = LadderPlan(place=[_place()])
    rc = execute_plan(
        plan,
        _creds(),
        tmp_path / "log.jsonl",
        confirm=_confirm_script(["skip"]),
        preflight_http=NonJsonHttp(),
        timestamp_seconds=_frozen_clock,
    )
    assert rc == 0
    assert "Pre-flight OK." in capsys.readouterr().out


# ── placements (manual walk) ──────────────────────────────────────────────────

def test_place_manual_confirmed_skip_and_declined(tmp_path, capsys):
    preflight = FakePreflightHttp()
    plan = LadderPlan(place=[_place(0.70), _place(0.72), _place(0.74)])

    rc = execute_plan(
        plan,
        _creds(),
        tmp_path / "log.jsonl",
        confirm=_confirm_script(["y", "skip", "n"]),
        preflight_http=preflight,
        timestamp_seconds=_frozen_clock,
    )

    assert rc == 0
    out = capsys.readouterr().out
    assert "PLACE|test_buy_mkt|NO|BUY|0.7000|200.0|limit|" in out  # paste line printed
    entries = _read_log(tmp_path / "log.jsonl")
    assert [e["status"] for e in entries] == ["manual_confirmed", "skipped", "declined"]
    assert all(e["order_id"] is None for e in entries)
    assert all(e["action"] == "PLACE" for e in entries)


# ── log shape / misc ──────────────────────────────────────────────────────────

def test_jsonl_entry_shape(tmp_path):
    opener = ScriptedOpener([{"canceled": ["ord_1"]}])
    preflight = FakePreflightHttp()
    plan = LadderPlan(cancel=[_cancel("ord_1")], place=[_place()])

    execute_plan(
        plan,
        _creds(),
        tmp_path / "log.jsonl",
        confirm=_confirm_script(["y", "y"]),
        cancel_client=MutatingClobClient(opener=opener),
        preflight_http=preflight,
        timestamp_seconds=_frozen_clock,
    )

    entries = _read_log(tmp_path / "log.jsonl")
    expected_keys = {
        "ts", "action", "market_id", "outcome", "side",
        "price", "shares", "order_id", "status", "response_excerpt",
    }
    assert len(entries) == 2
    for entry in entries:
        assert set(entry.keys()) == expected_keys
    cancel_entry = entries[0]
    assert cancel_entry["action"] == "CANCEL"
    assert cancel_entry["side"] == "SELL"
    assert cancel_entry["outcome"] == "NO"


def test_append_order_log_is_append_only(tmp_path):
    log = tmp_path / "log.jsonl"
    append_order_log(log, {"a": 1})
    append_order_log(log, {"b": 2})
    assert _read_log(log) == [{"a": 1}, {"b": 2}]


def test_empty_plan_nothing_to_execute(tmp_path, capsys):
    rc = execute_plan(
        LadderPlan(),
        _creds(),
        tmp_path / "log.jsonl",
        confirm=_confirm_script([]),
    )
    assert rc == 0
    assert "Nothing to execute" in capsys.readouterr().out
    assert not (tmp_path / "log.jsonl").exists()
