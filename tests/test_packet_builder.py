from __future__ import annotations

from polymarket_desk.packet_builder import build_packet


def test_build_packet_contains_required_sections() -> None:
    packet = build_packet()

    assert "Cash available" in packet
    assert "hormuz_normal_may15" in packet
    assert "Recent Catalysts" in packet
    assert "Trading Principles" in packet
    assert "Factual Source Data" in packet
    assert "Unresolved/Missing Information" in packet
    assert "Context Freshness Audit" in packet
    assert "Noisy Social-Media And Rumour Watch" in packet
    assert "Trader Interpretation Notes" in packet
    assert "does not verify live markets" in packet
