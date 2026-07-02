"""Hermetic tests for canonical_session.json: build, validate, reconstruct,
re-render.

PacketState is built inline (test_packet_trim.py pattern) — no network and no
repo context reads; the only file touched is the checked-in schema. The render
round-trip tests are the enforcement of "packets are views of the JSON":
render(state rebuilt from the payload) must equal render(in-memory state).
"""

from __future__ import annotations

import inspect
import json
from datetime import UTC, datetime, timedelta

import pytest
from pydantic import ValidationError

from polyberg.lifecycle import MarketTypeFilter
from polyberg.models import (
    LiveState,
    MarketRegistry,
    MarketSnapshot,
    OpenOrders,
    Portfolio,
)
from polyberg.packet_builder.collect_state import PacketState
from polyberg.packet_builder.normalize_packet_state import build_canonical_packet
from polyberg.packet_builder.renderers import render_claude_packet, render_gpt_packet
from polyberg.packet_builder.session import (
    SCHEMA_VERSION,
    SESSION_ID_RE,
    CanonicalSession,
    SessionBuildParameters,
    SessionOperatingConstraints,
    build_canonical_session,
    canonical_packet_from_session,
    new_session_id,
    packet_state_from_session,
)
from polyberg.validators import (
    ResponseValidationError,
    validate_canonical_session,
    validate_canonical_session_payload,
)

_NOW = datetime(2026, 6, 22, 12, 0, tzinfo=UTC)
_SESSION_ID = "session_2026-06-22_120000"

TOP_LEVEL_KEYS = {
    "schema_version",
    "session_id",
    "generated_at",
    "mode",
    "execution_allowed",
    "operating_constraints",
    "source_timestamps",
    "fresh_context",
    "static_reference",
    "portfolio",
    "open_orders",
    "market_registry",
    "order_books",
    "market_snapshot",
    "catalysts",
    "freshness_audit",
    "completeness_audit",
    "gate_status",
    "exposure_summary",
    "build_parameters",
}


# --- builders --------------------------------------------------------------


def _market(market_id: str, *, lifecycle: str = "active", category: str = "test") -> dict:
    return {
        "market_id": market_id,
        "name": market_id,
        "polymarket_url": "https://example.invalid",
        "category": category,
        "rule_key": "rule_" + market_id,
        "oracle_type": "pure_data",
        "preferred_side": "YES",
        "risk_flags": [],
        "resolution_date": "2026-06-30",
        "lifecycle": lifecycle,
        "notes": "",
        "thesis_bucket": "Iran conflict",
        "yes_token_id": "1",
        "no_token_id": "2",
        "data_collection": {"fetch_orderbook": True},
    }


def _position(market_id: str, thesis_bucket: str = "Iran conflict") -> dict:
    return {
        "market_id": market_id,
        "market_name": market_id,
        "side": "YES",
        "avg_price": 0.5,
        "mark_price": 0.5,
        "shares": 10.0,
        "current_value": 5.0,
        "pnl": 0.0,
        "thesis_bucket": thesis_bucket,
    }


def _state(
    *,
    markets: list[dict],
    positions: list[dict],
    catalysts_markdown: str = "",
    snapshot: MarketSnapshot | None = None,
    order_books: dict | None = None,
    order_books_markdown: str | None = None,
    now: datetime = _NOW,
) -> PacketState:
    registry = MarketRegistry.model_validate({"markets": markets})
    portfolio = Portfolio.model_validate(
        {
            "as_of": now.isoformat(),
            "portfolio_value": sum(p["current_value"] for p in positions) + 10.0,
            "cash_available": 10.0,
            "positions": positions,
        }
    )
    open_orders = OpenOrders.model_validate(
        {"as_of": now.isoformat(), "buy_orders": [], "sell_orders": []}
    )
    live_state = LiveState.model_validate(
        {
            "as_of": now.isoformat(),
            "mode": "research_only",
            "account_snapshot": {"portfolio_value": 15.0, "cash_available": 10.0},
            "active_thesis": [],
            "constraints": {
                "no_market_orders": True,
                "use_sell_ladders": True,
                "avoid_99c_dispute_tax": True,
            },
            "watchlist": [],
            "notes": [],
        }
    )
    return PacketState(
        now=now,
        registry=registry,
        live_state=live_state,
        portfolio=portfolio,
        open_orders=open_orders,
        snapshot=snapshot,
        catalysts_markdown=catalysts_markdown,
        order_books=order_books,
        order_books_markdown=order_books_markdown,
    )


