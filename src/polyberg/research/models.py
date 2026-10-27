"""Allowlisted research contract. Unknown fields fail at every object boundary."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

Status = Literal["discovered", "screening", "researching", "monitoring", "rejected", "archived"]
Category = Literal[
    "observation",
    "evidence_summary",
    "question",
    "catalyst",
    "hypothesis",
    "scenario",
    "contradiction",
    "model_interpretation",
]
RelationKind = Literal[
    "related",
    "same_topic",
    "correlated",
    "mutually_exclusive",
    "exhaustive",
    "complementary",
    "overlapping",
    "alternative_deadline",
    "same_measurement",
    "implication",
    "causal",
    "prerequisite",
]
SYMMETRIC = {
    "related",
    "same_topic",
    "correlated",
    "mutually_exclusive",
    "exhaustive",
    "complementary",
    "overlapping",
    "alternative_deadline",
    "same_measurement",
}
AnnotationKind = Literal[
    "conditions",
    "oracle",
    "resolution_source",
    "fallback",
    "ambiguity",
    "dispute",
    "measurement_period",
    "resolution_deadline",
]


def utcnow() -> str:
    return datetime.now(UTC).isoformat()


def canonical(value: BaseModel | dict | list) -> str:
    if isinstance(value, BaseModel):
        value = value.model_dump(mode="json")
    return json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False) + "\n"


def digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, allow_inf_nan=False)


class Outcome(StrictModel):
    outcome_id: str
    index: int
    label: str
    token_id: str | None = None
    position_id: str | None = None
    asset_id: str | None = None


class Identification(StrictModel):
    market_id: str
    event_id: str | None = None
    slug: str | None = None
    question: str
    condition_id: str | None = None
    question_id: str | None = None
    protocol: str | None = None
    lifecycle: Literal["active", "closed", "archived", "inactive", "unknown"] = "unknown"
    trading_start: str | None = None
    trading_end: str | None = None
    page_url: str | None = None
    api_url: str
    outcomes: list[Outcome] = Field(default_factory=list)


class Event(StrictModel):
    event_id: str
    slug: str | None = None
    title: str
    description: str | None = None
    page_url: str | None = None
    api_url: str
    retrieved_at: str | None = None
    expected_market_ids: list[str] = Field(default_factory=list)
    contracts: list[Identification] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class Quote(StrictModel):
    outcome_id: str
    displayed_price: float | None = Field(default=None, ge=0, le=1)
    displayed_at: str | None = None
    best_bid: float | None = Field(default=None, ge=0, le=1)
    best_ask: float | None = Field(default=None, ge=0, le=1)
    midpoint: float | None = Field(default=None, ge=0, le=1)
    last_trade: float | None = Field(default=None, ge=0, le=1)
    book_retrieved_at: str | None = None
    midpoint_retrieved_at: str | None = None
    last_trade_retrieved_at: str | None = None
    book_timestamp: str | None = None
    source_urls: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class RulesInput(StrictModel):
    text: str
    text_sha256: str
    api_url: str
    page_url: str | None = None
    resolution_source: str | None = None
    resolution_status: str | None = None

    @model_validator(mode="after")
    def check_hash(self):
        if self.text_sha256 != digest(self.text):
            raise ValueError("Rules text hash does not match verbatim text")
        return self


class Annotation(StrictModel):
    annotation_id: int
    kind: AnnotationKind
    text: str
    source_url: str
    created_at: str
    rules_version_id: int
    needs_review: bool = False


class RulesVersion(RulesInput):
    rules_version_id: int
    first_retrieved_at: str
    observations: list[str] = Field(default_factory=list)
    annotations: list[Annotation] = Field(default_factory=list)


class Snapshot(StrictModel):
    snapshot_id: int
    retrieved_at: str
    rules_version_id: int | None = None
    quotes: list[Quote]
    warnings: list[str] = Field(default_factory=list)


class Source(StrictModel):
    url: str
    title: str = ""
    published_at: str | None = None
    observed_at: str | None = None

    @field_validator("published_at", "observed_at")
    @classmethod
    def timestamp(cls, value: str | None) -> str | None:
        if value is not None:
            at = datetime.fromisoformat(value.replace("Z", "+00:00"))
            if at.tzinfo is None:
                raise ValueError("Source timestamps require timezone offsets")
        return value

    @field_validator("url")
    @classmethod
    def http_url(cls, value: str) -> str:
        from urllib.parse import urlsplit

        parsed = urlsplit(value)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            raise ValueError("Source requires an http(s) URL")
        return value


class Entry(StrictModel):
    entry_id: int
    category: Category
    text: str
    created_at: str
    verified_at: str | None = None
    sources: list[Source] = Field(default_factory=list)


class Relationship(StrictModel):
    relationship_id: int
    from_market: str
    to_market: str
    kind: RelationKind
    explanation: str
    source_url: str | None = None
    created_at: str


class ResearchMarket(StrictModel):
    identification: Identification
    status: Status
    followed: bool
    tags: list[str]
    projects: list[str]
    snapshot: Snapshot | None = None
    rules: RulesVersion | None = None
    entries: list[Entry]
    relationships: list[Relationship]
    annotations_for_review: list[Annotation] = Field(default_factory=list)
    last_attempt_at: str | None = None
    last_success_at: str | None = None
    warnings: list[str] = Field(default_factory=list)


class ResearchPacket(StrictModel):
    schema_version: Literal["polyberg_research_packet_v1"] = "polyberg_research_packet_v1"
    generated_at: str
    max_age_hours: float = Field(gt=0)
    selection: str
    events: list[Event]
    markets: list[ResearchMarket]
    warnings: list[str]

    @field_validator("generated_at")
    @classmethod
    def generation_timestamp(cls, value: str) -> str:
        if datetime.fromisoformat(value.replace("Z", "+00:00")).tzinfo is None:
            raise ValueError("Packet generation timestamp requires a timezone")
        return value


class FrozenPacket(StrictModel):
    packet_id: str = Field(pattern=r"^[a-f0-9]{64}$")
    snapshot_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    packet: ResearchPacket

    @model_validator(mode="after")
    def snapshot_identity(self):
        if (
            self.packet_id != self.snapshot_sha256
            or digest(canonical(self.packet)) != self.packet_id
        ):
            raise ValueError("Frozen packet identity does not match the canonical snapshot")
        return self


class MarketActivity(StrictModel):
    """Public trading activity. Stored beside snapshots; never part of a research packet."""

    retrieved_at: str
    volume_total: float | None = Field(default=None, ge=0)
    volume_24h: float | None = Field(default=None, ge=0)
    volume_1w: float | None = Field(default=None, ge=0)
    liquidity: float | None = Field(default=None, ge=0)
    price_change_1d: float | None = Field(default=None, ge=-1, le=1)
    price_change_1w: float | None = Field(default=None, ge=-1, le=1)
    spread: float | None = Field(default=None, ge=0, le=1)
    open_interest: float | None = Field(default=None, ge=0)
    open_interest_retrieved_at: str | None = None
    source_urls: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class CollectedMarket(StrictModel):
    identification: Identification
    retrieved_at: str
    quotes: list[Quote]
    rules: RulesInput | None
    activity: MarketActivity | None = None
    warnings: list[str] = Field(default_factory=list)


class Discovery(StrictModel):
    events: list[Event] = Field(default_factory=list)
    markets: list[CollectedMarket] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


# Viewer models below are returned beside, never inside, the research packet contract.
HistorySpan = Literal["1d", "1w", "1m", "max"]


class PricePoint(StrictModel):
    t: int = Field(ge=0)
    p: float = Field(ge=0, le=1)
    r: int = Field(ge=0)


class PriceSeries(StrictModel):
    outcome_id: str
    label: str
    asset_id: str | None = None
    span: HistorySpan
    source_url: str | None = None
    retrieved_at: str | None = None
    points: list[PricePoint] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class PriceHistory(StrictModel):
    market_id: str
    span: HistorySpan
    series: list[PriceSeries]


class BookLevel(StrictModel):
    price: float = Field(ge=0, le=1)
    size: float = Field(ge=0)
    cumulative: float = Field(ge=0)


class OutcomeBook(StrictModel):
    outcome_id: str
    label: str
    asset_id: str | None = None
    bids: list[BookLevel] = Field(default_factory=list)
    asks: list[BookLevel] = Field(default_factory=list)
    bid_levels: int = 0
    ask_levels: int = 0
    best_bid: float | None = Field(default=None, ge=0, le=1)
    best_ask: float | None = Field(default=None, ge=0, le=1)
    spread: float | None = Field(default=None, ge=-1, le=1)
    book_midpoint: float | None = Field(default=None, ge=0, le=1)
    tick_size: float | None = Field(default=None, ge=0)
    min_order_size: float | None = Field(default=None, ge=0)
    book_timestamp: str | None = None
    retrieved_at: str | None = None
    source_url: str | None = None
    warnings: list[str] = Field(default_factory=list)


class MarketBook(StrictModel):
    market_id: str
    outcomes: list[OutcomeBook]
