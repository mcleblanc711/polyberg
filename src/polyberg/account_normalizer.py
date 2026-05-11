"""Raw Polymarket data-api responses → canonical context schema.

Maps the unauthenticated ``data-api.polymarket.com/positions`` payload onto
``Portfolio`` so the GUI's PROMOTE-TO-CONTEXT path can write to
``context/portfolio_current.yaml`` after user review.

Balances and open orders are not normalized here — data-api does not expose
those without authentication, and uses an authenticated path (the
existing authenticated path). Adding wallet-on-chain balance + CLOB order
fetch is a separate scope.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

import yaml

from polyberg.config import get_timezone
from polyberg.loaders import load_market_registry, load_portfolio
from polyberg.models import MarketRegistry, Portfolio, Position


class NormalizerError(RuntimeError):
    pass


def normalize_data_api_positions(
    payload: list[dict],
    registry: MarketRegistry,
    cash_available: float,
    portfolio_value_override: float | None = None,
    now: datetime | None = None,
) -> tuple[Portfolio, list[dict[str, str]]]:
    """Map data-api positions onto a canonical Portfolio.

    Returns ``(portfolio, skipped)`` where ``skipped`` lists positions that
    could not be matched to a registry market (with reasons). Positions are
    matched by ``conditionId`` against the registry's ``condition_id`` field.

    ``portfolio_value`` defaults to the sum of position current values plus
    ``cash_available`` unless explicitly overridden.
    """
    if not isinstance(payload, list):
        raise NormalizerError(
            f"Expected a list payload from data-api/positions, got {type(payload).__name__}"
        )
    by_condition: dict[str, str] = {}
    for market in registry.markets:
        if market.condition_id:
            by_condition[market.condition_id.lower()] = market.market_id

    positions: list[Position] = []
    skipped: list[dict[str, str]] = []
    for raw in payload:
        if not isinstance(raw, dict):
            skipped.append({"reason": "non-object position entry", "title": ""})
            continue
        condition_id = str(raw.get("conditionId") or "").lower()
        title = str(raw.get("title") or "")
        if not condition_id:
            skipped.append({"reason": "missing conditionId", "title": title})
            continue
        market_id = by_condition.get(condition_id)
        if market_id is None:
            skipped.append(
                {
                    "reason": "conditionId not in registry",
                    "title": title,
                    "condition_id": condition_id,
                }
            )
            continue
        size = _as_float(raw.get("size"))
        if size <= 0:
            skipped.append({"reason": "non-positive size", "title": title})
            continue
        positions.append(
            Position(
                market_id=market_id,
                market_name=title or market_id,
                side=_outcome_to_side(raw.get("outcome")),
                avg_price=_clamp_unit(_as_float(raw.get("avgPrice"))),
                mark_price=_clamp_unit(_as_float(raw.get("curPrice"))),
                shares=size,
                current_value=max(0.0, _as_float(raw.get("currentValue"))),
                pnl=_as_float(raw.get("cashPnl")),
                thesis_bucket="",
            )
        )

    positions_value = sum(p.current_value for p in positions)
    portfolio_value = (
        portfolio_value_override
        if portfolio_value_override is not None
        else positions_value + max(0.0, cash_available)
    )
    if now is None:
        now = datetime.now(get_timezone())
    elif now.tzinfo is None or now.utcoffset() is None:
        now = now.replace(tzinfo=get_timezone())

    portfolio = Portfolio(
        as_of=now,
        portfolio_value=max(0.0, portfolio_value),
        cash_available=max(0.0, cash_available),
        positions=positions,
    )
    return portfolio, skipped


def promote_data_api_positions(
    raw_path: Path,
    output_path: Path,
    cash_available: float,
    registry_path: Path | None = None,
    portfolio_path_for_thesis: Path | None = None,
    now: datetime | None = None,
) -> tuple[Path, list[dict[str, str]]]:
    """Read a raw data-api positions JSON file, normalize, write canonical YAML.

    ``portfolio_path_for_thesis`` (defaults to ``context/portfolio_current.yaml``)
    is read if present so existing ``thesis_bucket`` labels survive promotion —
    they're a polyberg-only annotation the API doesn't carry. Position-bucket
    mapping is by ``market_id``.
    """
    raw_text = raw_path.read_text(encoding="utf-8")
    raw_doc = json.loads(raw_text)
    payload = raw_doc.get("payload", raw_doc) if isinstance(raw_doc, dict) else raw_doc

    registry = load_market_registry(registry_path)
    portfolio, skipped = normalize_data_api_positions(
        payload, registry, cash_available=cash_available, now=now
    )

    thesis_by_market = _read_existing_thesis_buckets(portfolio_path_for_thesis)
    if thesis_by_market:
        portfolio = portfolio.model_copy(
            update={
                "positions": [
                    p.model_copy(update={"thesis_bucket": thesis_by_market.get(p.market_id, "")})
                    for p in portfolio.positions
                ]
            }
        )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(_dump_portfolio_yaml(portfolio), encoding="utf-8")
    return output_path, skipped


def _read_existing_thesis_buckets(path: Path | None) -> dict[str, str]:
    try:
        existing = load_portfolio(path)
    except Exception:
        return {}
    return {p.market_id: p.thesis_bucket for p in existing.positions if p.thesis_bucket}


def _dump_portfolio_yaml(portfolio: Portfolio) -> str:
    data = portfolio.model_dump(mode="json")
    return yaml.safe_dump(data, sort_keys=False, default_flow_style=False, allow_unicode=True)


def _outcome_to_side(raw: object) -> str:
    text = str(raw or "").strip().lower()
    if text in ("yes", "up"):
        return "YES"
    if text in ("no", "down"):
        return "NO"
    # Conservative default: treat unknown outcome labels as NO. The user can
    # correct on review; logging the original label keeps the audit trail in
    # the skipped channel is the caller's job if they care.
    return "NO"


def _as_float(value: object) -> float:
    if isinstance(value, (int, float)):
        return float(value)
    return 0.0


def _clamp_unit(value: float) -> float:
    if value < 0.0:
        return 0.0
    if value > 1.0:
        return 1.0
    return value
