from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from polyberg.cli import build_parser
from polyberg.config import windows_safe_timestamp
from polyberg.snapshots import build_market_snapshot, diff_snapshots
from polyberg.trade_ticket import build_trade_ticket
from polyberg.validators import ResponseValidationError


def write_json(tmp_path, name: str, payload: dict):
    path = tmp_path / name
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def adjudicator_payload(human_review_required: bool = True) -> dict:
    return {
        "as_of": "2026-04-26T09:00:00-06:00",
        "agreed_trades": [],
        "disputed_trades": [],
        "rejected_trades": [
            {
                "market_id": "hormuz_normal_end_june",
                "rationale": "Rejected until rule gap is checked.",
            }
        ],
        "final_order_list": [
            {
                "market_id": "hormuz_normal_jul31",
                "side": "NO",
                "action": "sell_ladder",
                "price": 0.94,
                "shares": 15,
                "rationale": "Reduce deadline and liquidity risk.",
                "source_model_support": "both",
                "human_review_required": human_review_required,
            }
        ],
        "invalidation_triggers": ["Official announcement invalidates NO thesis."],
        "missing_info_checklist": ["Check current order book depth."],
        "adjudicator_notes": ["Liquidity should be reviewed manually."],
    }


def test_windows_safe_timestamp_has_no_colons() -> None:
    stamp = windows_safe_timestamp(datetime(2026, 4, 26, 9, 0, tzinfo=ZoneInfo("UTC")), "UTC")

    assert stamp == "2026-04-26_0900"
    assert ":" not in stamp


def test_tzdata_dependency_exists_for_windows() -> None:
    text = Path("pyproject.toml").read_text(encoding="utf-8")

    assert "tzdata; sys_platform == 'win32'" in text


def test_cli_exposes_no_execution_commands() -> None:
    parser = build_parser()
    subparser_actions = [
        action for action in parser._actions if getattr(action, "choices", None)
    ]
    commands = set(subparser_actions[0].choices)
    forbidden_terms = {"place", "create", "cancel", "modify", "execute", "wallet", "private"}

    assert not any(term in command for command in commands for term in forbidden_terms)


def test_trade_ticket_generation(tmp_path) -> None:
    source = write_json(tmp_path, "adjudicator.json", adjudicator_payload())
    output = tmp_path / "trade_ticket.md"

    build_trade_ticket(source, output)
    text = output.read_text(encoding="utf-8")

    assert "HUMAN REVIEW REQUIRED" in text
    assert "No orders were placed" in text
    assert "Estimated proceeds" in text


def test_trade_ticket_emits_ledger_json_sibling(tmp_path) -> None:
    source = write_json(tmp_path, "adjudicator.json", adjudicator_payload())
    output = tmp_path / "trade_ticket.md"

    build_trade_ticket(source, output)

    json_path = output.with_suffix(".json")
    assert json_path.exists()
    ticket = json.loads(json_path.read_text(encoding="utf-8"))

    assert ticket["schema_version"] == "1"
    assert ticket["source"] == "polyberg-adjudicator"
    assert ticket["human_review_required"] is True
    assert len(ticket["decisions"]) == 1

    decision = ticket["decisions"][0]
    assert decision["market_id"] == "hormuz_normal_jul31"
    assert decision["side"] == "NO"
    assert decision["intent"] == "sell_ladder"
    assert decision["decision_type"] == "EXIT"
    assert decision["price_used"] == 0.94
    assert decision["max_allocation"] == pytest.approx(0.94 * 15)
    assert decision["status"] == "DRAFT"

    # source_model_support is carried verbatim; no enum mapping on this side.
    assert decision["attributions"][0]["source_model_support"] == "both"
    assert decision["attributions"][0]["recommended_size"] == 15

    assert ticket["rejected"][0]["market_id"] == "hormuz_normal_end_june"


def test_trade_ticket_rejects_false_human_review(tmp_path) -> None:
    source = write_json(tmp_path, "adjudicator.json", adjudicator_payload(False))

    with pytest.raises(ResponseValidationError):
        build_trade_ticket(source, tmp_path / "ticket.md")


def test_trade_ticket_includes_nonstandard_final_order_action(tmp_path) -> None:
    payload = adjudicator_payload()
    payload["final_order_list"][0]["action"] = "trim_exposure"
    source = write_json(tmp_path, "adjudicator.json", payload)
    output = tmp_path / "trade_ticket.md"

    build_trade_ticket(source, output)
    text = output.read_text(encoding="utf-8")

    assert "All Final Orders Requiring Human Review" in text
    assert "Other Final Orders" in text
    assert "trim_exposure" in text


def test_snapshot_markets_records_api_errors_in_missing_info(tmp_path) -> None:
    output = tmp_path / "markets_2026-04-26_0900.json"

    class AlwaysFailClient:
        def get_json(self, *_a, **_kw):
            from polyberg.collectors.polymarket_account import AccountImportError

            raise AccountImportError("HTTP 503 simulated")

    build_market_snapshot(output, http=AlwaysFailClient())  # type: ignore[arg-type]
    data = json.loads(output.read_text(encoding="utf-8"))

    assert data["markets"]
    assert data["markets"][0]["missing_info"]


def test_snapshot_diff_price_liquidity_and_missing_market(tmp_path) -> None:
    old = write_json(
        tmp_path,
        "old.json",
        {
            "as_of": "2026-04-26T09:00:00-06:00",
            "markets": [
                {
                    "market_id": "hormuz_normal_may15",
                    "yes_price": 0.4,
                    "no_price": 0.6,
                    "best_bid_yes": None,
                    "best_ask_yes": None,
                    "best_bid_no": None,
                    "best_ask_no": None,
                    "spread": 0.02,
                    "orderbook_depth_top": None,
                    "liquidity_warning": False,
                    "missing_info": [],
                },
                {
                    "market_id": "cl_high_120_end_june",
                    "yes_price": None,
                    "no_price": None,
                    "best_bid_yes": None,
                    "best_ask_yes": None,
                    "best_bid_no": None,
                    "best_ask_no": None,
                    "spread": None,
                    "orderbook_depth_top": None,
                    "liquidity_warning": True,
                    "missing_info": ["missing token"],
                },
            ],
        },
    )
    new = write_json(
        tmp_path,
        "new.json",
        {
            "as_of": "2026-04-26T10:00:00-06:00",
            "markets": [
                {
                    "market_id": "hormuz_normal_may15",
                    "yes_price": 0.45,
                    "no_price": 0.55,
                    "best_bid_yes": None,
                    "best_ask_yes": None,
                    "best_bid_no": None,
                    "best_ask_no": None,
                    "spread": 0.03,
                    "orderbook_depth_top": None,
                    "liquidity_warning": True,
                    "missing_info": ["depth missing"],
                }
            ],
        },
    )

    text = diff_snapshots(old, new)

    assert "yes_price: 0.4 -> 0.45" in text
    assert "liquidity_warning: False -> True" in text
    assert "Markets removed: cl_high_120_end_june" in text
