"""Tests for ladder/diff.py — pure diff logic."""
from __future__ import annotations

from polyberg.ladder.diff import (
    PREFLIGHT_DESCRIPTION,
    diff_ladders,
)
from polyberg.ladder.live_orders import LiveRung, UnmappedOrder
from polyberg.ladder.models import Ladder, MatchingConfig, Rung, Tags, TargetLadders

# ── fixtures ──────────────────────────────────────────────────────────────────

def _matching(price_tol=0.0005, shares_tol=1.0):
    return MatchingConfig(price_tolerance=price_tol, shares_tolerance=shares_tol)


def _targets(*ladders):
    return TargetLadders(ladders=list(ladders))


def _ladder(market_id, outcome, action, rungs, purpose=None):
    tags = Tags(purpose=purpose) if purpose else None
    return Ladder(
        market_id=market_id,
        outcome=outcome,
        action=action,
        rungs=[Rung(price=p, shares=s) for p, s in rungs],
        tags=tags,
    )


def _live(order_id, market_id, outcome, action, price, original_size=100.0, matched=0.0):
    return LiveRung(
        order_id=order_id,
        market_id=market_id,
        outcome=outcome,
        action=action,
        price=price,
        original_size=original_size,
        size_matched=matched,
        remaining=original_size - matched,
    )


# ── empty live book → full placement ─────────────────────────────────────────

def test_empty_live_book_full_placement():
    """User's first run: empty live book means all target rungs become PLACEs."""
    targets = _targets(
        _ladder("mkt_a", "NO", "SELL", [(0.90, 150), (0.94, 100)], purpose="cash_rebuild"),
        _ladder("mkt_b", "NO", "BUY", [(0.72, 200)], purpose="runner"),
    )
    plan = diff_ladders(targets, [], [], matching=_matching())

    assert len(plan.cancel) == 0
    assert len(plan.keep) == 0
    assert len(plan.place) == 3
    assert len(plan.preflight) == 1
    assert PREFLIGHT_DESCRIPTION in plan.preflight[0]

    prices = {(p.market_id, p.price) for p in plan.place}
    assert ("mkt_a", 0.90) in prices
    assert ("mkt_a", 0.94) in prices
    assert ("mkt_b", 0.72) in prices


# ── partial overlap ───────────────────────────────────────────────────────────

def test_partial_overlap():
    """Some target rungs match live, others don't."""
    targets = _targets(
        _ladder("mkt_a", "NO", "SELL", [(0.90, 150), (0.94, 100)]),
    )
    live = [_live("ord1", "mkt_a", "NO", "SELL", 0.90, original_size=150)]
    plan = diff_ladders(targets, live, [], matching=_matching())

    assert len(plan.keep) == 1
    assert plan.keep[0].order_id == "ord1"
    assert len(plan.place) == 1
    assert plan.place[0].price == 0.94


# ── price tolerance edges ─────────────────────────────────────────────────────

def test_price_within_tolerance_matches():
    targets = _targets(_ladder("mkt_a", "YES", "BUY", [(0.50, 100)]))
    live = [_live("ord1", "mkt_a", "YES", "BUY", 0.5004)]  # diff = 0.0004 < 0.0005
    plan = diff_ladders(targets, live, [], matching=_matching(price_tol=0.0005))
    assert len(plan.keep) == 1
    assert len(plan.place) == 0


def test_price_outside_tolerance_no_match():
    targets = _targets(_ladder("mkt_a", "YES", "BUY", [(0.50, 100)]))
    live = [_live("ord1", "mkt_a", "YES", "BUY", 0.5006)]  # diff = 0.0006 > 0.0005
    plan = diff_ladders(targets, live, [], matching=_matching(price_tol=0.0005))
    assert len(plan.place) == 1  # unmatched target → place
    assert len(plan.cancel) == 1  # unmatched live on managed key → cancel


def test_price_exactly_at_tolerance_matches():
    targets = _targets(_ladder("mkt_a", "YES", "BUY", [(0.50, 100)]))
    live = [_live("ord1", "mkt_a", "YES", "BUY", 0.5005)]  # diff == 0.0005 exactly
    plan = diff_ladders(targets, live, [], matching=_matching(price_tol=0.0005))
    assert len(plan.keep) == 1


# ── shares mismatch → cancel + replace pair ───────────────────────────────────

