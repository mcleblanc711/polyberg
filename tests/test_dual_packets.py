from __future__ import annotations

import json
import re

import pytest

from polyberg.packet_builder import (
    PACKET_FILENAMES,
    build_canonical_packet,
    write_model_packets,
)
from polyberg.packet_builder.renderers.claude_packet_renderer import render_claude_packet
from polyberg.packet_builder.renderers.gpt_packet_renderer import render_gpt_packet


def _extract_json_blocks(markdown: str) -> list[str]:
    return re.findall(r"```json\n(.*?)\n```", markdown, flags=re.DOTALL)


@pytest.fixture
def canonical():
    return build_canonical_packet()


def test_both_packets_render_from_same_canonical_object(canonical) -> None:
    gpt = render_gpt_packet(canonical)
    claude = render_claude_packet(canonical)

    assert gpt.startswith("# Polyberg Current Research Packet — GPT Source")
    assert claude.startswith("# Polyberg Current Research Packet — Claude Source")

    # Both embed the same compact machine-readable state, proving the factual
    # layer is identical and only the framing differs.
    gpt_json = _extract_json_blocks(gpt)[-1]
    claude_json = _extract_json_blocks(claude)[-1]
    assert json.loads(gpt_json) == json.loads(claude_json)


def test_both_packets_include_core_state(canonical) -> None:
    gpt = render_gpt_packet(canonical)
    claude = render_claude_packet(canonical)

    pv = f"{canonical.portfolio['portfolio_value']:.2f}"
    cash = f"{canonical.portfolio['cash_available']:.2f}"
    position_id = canonical.portfolio["positions"][0]["market_id"]

    for packet in (gpt, claude):
        assert pv in packet
        assert cash in packet
        assert position_id in packet
        # open orders section
        assert "Open Orders" in packet or "Open Orders".lower() in packet.lower()
        # missing info + freshness warnings surfaced
        assert "Missing" in packet
        assert "Freshness" in packet


def test_gpt_packet_has_compact_machine_readable_json(canonical) -> None:
    gpt = render_gpt_packet(canonical)
    assert "Compact Machine-Readable State" in gpt
    blocks = _extract_json_blocks(gpt)
    assert blocks, "expected a fenced JSON block in the GPT packet"
    state = json.loads(blocks[-1])
    assert state["portfolio"]["portfolio_value"] == canonical.portfolio["portfolio_value"]
    assert state["constraints"]["no_market_orders"] is True


def test_claude_packet_has_adversarial_critique_instructions(canonical) -> None:
    claude = render_claude_packet(canonical)
    assert "Adversarial Critique Instructions" in claude
    assert "attack this book" in claude.lower()
    assert "oracle event" in claude.lower()
    assert "world event" in claude.lower()
    assert "beats holding cash" in claude.lower() or "beat cash" in claude.lower()


def test_empty_buy_orders_render_as_none_not_broken_table(canonical) -> None:
    canonical.open_orders["buys"] = []
    gpt = render_gpt_packet(canonical)
    claude = render_claude_packet(canonical)

    order_table_header = (
        "| Market | Side | Price | Shares | Type | Notes |\n"
        "| --- | --- | ---: | ---: | --- | --- |\n\n"
    )
    for packet in (gpt, claude):
        # The empty buys placeholder is present and there is no header-only
        # (broken) table where a buy table would be.
        assert "_None._" in packet
        assert order_table_header not in packet


def test_missing_market_snapshot_renders_clear_warning() -> None:
    # The default real build has no snapshot path, so market_snapshot is None.
    canonical = build_canonical_packet()
    assert canonical.market_snapshot is None

    gpt = render_gpt_packet(canonical)
    claude = render_claude_packet(canonical)

    for packet in (gpt, claude):
        assert "no market snapshot" in packet.lower()
        assert "missing market snapshot" in packet.lower()


def test_no_market_orders_are_suggested_in_either_template(canonical) -> None:
    gpt = render_gpt_packet(canonical)
    claude = render_claude_packet(canonical)

    suggestive = [
        "place a market order",
        "use a market order",
        "submit a market order",
        "market buy",
        "market sell",
        "execute at market",
    ]
    for packet in (gpt, claude):
        low = packet.lower()
        collapsed = re.sub(r"\s+", " ", low)
        for phrase in suggestive:
            assert phrase not in collapsed, f"suggestive phrase leaked into packet: {phrase}"
        # The prohibition is present and the constraint is set.
        assert "no_market_orders" in low
        assert "never market orders" in collapsed or "no market orders" in collapsed


def test_write_model_packets_creates_both_files(tmp_path) -> None:
    out = tmp_path / "packets"
    paths = write_model_packets(target="all", output_dir=out)

    names = {p.name for p in paths}
    assert names == set(PACKET_FILENAMES.values())
    for p in paths:
        assert p.exists()
        assert p.read_text(encoding="utf-8").strip()
    # rules layer is emitted alongside the packets
    assert (out / "polymarket_rules.md").exists()


def test_write_model_packets_single_target(tmp_path) -> None:
    out = tmp_path / "packets"
    paths = write_model_packets(target="gpt", output_dir=out)
    assert [p.name for p in paths] == [PACKET_FILENAMES["gpt"]]
    assert not (out / PACKET_FILENAMES["claude"]).exists()