def _books(now: datetime) -> tuple[dict, str]:
    stale = (now - timedelta(hours=40)).isoformat()
    order_books = {
        "generated_at": now.isoformat(),
        "markets": {
            "m_fresh": {"status": "ok", "fetched_at": now.isoformat()},
            "m_stale": {"status": "ok", "fetched_at": stale},
            "m_404": {"status": "unavailable", "fetched_at": now.isoformat(), "error": "404"},
        },
    }
    md = (
        "## Live Order Books\n"
        f"### m_fresh — NO book · fetched_at {now.isoformat()}\n- ok\n"
        f"### m_stale — NO book · fetched_at {stale}\n- ok\n"
        "### m_404 — BOOK UNAVAILABLE — do not price orders\n- error\n"
    )
    return order_books, md


def _catalysts_md() -> str:
    return (
        "## Credible Reporting Watch\n"
        "- [2026-06-21 12:00Z] **m_fresh** recent + active\n"
        "\n"
        "## Trader Interpretation Notes\n"
        "- a trader hypothesis with no timestamp\n"
    )


def _build_parameters(**overrides) -> SessionBuildParameters:
    params: dict = {
        "targets": ["gpt", "claude"],
        "include_resolved": False,
        "catalyst_window_hours": 48.0,
        "books_for": "active",
        "type_filter": None,
        "max_context_age_hours": 24.0,
        "context_dir": None,
        "snapshot_path": None,
    }
    params.update(overrides)
    return SessionBuildParameters.model_validate(params)


def _session(
    state: PacketState,
    *,
    build_parameters: SessionBuildParameters | None = None,
    static_reference_texts: dict[str, str] | None = None,
):
    """Build (CanonicalPacket, CanonicalSession) with coherent build args."""
    bp = build_parameters or _build_parameters()
    type_filter = (
        MarketTypeFilter(
            category=bp.type_filter.category,
            thesis_bucket=bp.type_filter.thesis_bucket,
            rule_key=bp.type_filter.rule_key,
        )
        if bp.type_filter
        else None
    )
    cp = build_canonical_packet(
        state=state,
        include_resolved=bp.include_resolved,
        catalyst_window_hours=bp.catalyst_window_hours,
        books_for=bp.books_for,
        type_filter=type_filter,
    )
    session = build_canonical_session(
        state,
        cp,
        session_id=_SESSION_ID,
        build_parameters=bp,
        static_reference_texts=static_reference_texts,
    )
    return cp, session


def _rich_state() -> PacketState:
    order_books, md = _books(_NOW)
    return _state(
        markets=[
            _market("m_fresh"),
            _market("m_stale"),
            _market("m_404"),
            _market("m_resolved", lifecycle="resolved"),
        ],
        positions=[_position("m_fresh")],
        catalysts_markdown=_catalysts_md(),
        order_books=order_books,
        order_books_markdown=md,
    )


# --- schema + shape ----------------------------------------------------------


def test_built_session_validates_and_has_all_pinned_keys() -> None:
    cp, session = _session(_rich_state())
    payload = session.model_dump(mode="json")

    validate_canonical_session_payload(payload)
    assert set(payload) == TOP_LEVEL_KEYS
    assert payload["schema_version"] == SCHEMA_VERSION
    assert payload["session_id"] == _SESSION_ID
    # The determinism anchor: identical string to the packet's generated_at.
    assert payload["generated_at"] == cp.packet_generated_at
    assert payload["mode"] == "research_only"
    assert payload["execution_allowed"] is False
    # Raw catalysts text is stored; windowed lists are derived, not persisted.
    assert payload["catalysts"] == {"markdown": _catalysts_md()}
    assert payload["gate_status"] == {}


def test_on_disk_session_validates(tmp_path) -> None:
    _, session = _session(_rich_state())
    path = tmp_path / "canonical_session.json"
    path.write_text(
        json.dumps(session.model_dump(mode="json"), indent=2) + "\n", encoding="utf-8"
    )
    validate_canonical_session(path)