def test_shares_mismatch_cancel_and_replace():
    targets = _targets(_ladder("mkt_a", "NO", "SELL", [(0.90, 150)]))
    # original_size=200 → remaining=200; target=150 → shares_mismatch
    live = [_live("ord1", "mkt_a", "NO", "SELL", 0.90, original_size=200)]
    plan = diff_ladders(targets, live, [], matching=_matching(shares_tol=1.0))

    assert len(plan.cancel) == 1
    assert plan.cancel[0].order_id == "ord1"
    assert plan.cancel[0].reason == "shares_mismatch"
    assert plan.cancel[0].replacement is not None
    assert plan.cancel[0].replacement.shares == 150

    assert len(plan.place) == 1
    assert plan.place[0].shares == 150


def test_shares_within_tolerance_kept():
    targets = _targets(_ladder("mkt_a", "NO", "SELL", [(0.90, 150)]))
    live = [_live("ord1", "mkt_a", "NO", "SELL", 0.90, original_size=150.5)]  # diff = 0.5 < 1.0
    plan = diff_ladders(targets, live, [], matching=_matching(shares_tol=1.0))

    assert len(plan.keep) == 1
    assert len(plan.cancel) == 0


# ── partial fill on remaining ─────────────────────────────────────────────────

def test_partial_fill_compared_on_remaining():
    """A partially filled order is compared on REMAINING shares, not original_size."""
    # Target: 100 shares. Live: original=200, matched=100, remaining=100. → keep.
    targets = _targets(_ladder("mkt_a", "YES", "BUY", [(0.50, 100)]))
    live = [_live("ord1", "mkt_a", "YES", "BUY", 0.50, original_size=200, matched=100)]
    plan = diff_ladders(targets, live, [], matching=_matching(shares_tol=1.0))
    assert len(plan.keep) == 1
    assert plan.keep[0].remaining == 100.0


# ── unmanaged orders ──────────────────────────────────────────────────────────

def test_unmanaged_orders_untouched_by_default():
    targets = _targets(_ladder("mkt_a", "YES", "BUY", [(0.50, 100)]))
    unmanaged_live = [_live("ord99", "mkt_b", "NO", "SELL", 0.80)]  # not a managed key
    plan = diff_ladders(targets, [*unmanaged_live], [], matching=_matching())
    # mkt_a/YES/BUY is managed; mkt_b/NO/SELL is unmanaged
    assert any(r.order_id == "ord99" for r in plan.unmanaged)
    assert not any(c.order_id == "ord99" for c in plan.cancel)


def test_manage_all_cancels_unmanaged():
    targets = _targets(_ladder("mkt_a", "YES", "BUY", [(0.50, 100)]))
    unmanaged_live = [_live("ord99", "mkt_b", "NO", "SELL", 0.80)]
    plan = diff_ladders(targets, [*unmanaged_live], [], matching=_matching(), manage_all=True)
    assert len(plan.unmanaged) == 0
    assert any(c.order_id == "ord99" for c in plan.cancel)
    assert plan.cancel[-1].reason == "not_in_target"


# ── unmapped orders surfaced ──────────────────────────────────────────────────

def test_unmapped_orders_surfaced():
    unmapped = [UnmappedOrder(raw={"id": "x1", "asset_id": "unknown"})]
    plan = diff_ladders(_targets(), [], unmapped, matching=_matching())
    assert len(plan.unmapped) == 1
    assert plan.unmapped[0].raw["id"] == "x1"


# ── deterministic ordering ────────────────────────────────────────────────────

def test_deterministic_ordering_by_market_price():
    targets = _targets(
        _ladder("mkt_b", "NO", "SELL", [(0.80, 100), (0.70, 50)]),
        _ladder("mkt_a", "YES", "BUY", [(0.60, 200)]),
    )
    plan = diff_ladders(targets, [], [], matching=_matching())
    prices = [(p.market_id, p.price) for p in plan.place]
    # mkt_a should come before mkt_b (alphabetical market_id)
    assert prices == sorted(prices)


# ── no preflight when no placements ──────────────────────────────────────────

def test_no_preflight_when_no_places():
    targets = _targets(_ladder("mkt_a", "NO", "SELL", [(0.90, 100)]))
    live = [_live("ord1", "mkt_a", "NO", "SELL", 0.90, original_size=100)]
    plan = diff_ladders(targets, live, [], matching=_matching())
    assert len(plan.place) == 0
    assert len(plan.preflight) == 0
