"""canonical_session.json — the canonical on-disk artifact for a packet build.

A session captures the RAW inputs (registry/live_state/portfolio/open_orders/
snapshot dumps, catalyst and order-book text) plus the build parameters that
shaped the derived content. Everything else — trims, warnings, priceability,
rendered packets — is recomputed deterministically from those inputs, which is
what makes "packets are views of the JSON" enforceable: production rendering
happens from state reconstructed out of the validated payload, and round-trip
tests prove render(from_json) == render(in_memory).

Safety fields are Literal-pinned: no parameter on any producer in this module
can set execution_allowed, mode, automated_execution, or human_review_required
to anything but their research-only values.
"""

from __future__ import annotations

import re
from datetime import datetime
from typing import Any, Literal

from pydantic import field_validator

from polyberg.lifecycle import MarketTypeFilter
from polyberg.models import (
    LiveState,
    MarketRegistry,
    MarketSnapshot,
    OpenOrders,
    Portfolio,
    StrictModel,
)
from polyberg.packet_builder.collect_state import PacketState
from polyberg.packet_builder.normalize_packet_state import (
    CanonicalPacket,
    build_canonical_packet,
)

SCHEMA_VERSION = "polyberg_session_v1"

# Windows-safe (no ':' '/' '\'), lexicographically sortable, second resolution;
# optional _N suffix for same-second collisions (the dir claim adds it).
SESSION_ID_RE = re.compile(r"^session_\d{4}-\d{2}-\d{2}_\d{6}(_\d+)?$")


def new_session_id(now: datetime) -> str:
    return "session_" + now.strftime("%Y-%m-%d_%H%M%S")


class SessionOperatingConstraints(StrictModel):
    """cp.constraints minus its "mode" key; automation flags pinned."""

    no_market_orders: bool
    use_sell_ladders: bool
    avoid_99c_dispute_tax: bool
    automated_execution: Literal[False] = False
    human_review_required: Literal[True] = True


class SessionSourceTimestamps(StrictModel):
    portfolio_current: str | None
    open_orders: str | None
    market_snapshot: str | None
    # recent_catalysts.md carries no machine timestamp; entries are dated inline.
    catalysts: str | None
    order_books: str | None
    # One null entry per embedded static_reference text (those markdown files
    # carry no machine timestamps either); {} when the run embeds no rules.
    static_reference: dict[str, str | None]


class SessionTypeFilterParameters(StrictModel):
    category: str | None = None
    thesis_bucket: str | None = None
    rule_key: str | None = None


class SessionBuildParameters(StrictModel):
    """Everything that changes derived content, resolved to concrete values.

    Without these the JSON cannot re-render its packets: trim flags decide the
    active set, catalyst window, and book scope. max_context_age_hours is
    recorded for audit only — it is re-read from the environment at render time.
    """

    targets: list[str]
    include_resolved: bool
    catalyst_window_hours: float
    books_for: Literal["active", "all"]
    type_filter: SessionTypeFilterParameters | None = None
    max_context_age_hours: float
    context_dir: str | None = None
    snapshot_path: str | None = None


class CanonicalSession(StrictModel):
    schema_version: Literal["polyberg_session_v1"] = SCHEMA_VERSION
    session_id: str
    # Identical string to cp.packet_generated_at == state.now.isoformat() —
    # the determinism anchor for byte-exact re-rendering.
    generated_at: str
    mode: Literal["research_only"] = "research_only"
    execution_allowed: Literal[False] = False
    operating_constraints: SessionOperatingConstraints
    source_timestamps: SessionSourceTimestamps
    # {"live_state": <raw LiveState dump>} — live_state.mode stays untouched
    # in here; the top-level mode const is the session's own safety pin.
    fresh_context: dict[str, Any]
    # {"trading_principles": <text>, "stable_rules": <text>} when the run
    # writes a rules artifact; {} otherwise.
    static_reference: dict[str, str]
    portfolio: dict[str, Any]
    open_orders: dict[str, Any]
    # Full registry dump ({"markets": [...]}); packet trimming is re-derived.
    market_registry: dict[str, Any]
    # {"raw": <order_books.json dict|null>, "markdown": <order_books.md|null>}
    order_books: dict[str, Any]
    # Raw MarketSnapshot dump, or {} when the build ran without a snapshot.
    market_snapshot: dict[str, Any]
    # {"markdown": <recent_catalysts.md text>} — windowed lists are derived.
    catalysts: dict[str, Any]
    freshness_audit: dict[str, Any]
    completeness_audit: dict[str, Any]
    # Placeholder for a later severity/gating pass.
    gate_status: dict[str, Any]
    exposure_summary: dict[str, Any]
    build_parameters: SessionBuildParameters

    @field_validator("session_id")
    @classmethod
    def validate_session_id(cls, value: str) -> str:
        if not SESSION_ID_RE.fullmatch(value):
            raise ValueError(
                "session_id must match session_YYYY-MM-DD_HHMMSS with an "
                "optional _N collision suffix"
            )
        return value


