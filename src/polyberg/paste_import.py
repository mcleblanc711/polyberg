"""Canonical-JSON paste-import pipeline.

For users who don't want to mint CLOB credentials or who need to override
the on-chain importers manually, this module lets pre-formatted JSON
matching the canonical Pydantic schemas land directly in
``context/portfolio_current.yaml`` or ``context/open_orders.yaml``.

The flow is intentionally strict: the JSON must already match the canonical
schema (Portfolio / OpenOrders). No field mapping happens here — that's
the normalizer's job for API-shaped inputs. Pasted JSON is expected to
come from a downstream tool (typically an LLM that has been given the
schema as part of its prompt).
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Literal

from pydantic import ValidationError

from polyberg.account_normalizer import (
    _dump_open_orders_yaml,
    _dump_portfolio_yaml,
    _read_existing_thesis_buckets,
)
from polyberg.config import get_timezone
from polyberg.loaders import load_market_registry
from polyberg.models import OpenOrders, Portfolio

PasteKind = Literal["portfolio", "orders"]


class PasteImportError(RuntimeError):
    pass


def import_paste(
    kind: PasteKind,
    raw_text: str,
    output_path: Path,
    dry_run: bool = False,
    registry_path: Path | None = None,
    portfolio_path_for_thesis: Path | None = None,
    now: datetime | None = None,
) -> str:
    """Validate ``raw_text`` as canonical JSON and write the resulting YAML.

    Returns the YAML text that was (or would be, on ``dry_run``) written so
    the caller can preview it. Raises :class:`PasteImportError` on JSON
    parse failures, Pydantic validation errors, or market_id mismatches
    against the registry.
    """
    try:
        doc = json.loads(raw_text)
    except json.JSONDecodeError as exc:
        raise PasteImportError(f"Invalid JSON: {exc}") from exc

    if not isinstance(doc, dict):
        raise PasteImportError(
            f"Top-level value must be an object, got {type(doc).__name__}"
        )

    # Default as_of so the LLM doesn't have to invent a timestamp. The user
    # can override by including as_of explicitly.
    if "as_of" not in doc:
        doc = dict(doc)
        doc["as_of"] = (now or datetime.now(get_timezone())).isoformat()

    registry = load_market_registry(registry_path)
    valid_market_ids = registry.market_ids

    if kind == "portfolio":
        yaml_text = _validate_portfolio(
            doc, valid_market_ids, portfolio_path_for_thesis=portfolio_path_for_thesis
        )
    elif kind == "orders":
        yaml_text = _validate_orders(doc, valid_market_ids)
    else:
        raise PasteImportError(f"Unknown paste kind: {kind}")

    if not dry_run:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(yaml_text, encoding="utf-8")
    return yaml_text


def _validate_portfolio(
    doc: dict, valid_market_ids: set[str], portfolio_path_for_thesis: Path | None
) -> str:
    try:
        portfolio = Portfolio.model_validate(doc)
    except ValidationError as exc:
        raise PasteImportError(_format_validation_error(exc, "Portfolio")) from exc

    unknown = [p.market_id for p in portfolio.positions if p.market_id not in valid_market_ids]
    if unknown:
        raise PasteImportError(
            "Unknown market_id values not present in market_registry.yaml: "
            + ", ".join(sorted(set(unknown)))
        )

    thesis = _read_existing_thesis_buckets(portfolio_path_for_thesis)
    if thesis:
        portfolio = portfolio.model_copy(
            update={
                "positions": [
                    p.model_copy(update={"thesis_bucket": thesis.get(p.market_id, p.thesis_bucket)})
                    for p in portfolio.positions
                ]
            }
        )
    return _dump_portfolio_yaml(portfolio)


def _validate_orders(doc: dict, valid_market_ids: set[str]) -> str:
    try:
        orders = OpenOrders.model_validate(doc)
    except ValidationError as exc:
        raise PasteImportError(_format_validation_error(exc, "OpenOrders")) from exc

    every_order = list(orders.buy_orders) + list(orders.sell_orders)
    unknown = [o.market_id for o in every_order if o.market_id not in valid_market_ids]
    if unknown:
        raise PasteImportError(
            "Unknown market_id values not present in market_registry.yaml: "
            + ", ".join(sorted(set(unknown)))
        )
    return _dump_open_orders_yaml(orders)


def _format_validation_error(exc: ValidationError, model_name: str) -> str:
    lines = [f"Schema validation failed for {model_name}:"]
    for err in exc.errors():
        loc = ".".join(str(p) for p in err.get("loc", []))
        msg = err.get("msg", "invalid")
        lines.append(f"  - {loc or '(root)'}: {msg}")
    return "\n".join(lines)


__all__ = ["PasteImportError", "import_paste", "PasteKind"]
