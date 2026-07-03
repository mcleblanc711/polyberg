from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator, FormatChecker

from polyberg.config import repo_path
from polyberg.loaders import load_market_registry


class ResponseValidationError(RuntimeError):
    pass


def load_json(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise ResponseValidationError(f"Unable to read JSON file {path}: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise ResponseValidationError(f"Invalid JSON in {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise ResponseValidationError(f"Expected top-level JSON object in {path}")
    return data


def load_schema(path: Path) -> dict[str, Any]:
    try:
        schema = json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise ResponseValidationError(f"Unable to read schema {path}: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise ResponseValidationError(f"Invalid schema JSON in {path}: {exc}") from exc
    if not isinstance(schema, dict):
        raise ResponseValidationError(f"Expected top-level schema object in {path}")
    return schema


def validate_payload(payload: dict[str, Any], schema_path: Path, source: str) -> None:
    """Validate an in-memory payload; source names it in error messages."""
    schema = load_schema(schema_path)
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    errors = sorted(validator.iter_errors(payload), key=lambda err: list(err.absolute_path))
    if errors:
        details = "\n".join(format_error(error) for error in errors)
        raise ResponseValidationError(f"Validation failed for {source}:\n{details}")


def validate_json_file(json_path: Path, schema_path: Path) -> None:
    payload = load_json(json_path)
    validate_payload(payload, schema_path, str(json_path))


def validate_canonical_session_payload(
    payload: dict[str, Any], source: str = "canonical_session payload"
) -> None:
    """In-memory contract check, run BEFORE any session file or dir is written."""
    validate_payload(payload, repo_path("schemas", "canonical_session.schema.json"), source)


def validate_canonical_session(json_path: Path) -> None:
    payload = load_json(json_path)
    validate_payload(
        payload, repo_path("schemas", "canonical_session.schema.json"), str(json_path)
    )


def validate_model_response(json_path: Path) -> None:
    payload = load_json(json_path)
    validate_json_file(json_path, repo_path("schemas", "model_trade_response.schema.json"))
    validate_timezone_aware_as_of(payload, json_path)
    validate_model_market_references(payload, json_path)


def validate_adjudicator_output(json_path: Path) -> None:
    payload = load_json(json_path)
    validate_json_file(json_path, repo_path("schemas", "adjudicator_output.schema.json"))
    validate_timezone_aware_as_of(payload, json_path)
    validate_adjudicator_market_references(payload, json_path)


def validate_market_snapshot(json_path: Path) -> None:
    payload = load_json(json_path)
    validate_json_file(json_path, repo_path("schemas", "market_snapshot.schema.json"))
    validate_timezone_aware_as_of(payload, json_path)


def validate_timezone_aware_as_of(payload: dict[str, Any], json_path: Path) -> None:
    value = payload.get("as_of")
    if not isinstance(value, str):
        return
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ResponseValidationError(
            f"Validation failed for {json_path}: as_of is not a valid ISO datetime: {exc}"
        ) from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ResponseValidationError(
            f"Validation failed for {json_path}: as_of must include timezone"
        )


def validate_model_market_references(payload: dict[str, Any], json_path: Path) -> None:
    registry = load_market_registry()
    names_by_id = {market.market_id: market.name for market in registry.markets}
    errors = []
    for index, trade in enumerate(payload.get("candidate_trades", [])):
        market_id = trade.get("market_id")
        market_name = trade.get("market_name")
        if market_id not in names_by_id:
            errors.append(f"- $['candidate_trades'][{index}]['market_id']: unknown market_id")
            continue
        if market_name != names_by_id[market_id]:
            errors.append(
                f"- $['candidate_trades'][{index}]['market_name']: expected "
                f"{names_by_id[market_id]!r} for market_id {market_id!r}"
            )
    if errors:
        raise ResponseValidationError(
            f"Business validation failed for {json_path}:\n" + "\n".join(errors)
        )


def validate_adjudicator_market_references(payload: dict[str, Any], json_path: Path) -> None:
    registry = load_market_registry()
    known_ids = registry.market_ids
    errors = []
    for section in ["agreed_trades", "disputed_trades", "rejected_trades", "final_order_list"]:
        for index, item in enumerate(payload.get(section, [])):
            market_id = item.get("market_id")
            if market_id not in known_ids:
                errors.append(f"- $['{section}'][{index}]['market_id']: unknown market_id")
    if errors:
        raise ResponseValidationError(
            f"Business validation failed for {json_path}:\n" + "\n".join(errors)
        )


def format_error(error: Any) -> str:
    location = "$"
    if error.absolute_path:
        location += "".join(f"[{part!r}]" for part in error.absolute_path)
    return f"- {location}: {error.message}"