def test_operating_constraints_strip_mode_and_pin_automation() -> None:
    _, session = _session(_rich_state())
    payload = session.model_dump(mode="json")
    assert payload["operating_constraints"] == {
        "no_market_orders": True,
        "use_sell_ladders": True,
        "avoid_99c_dispute_tax": True,
        "automated_execution": False,
        "human_review_required": True,
    }


# --- safety pins: model AND schema must reject drift -------------------------


_PINNED_MUTATIONS = [
    ("execution_allowed", True),
    ("mode", "live_trading"),
    ("schema_version", "something_else"),
]


@pytest.mark.parametrize(("key", "value"), _PINNED_MUTATIONS)
def test_model_rejects_pinned_field_drift(key: str, value: object) -> None:
    _, session = _session(_rich_state())
    broken = session.model_dump()
    broken[key] = value
    with pytest.raises(ValidationError):
        CanonicalSession.model_validate(broken)


@pytest.mark.parametrize(("key", "value"), _PINNED_MUTATIONS)
def test_schema_rejects_pinned_field_drift(key: str, value: object) -> None:
    _, session = _session(_rich_state())
    payload = session.model_dump(mode="json")
    payload[key] = value
    with pytest.raises(ResponseValidationError, match=key):
        validate_canonical_session_payload(payload)


@pytest.mark.parametrize(
    ("key", "value"),
    [("automated_execution", True), ("human_review_required", False)],
)
def test_automation_flags_pinned_in_model_and_schema(key: str, value: bool) -> None:
    with pytest.raises(ValidationError):
        SessionOperatingConstraints.model_validate(
            {
                "no_market_orders": True,
                "use_sell_ladders": True,
                "avoid_99c_dispute_tax": True,
                key: value,
            }
        )
    _, session = _session(_rich_state())
    payload = session.model_dump(mode="json")
    payload["operating_constraints"][key] = value
    with pytest.raises(ResponseValidationError, match=key):
        validate_canonical_session_payload(payload)


def test_schema_rejects_missing_and_extra_top_level_keys() -> None:
    _, session = _session(_rich_state())
    payload = session.model_dump(mode="json")

    missing = dict(payload)
    del missing["gate_status"]
    with pytest.raises(ResponseValidationError, match="gate_status"):
        validate_canonical_session_payload(missing)

    extra = dict(payload)
    extra["surprise_key"] = {}
    with pytest.raises(ResponseValidationError, match="surprise_key"):
        validate_canonical_session_payload(extra)


def test_no_producer_parameter_can_set_safety_fields() -> None:
    parameters = inspect.signature(build_canonical_session).parameters
    for name in ("execution_allowed", "mode", "automated_execution", "human_review_required"):
        assert name not in parameters
    # Build parameters can't smuggle them in either.
    bp_fields = set(SessionBuildParameters.model_fields)
    assert not bp_fields & {"execution_allowed", "mode"}


# --- session_id ---------------------------------------------------------------


def test_new_session_id_is_windows_safe_and_matches_pattern() -> None:
    session_id = new_session_id(_NOW)
    assert session_id == "session_2026-06-22_120000"
    assert SESSION_ID_RE.fullmatch(session_id)
    # Collision suffix stays valid; deeper suffixes do not.
    assert SESSION_ID_RE.fullmatch(session_id + "_2")
    assert not SESSION_ID_RE.fullmatch(session_id + "_2_3")
    assert not any(ch in session_id for ch in ':/\\')


def test_model_rejects_malformed_session_id() -> None:
    _, session = _session(_rich_state())
    broken = session.model_dump()
    broken["session_id"] = "session_2026/06/22_120000"
    with pytest.raises(ValidationError, match="session_id"):
        CanonicalSession.model_validate(broken)


# --- reconstruction round-trip -------------------------------------------------


def _json_round_trip(session: CanonicalSession) -> dict:
    return json.loads(json.dumps(session.model_dump(mode="json")))


def test_packet_state_round_trips_losslessly() -> None:
    state = _rich_state()
    _, session = _session(state)
    rebuilt = packet_state_from_session(_json_round_trip(session))

    assert rebuilt.now.isoformat() == state.now.isoformat()
    assert rebuilt.registry == state.registry
    assert rebuilt.live_state == state.live_state
    assert rebuilt.portfolio == state.portfolio
    assert rebuilt.open_orders == state.open_orders
    assert rebuilt.snapshot == state.snapshot
    assert rebuilt.catalysts_markdown == state.catalysts_markdown
    assert rebuilt.order_books == state.order_books
    assert rebuilt.order_books_markdown == state.order_books_markdown


