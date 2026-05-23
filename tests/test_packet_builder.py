from __future__ import annotations

import shutil

from polyberg.config import repo_path
from polyberg.packet_builder import build_packet, build_rules


def test_build_packet_contains_required_sections() -> None:
    packet = build_packet()

    assert "Cash available" in packet
    assert "hormuz_normal_end_june" in packet
    assert "Recent Catalysts" in packet
    assert "Factual Source Data" in packet
    assert "Unresolved/Missing Information" in packet
    assert "Context Freshness Audit" in packet
    assert "Noisy Social-Media And Rumour Watch" in packet
    assert "Trader Interpretation Notes" in packet
    assert "does not verify live markets" in packet
    assert "Missing Info And Safety Warnings" in packet
    assert "Exposure Summary By Thesis Bucket" in packet
    assert "Rule risk" in packet
    assert "generated_at" in packet
    assert "freshness_warnings" in packet
    assert "Trading Principles" not in packet
    assert "Stable Rules Reference" not in packet


def test_build_rules_contains_principles_and_rules() -> None:
    rules = build_rules()

    assert "Trading Principles" in rules
    assert "Stable Rules Reference" in rules
    assert "generated_at" not in rules


def test_build_packet_works_with_context_dir(tmp_path) -> None:
    context_dir = tmp_path / "context"
    shutil.copytree(repo_path("context"), context_dir)

    packet = build_packet(context_dir=context_dir)

    assert "Polymarket Research Packet" in packet
    assert "hormuz_normal_end_june" in packet


def test_build_packet_works_with_snapshot(tmp_path) -> None:
    snapshot = tmp_path / "snapshot.json"
    snapshot.write_text(
        """
{
  "as_of": "2026-04-26T09:00:00-06:00",
  "markets": [
    {
      "market_id": "hormuz_normal_end_june",
      "yes_price": 0.4,
      "no_price": 0.6,
      "best_bid_yes": 0.39,
      "best_ask_yes": 0.41,
      "best_bid_no": 0.59,
      "best_ask_no": 0.61,
      "spread": 0.02,
      "orderbook_depth_top": 100,
      "liquidity_warning": false,
      "missing_info": []
    }
  ]
}
""".strip(),
        encoding="utf-8",
    )

    packet = build_packet(snapshot_path=snapshot)

    assert "Market Snapshot" in packet
    assert "0.400" in packet


def test_recent_catalysts_heading_is_normalized() -> None:
    packet = build_packet()

    assert "## Trader Notes And Catalyst Watch\n\n# Recent Catalysts" not in packet
