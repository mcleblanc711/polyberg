from __future__ import annotations

import re
from datetime import date, datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

Side = Literal["YES", "NO"]
MARKET_ID_RE = re.compile(r"^[a-z0-9_]+$")


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


def require_timezone(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("datetime values must include a timezone offset")
    return value


def require_market_id(value: str) -> str:
    if not MARKET_ID_RE.fullmatch(value):
        raise ValueError("market_id must be lowercase letters, numbers, and underscores only")
    return value


class Market(StrictModel):
    market_id: str
    name: str
    polymarket_url: str
    category: str
    thesis_bucket: str = ""
    rule_key: str
    oracle_type: str
    preferred_side: Side
    risk_flags: list[str] = Field(default_factory=list)
    resolution_date: date
    notes: str
    event_slug: str | None = None
    condition_id: str | None = None
    yes_token_id: str | None = None
    no_token_id: str | None = None
    data_collection: DataCollection | None = None
    rule_risk: RuleRisk | None = None

    @field_validator("market_id")
    @classmethod
    def validate_market_id(cls, value: str) -> str:
        return require_market_id(value)


class MarketRegistry(StrictModel):
    markets: list[Market]

    @model_validator(mode="after")
    def require_unique_market_ids(self) -> MarketRegistry:
        ids = [market.market_id for market in self.markets]
        duplicates = sorted({market_id for market_id in ids if ids.count(market_id) > 1})
        if duplicates:
            raise ValueError(f"duplicate market_id values in registry: {', '.join(duplicates)}")
        return self

    @property
    def market_ids(self) -> set[str]:
        return {market.market_id for market in self.markets}


class Position(StrictModel):
    market_id: str
    market_name: str
    side: Side
    avg_price: float = Field(ge=0, le=1)
    mark_price: float = Field(ge=0, le=1)
    shares: float = Field(ge=0)
    current_value: float = Field(ge=0)
    pnl: float
    thesis_bucket: str

    @field_validator("market_id")
    @classmethod
    def validate_market_id(cls, value: str) -> str:
        return require_market_id(value)


class Portfolio(StrictModel):
    as_of: datetime
    portfolio_value: float = Field(ge=0)
    cash_available: float = Field(ge=0)
    positions: list[Position]

    @field_validator("as_of")
    @classmethod
    def validate_as_of_timezone(cls, value: datetime) -> datetime:
        return require_timezone(value)


class Order(StrictModel):
    market_id: str
    side: Side
    price: float = Field(ge=0, le=1)
    shares: float = Field(ge=0)
    order_type: str = "limit"
    notes: str = ""

    @field_validator("market_id")
    @classmethod
    def validate_market_id(cls, value: str) -> str:
        return require_market_id(value)

    @field_validator("order_type")
    @classmethod
    def require_limit_order(cls, value: str) -> str:
        if value != "limit":
            raise ValueError("order_type must be 'limit'")
        return value


class OpenOrders(StrictModel):
    as_of: datetime
    buy_orders: list[Order] = Field(default_factory=list)
    sell_orders: list[Order] = Field(default_factory=list)

    @field_validator("as_of")
    @classmethod
    def validate_as_of_timezone(cls, value: datetime) -> datetime:
        return require_timezone(value)


class AccountSnapshot(StrictModel):
    portfolio_value: float = Field(ge=0)
    cash_available: float = Field(ge=0)
    notes: str = ""


class LiveState(StrictModel):
    as_of: datetime
    mode: str
    account_snapshot: AccountSnapshot
    active_thesis: list[str]
    constraints: dict[str, Any]
    watchlist: list[str]
    notes: list[str]
    proxy_wallet: str = ""

    @field_validator("as_of")
    @classmethod
    def validate_as_of_timezone(cls, value: datetime) -> datetime:
        return require_timezone(value)

    @field_validator("watchlist")
    @classmethod
    def validate_watchlist_market_ids(cls, value: list[str]) -> list[str]:
        for market_id in value:
            require_market_id(market_id)
        return value

    @field_validator("mode")
    @classmethod
    def validate_mode(cls, value: str) -> str:
        if not value:
            raise ValueError("mode must be a non-empty string")
        return value


class DataCollection(StrictModel):
    fetch_gamma: bool = False
    fetch_clob: bool = False
    fetch_orderbook: bool = False


class RuleRisk(StrictModel):
    oracle_type: str
    ambiguity: str
    media_fallback: bool
    official_statement_required: bool
    dispute_risk: str


class MarketSnapshotEntry(StrictModel):
    market_id: str
    yes_price: float | None = Field(default=None, ge=0, le=1)
    no_price: float | None = Field(default=None, ge=0, le=1)
    best_bid_yes: float | None = Field(default=None, ge=0, le=1)
    best_ask_yes: float | None = Field(default=None, ge=0, le=1)
    best_bid_no: float | None = Field(default=None, ge=0, le=1)
    best_ask_no: float | None = Field(default=None, ge=0, le=1)
    spread: float | None = Field(default=None, ge=0, le=1)
    orderbook_depth_top: float | None = Field(default=None, ge=0)
    liquidity_warning: bool = False
    missing_info: list[str] = Field(default_factory=list)

    @field_validator("market_id")
    @classmethod
    def validate_market_id(cls, value: str) -> str:
        return require_market_id(value)


class MarketSnapshot(StrictModel):
    as_of: datetime
    markets: list[MarketSnapshotEntry]

    @field_validator("as_of")
    @classmethod
    def validate_as_of_timezone(cls, value: datetime) -> datetime:
        return require_timezone(value)


class TradeTicketAttribution(StrictModel):
    """Which assistant backed a final order, carried verbatim for the ledger.

    ``source_model_support`` is left as the adjudicator emitted it (free text or a
    list); normalization to the ledger's closed assistant set happens on the
    Polygraph import side, not here — this package deliberately keeps no mapping
    layer (see the unification build decision).
    """

    source_model_support: str | list[str]
    recommended_price: float | None = Field(default=None, ge=0, le=1)
    recommended_size: float | None = Field(default=None, ge=0)
    evidence: str = ""


class TradeTicketDecision(StrictModel):
    market_id: str
    market_slug: str
    market_title: str
    side: Side
    intent: str
    decision_type: str | None = None
    price_used: float = Field(ge=0, le=1)
    max_allocation: float = Field(ge=0)
    thesis_summary: str = ""
    rule_summary: str = ""
    # oracle_type / thesis_bucket are copied verbatim from the registry. They may
    # not yet be valid ledger enum values (the registry migration is a later
    # phase); the importer validates leniently and drops unknown values.
    oracle_type: str | None = None
    thesis_bucket: str | None = None
    status: str = "DRAFT"
    attributions: list[TradeTicketAttribution] = Field(default_factory=list)

    @field_validator("market_id")
    @classmethod
    def validate_market_id(cls, value: str) -> str:
        return require_market_id(value)


class TradeTicketRejected(StrictModel):
    market_id: str
    rationale: str = ""


class TradeTicket(StrictModel):
    """Machine-readable sibling of the human trade ticket, shaped for the ledger."""

    schema_version: str = "1"
    source: str = "polyberg-adjudicator"
    as_of: datetime
    human_review_required: bool = True
    decisions: list[TradeTicketDecision] = Field(default_factory=list)
    rejected: list[TradeTicketRejected] = Field(default_factory=list)

    @field_validator("as_of")
    @classmethod
    def validate_as_of_timezone(cls, value: datetime) -> datetime:
        return require_timezone(value)