def test_canonical_packet_round_trips() -> None:
    cp, session = _session(_rich_state())
    rebuilt = canonical_packet_from_session(_json_round_trip(session))
    # First real caller of to_dict(): the full derived layer must re-derive
    # identically from the stored raw inputs + build parameters.
    assert rebuilt.to_dict() == cp.to_dict()
    assert rebuilt == cp


def test_render_round_trip_gpt_and_claude() -> None:
    cp, session = _session(_rich_state())
    rebuilt = canonical_packet_from_session(_json_round_trip(session))
    assert render_gpt_packet(rebuilt) == render_gpt_packet(cp)
    assert render_claude_packet(rebuilt) == render_claude_packet(cp)


def test_render_round_trip_legacy() -> None:
    from polyberg.packet_builder.legacy import build_packet

    state = _rich_state()
    _, session = _session(state)
    rebuilt_state = packet_state_from_session(_json_round_trip(session))
    assert build_packet(state=rebuilt_state, catalyst_window_hours=48.0) == build_packet(
        state=state, catalyst_window_hours=48.0
    )


# --- variants -------------------------------------------------------------------


def test_snapshot_absent_stored_as_empty_object() -> None:
    state = _state(markets=[_market("m_fresh")], positions=[_position("m_fresh")])
    _, session = _session(state)
    payload = _json_round_trip(session)

    validate_canonical_session_payload(payload)
    assert payload["market_snapshot"] == {}
    assert packet_state_from_session(payload).snapshot is None


def test_snapshot_present_round_trips() -> None:
    snapshot = MarketSnapshot.model_validate(
        {
            "as_of": _NOW.isoformat(),
            "markets": [{"market_id": "m_fresh", "yes_price": 0.42, "no_price": 0.58}],
        }
    )
    state = _state(
        markets=[_market("m_fresh")], positions=[_position("m_fresh")], snapshot=snapshot
    )
    cp, session = _session(state)
    payload = _json_round_trip(session)

    validate_canonical_session_payload(payload)
    rebuilt = packet_state_from_session(payload)
    assert rebuilt.snapshot == snapshot
    assert canonical_packet_from_session(payload) == cp


def test_books_absent_stored_as_nulls() -> None:
    state = _state(markets=[_market("m_fresh")], positions=[_position("m_fresh")])
    cp, session = _session(state)
    payload = _json_round_trip(session)

    validate_canonical_session_payload(payload)
    assert payload["order_books"] == {"raw": None, "markdown": None}
    rebuilt = packet_state_from_session(payload)
    assert rebuilt.order_books is None
    assert rebuilt.order_books_markdown is None
    assert canonical_packet_from_session(payload) == cp


def test_type_filter_stored_and_rebuilt() -> None:
    state = _state(
        markets=[
            _market("m_hormuz", category="hormuz_transit_count"),
            _market("m_diplo", category="iran_us_diplomacy"),
        ],
        positions=[],
    )
    bp = _build_parameters(
        type_filter={
            "category": "hormuz_transit_count",
            "thesis_bucket": None,
            "rule_key": None,
        }
    )
    cp, session = _session(state, build_parameters=bp)
    payload = _json_round_trip(session)

    validate_canonical_session_payload(payload)
    assert payload["build_parameters"]["type_filter"] == {
        "category": "hormuz_transit_count",
        "thesis_bucket": None,
        "rule_key": None,
    }
    rebuilt = canonical_packet_from_session(payload)
    assert {row["market_id"] for row in rebuilt.market_registry} == {"m_hormuz"}
    assert rebuilt == cp


def test_static_reference_embedded_and_absent() -> None:
    state = _rich_state()
    _, bare = _session(state)
    payload = bare.model_dump(mode="json")
    assert payload["static_reference"] == {}
    assert payload["source_timestamps"]["static_reference"] == {}

    texts = {"trading_principles": "principles text", "stable_rules": "rules text"}
    _, embedded = _session(state, static_reference_texts=texts)
    payload = embedded.model_dump(mode="json")
    validate_canonical_session_payload(payload)
    assert payload["static_reference"] == texts
    assert payload["source_timestamps"]["static_reference"] == {
        "trading_principles": None,
        "stable_rules": None,
    }
