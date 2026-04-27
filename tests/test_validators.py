from __future__ import annotations

import json

import pytest

from polymarket_desk.validators import (
    ResponseValidationError,
    validate_adjudicator_output,
    validate_model_response,
)


def good_model_response() -> dict:
    return {
        "as_of": "2026-04-26T09:00:00-06:00",
        "agent_role": "aggressive_trader",
        "candidate_trades": [
            {
                "market_id": "trump_blockade_lifted_apr30",
                "market_name": "Trump blockade lifted by Apr 30",
                "side": "NO",
                "current_mark": 0.915,
                "recommendation": "hold_and_sell_ladder",
                "confidence": 0.78,
                "rule_edge": (
                    "Requires explicit official announcement that blockade lifted; "
                    "resumed shipping alone does not count."
                ),
                "opposing_side_wins_if": (
                    "Trump or the US government explicitly announces the blockade has ended."
                ),
                "correlation": "high",
                "source_quality": "official_resolution_source",
                "thesis_invalidated_if": [
                    "A qualifying official statement says the blockade has ended."
                ],
                "risk_flags": ["Trump social post can qualify", "media fallback exists"],
                "buy_orders": [],
                "sell_orders": [
                    {
                        "price": 0.94,
                        "shares": 15,
                        "order_type": "limit",
                        "rationale": "Reduce deadline risk.",
                    }
                ],
                "catalysts": ["Apr 30 resolution deadline"],
                "missing_info": ["current order book depth"],
                "human_review_required": True,
            }
        ],
    }


def write_json(tmp_path, payload: dict):
    path = tmp_path / "payload.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def test_validating_good_model_response(tmp_path) -> None:
    path = write_json(tmp_path, good_model_response())
    validate_model_response(path)


def test_rejecting_malformed_model_response(tmp_path) -> None:
    payload = good_model_response()
    del payload["candidate_trades"][0]["rule_edge"]
    path = write_json(tmp_path, payload)

    with pytest.raises(ResponseValidationError, match="rule_edge"):
        validate_model_response(path)


def test_model_output_rejects_invalid_side(tmp_path) -> None:
    payload = good_model_response()
    payload["candidate_trades"][0]["side"] = "MAYBE"
    path = write_json(tmp_path, payload)

    with pytest.raises(ResponseValidationError, match="YES"):
        validate_model_response(path)


def test_model_output_rejects_price_greater_than_one(tmp_path) -> None:
    payload = good_model_response()
    payload["candidate_trades"][0]["buy_orders"] = [
        {"price": 1.01, "shares": 1, "order_type": "limit", "rationale": "test"}
    ]
    path = write_json(tmp_path, payload)

    with pytest.raises(ResponseValidationError, match="greater than"):
        validate_model_response(path)


def test_model_output_rejects_unknown_market_id(tmp_path) -> None:
    payload = good_model_response()
    payload["candidate_trades"][0]["market_id"] = "unknown_market"
    path = write_json(tmp_path, payload)

    with pytest.raises(ResponseValidationError, match="unknown market_id"):
        validate_model_response(path)


def test_model_output_rejects_market_name_mismatch(tmp_path) -> None:
    payload = good_model_response()
    payload["candidate_trades"][0]["market_name"] = "Wrong market"
    path = write_json(tmp_path, payload)

    with pytest.raises(ResponseValidationError, match="expected"):
        validate_model_response(path)


def test_model_output_rejects_naive_as_of(tmp_path) -> None:
    payload = good_model_response()
    payload["as_of"] = "2026-04-26T09:00:00"
    path = write_json(tmp_path, payload)

    with pytest.raises(ResponseValidationError, match="timezone"):
        validate_model_response(path)


def test_adjudicator_schema_requires_human_review_true(tmp_path) -> None:
    payload = {
        "as_of": "2026-04-26T09:00:00-06:00",
        "agreed_trades": [],
        "disputed_trades": [],
        "rejected_trades": [],
        "final_order_list": [
            {
                "market_id": "trump_blockade_lifted_apr30",
                "market_name": "Trump blockade lifted by Apr 30",
                "side": "NO",
                "action": "sell_limit",
                "price": 0.94,
                "shares": 15,
                "rationale": "Reduce deadline risk.",
                "source_model_support": ["model_a", "model_b"],
                "human_review_required": False,
            }
        ],
        "invalidation_triggers": ["Official announcement invalidates NO thesis."],
        "missing_info_checklist": [],
        "adjudicator_notes": ["Human review required before any action."],
    }
    path = write_json(tmp_path, payload)

    with pytest.raises(ResponseValidationError, match="True"):
        validate_adjudicator_output(path)


def test_adjudicator_schema_rejects_zero_share_final_order(tmp_path) -> None:
    payload = {
        "as_of": "2026-04-26T09:00:00-06:00",
        "agreed_trades": [],
        "disputed_trades": [],
        "rejected_trades": [],
        "final_order_list": [
            {
                "market_id": "trump_blockade_lifted_apr30",
                "market_name": "Trump blockade lifted by Apr 30",
                "side": "NO",
                "action": "sell_limit",
                "price": 0.94,
                "shares": 0,
                "rationale": "Reduce deadline risk.",
                "source_model_support": ["both"],
                "human_review_required": True,
            }
        ],
        "invalidation_triggers": ["Official announcement invalidates NO thesis."],
        "missing_info_checklist": [],
        "adjudicator_notes": ["Human review required before any action."],
    }
    path = write_json(tmp_path, payload)

    with pytest.raises(ResponseValidationError, match="less than or equal to"):
        validate_adjudicator_output(path)


def test_adjudicator_schema_rejects_empty_model_support(tmp_path) -> None:
    payload = {
        "as_of": "2026-04-26T09:00:00-06:00",
        "agreed_trades": [],
        "disputed_trades": [],
        "rejected_trades": [],
        "final_order_list": [
            {
                "market_id": "trump_blockade_lifted_apr30",
                "market_name": "Trump blockade lifted by Apr 30",
                "side": "NO",
                "action": "sell_limit",
                "price": 0.94,
                "shares": 15,
                "rationale": "Reduce deadline risk.",
                "source_model_support": [],
                "human_review_required": True,
            }
        ],
        "invalidation_triggers": ["Official announcement invalidates NO thesis."],
        "missing_info_checklist": [],
        "adjudicator_notes": ["Human review required before any action."],
    }
    path = write_json(tmp_path, payload)

    with pytest.raises(ResponseValidationError, match="should be non-empty"):
        validate_adjudicator_output(path)