def build_canonical_session(
    state: PacketState,
    canonical: CanonicalPacket,
    *,
    session_id: str,
    build_parameters: SessionBuildParameters,
    static_reference_texts: dict[str, str] | None = None,
) -> CanonicalSession:
    constraints = dict(canonical.constraints)
    constraints.pop("mode", None)
    static_texts = dict(static_reference_texts) if static_reference_texts else {}
    return CanonicalSession(
        session_id=session_id,
        generated_at=canonical.packet_generated_at,
        operating_constraints=SessionOperatingConstraints.model_validate(constraints),
        source_timestamps=SessionSourceTimestamps(
            **canonical.source_timestamps,
            static_reference={key: None for key in static_texts},
        ),
        fresh_context={"live_state": state.live_state.model_dump(mode="json")},
        static_reference=static_texts,
        portfolio=state.portfolio.model_dump(mode="json"),
        open_orders=state.open_orders.model_dump(mode="json"),
        market_registry=state.registry.model_dump(mode="json"),
        order_books={"raw": state.order_books, "markdown": state.order_books_markdown},
        market_snapshot=state.snapshot.model_dump(mode="json") if state.snapshot else {},
        catalysts={"markdown": state.catalysts_markdown},
        freshness_audit={
            "warnings": list(canonical.freshness_warnings),
            "live_state_as_of": state.live_state.as_of.isoformat(),
        },
        completeness_audit={
            "missing_info": list(canonical.missing_info),
            "blocking_warnings": list(canonical.blocking_warnings),
            "priceable_markets": list(canonical.priceable_markets),
            "unpriceable_markets": list(canonical.unpriceable_markets),
        },
        gate_status={},
        exposure_summary={
            "by_thesis_bucket": list(canonical.exposure_summary),
            "is_fallback": canonical.exposure_is_fallback,
            "concentration_warnings": list(canonical.concentration_warnings),
        },
        build_parameters=build_parameters,
    )


def packet_state_from_session(payload: dict[str, Any]) -> PacketState:
    """Reconstruct the raw factual state from a validated session payload.

    Lossless because the session stores raw model dumps and raw text. The
    rebuilt now carries a fixed-offset tzinfo (datetime.fromisoformat), not the
    original ZoneInfo — renderers only use .isoformat(), which round-trips
    byte-exactly.
    """
    order_books = payload["order_books"]
    snapshot_raw = payload["market_snapshot"]
    return PacketState(
        now=datetime.fromisoformat(payload["generated_at"]),
        registry=MarketRegistry.model_validate(payload["market_registry"]),
        live_state=LiveState.model_validate(payload["fresh_context"]["live_state"]),
        portfolio=Portfolio.model_validate(payload["portfolio"]),
        open_orders=OpenOrders.model_validate(payload["open_orders"]),
        snapshot=MarketSnapshot.model_validate(snapshot_raw) if snapshot_raw else None,
        catalysts_markdown=payload["catalysts"]["markdown"],
        order_books=order_books["raw"],
        order_books_markdown=order_books["markdown"],
    )


def canonical_packet_from_session(payload: dict[str, Any]) -> CanonicalPacket:
    """Re-derive the CanonicalPacket a session payload was built from."""
    state = packet_state_from_session(payload)
    params = payload["build_parameters"]
    raw_filter = params["type_filter"]
    type_filter = (
        MarketTypeFilter(
            category=raw_filter["category"],
            thesis_bucket=raw_filter["thesis_bucket"],
            rule_key=raw_filter["rule_key"],
        )
        if raw_filter
        else None
    )
    return build_canonical_packet(
        state=state,
        include_resolved=params["include_resolved"],
        catalyst_window_hours=params["catalyst_window_hours"],
        books_for=params["books_for"],
        type_filter=type_filter,
    )
