"""Tests for ladder/render.py — markdown table and paste block."""
from __future__ import annotations

from polyberg.ladder.diff import (
    PREFLIGHT_DESCRIPTION,
    CancelAction,
    KeepAction,
    LadderPlan,
    PlaceAction,
)
from polyberg.ladder.live_orders import LiveRung, UnmappedOrder
from polyberg.ladder.render import plan_to_dict, render_plan

# ── helpers ───────────────────────────────────────────────────────────────────

def _plan(**kwargs):
    defaults = dict(
        preflight=[], cancel=[], place=[], keep=[], unmanaged=[], unmapped=[], warnings=[]
    )
    defaults.update(kwargs)
    return LadderPlan(**defaults)


def _cancel(
    order_id="c1", market_id="mkt_a", outcome="NO", action="SELL",
    price=0.90, shares=100.0, reason="not_in_target", replacement=None,
):
    return CancelAction(
        order_id=order_id, market_id=market_id, outcome=outcome, action=action,
        price=price, shares=shares, reason=reason, replacement=replacement,
    )


def _place(market_id="mkt_a", outcome="YES", action="BUY", price=0.50, shares=100.0, purpose=None):
    return PlaceAction(
        market_id=market_id, outcome=outcome, action=action,
        price=price, shares=shares, purpose=purpose,
    )


def _keep(order_id="k1", market_id="mkt_a", outcome="NO", action="SELL",
          price=0.80, remaining=100.0):
    return KeepAction(
        order_id=order_id, market_id=market_id, outcome=outcome, action=action,
        price=price, remaining=remaining,
    )


# ── section presence ──────────────────────────────────────────────────────────

def test_cancel_section_present():
    plan = _plan(cancel=[_cancel()])
    out = render_plan(plan)
    assert "### CANCEL" in out


def test_place_section_present():
    plan = _plan(place=[_place()], preflight=[PREFLIGHT_DESCRIPTION])
    out = render_plan(plan)
    assert "### PLACE" in out


def test_keep_section_present():
    plan = _plan(keep=[_keep()])
    out = render_plan(plan)
    assert "### KEEP" in out


def test_unmanaged_section_present():
    live = LiveRung("o1", "mkt_a", "NO", "SELL", 0.80, 100.0, 0.0, 100.0)
    plan = _plan(unmanaged=[live])
    out = render_plan(plan)
    assert "UNMANAGED" in out


def test_unmapped_section_present():
    plan = _plan(unmapped=[UnmappedOrder(raw={"id": "x"})])
    out = render_plan(plan)
    assert "UNRESOLVABLE" in out


def test_warnings_section_present():
    plan = _plan(warnings=["[stale-cash] from portfolio"])
    out = render_plan(plan)
    assert "## Warnings" in out
    assert "[stale-cash]" in out


def test_preflight_section_present():
    plan = _plan(preflight=[PREFLIGHT_DESCRIPTION], place=[_place()])
    out = render_plan(plan)
    assert "## Pre-flight" in out
    assert PREFLIGHT_DESCRIPTION in out


def test_empty_sections_absent():
    plan = _plan()
    out = render_plan(plan)
    assert "### CANCEL" not in out
    assert "### PLACE" not in out
    assert "### KEEP" not in out


# ── paste block ───────────────────────────────────────────────────────────────

def test_paste_block_present_when_places():
    plan = _plan(place=[_place()], preflight=[PREFLIGHT_DESCRIPTION])
    out = render_plan(plan, paste=True)
    assert "PLACE|" in out
    assert "PRE-FLIGHT|" in out


def test_paste_block_cancel_format():
    c = _cancel(order_id="abc123", market_id="mkt_a", outcome="NO", action="SELL",
                price=0.90, shares=150.0)
    plan = _plan(cancel=[c])
    out = render_plan(plan, paste=True)
    assert "CANCEL|mkt_a|NO|SELL|0.9000|150.0|order_id=abc123|" in out


def test_paste_block_place_format():
    p = _place(market_id="mkt_b", outcome="YES", action="BUY", price=0.72, shares=200.0)
    plan = _plan(place=[p], preflight=[PREFLIGHT_DESCRIPTION])
    out = render_plan(plan, paste=True)
    assert "PLACE|mkt_b|YES|BUY|0.7200|200.0|limit|" in out


def test_paste_block_includes_url_from_map():
    p = _place(market_id="mkt_a")
    plan = _plan(place=[p], preflight=[PREFLIGHT_DESCRIPTION])
    url_map = {"mkt_a": "https://polymarket.com/event/mkt_a"}
    out = render_plan(plan, url_map=url_map, paste=True)
    assert "https://polymarket.com/event/mkt_a" in out


def test_paste_block_suppressed_with_no_paste():
    plan = _plan(place=[_place()], preflight=[PREFLIGHT_DESCRIPTION])
    out = render_plan(plan, paste=False)
    assert "PLACE|" not in out
    assert "PRE-FLIGHT|" not in out


# ── preflight iff places ──────────────────────────────────────────────────────

def test_no_preflight_in_paste_when_no_places():
    plan = _plan(cancel=[_cancel()])
    out = render_plan(plan, paste=True)
    # cancel is present in paste block but no PRE-FLIGHT line since no places
    assert "CANCEL|" in out
    assert "PRE-FLIGHT|" not in out


def test_preflight_in_paste_only_when_places_exist():
    c = _cancel()
    p = _place()
    plan_with_place = _plan(cancel=[c], place=[p], preflight=[PREFLIGHT_DESCRIPTION])
    out = render_plan(plan_with_place, paste=True)
    assert "PRE-FLIGHT|" in out


# ── plan_to_dict (GUI JSON seam) ──────────────────────────────────────────────

def test_plan_to_dict_shape_and_indices():
    c = _cancel(order_id="c1", replacement=_place(price=0.91, shares=120.0))
    p = _place(market_id="mkt_b", outcome="YES", action="BUY", price=0.72, shares=200.0)
    plan = _plan(
        cancel=[c], place=[p], preflight=[PREFLIGHT_DESCRIPTION], warnings=["[stale-cash] x"]
    )
    url_map = {"mkt_a": "https://polymarket.com/event/mkt_a"}
    d = plan_to_dict(plan, url_map=url_map)

    assert d["summary"] == {"cancel": 1, "place": 1, "keep": 0, "unmanaged": 0, "unmapped": 0}
    assert d["warnings"] == ["[stale-cash] x"]
    assert d["preflight"] == [PREFLIGHT_DESCRIPTION]
    # stable, contiguous 1-based indices across CANCEL→PLACE order
    assert d["cancel"][0]["idx"] == 1
    assert d["place"][0]["idx"] == 2
    # cancel exposes order_id + replacement price + url + paste line
    assert d["cancel"][0]["order_id"] == "c1"
    assert d["cancel"][0]["replacement_price"] == 0.91
    assert d["cancel"][0]["url"] == "https://polymarket.com/event/mkt_a"
    assert d["cancel"][0]["paste"].startswith("CANCEL|")
    # place exposes the fields the GUI passes to record-manual
    place = d["place"][0]
    assert (place["market_id"], place["outcome"], place["action"]) == ("mkt_b", "YES", "BUY")
    assert place["paste"].startswith("PLACE|")


def test_plan_to_dict_unmapped_is_count():
    plan = _plan(unmapped=[UnmappedOrder(raw={"id": "x"}), UnmappedOrder(raw={"id": "y"})])
    d = plan_to_dict(plan)
    assert d["unmapped"] == 2
    assert d["summary"]["unmapped"] == 2
