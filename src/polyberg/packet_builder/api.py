from __future__ import annotations

from datetime import datetime
from pathlib import Path

from polyberg.config import get_timezone
from polyberg.packet_builder.legacy import build_rules
from polyberg.packet_builder.normalize_packet_state import (
    CanonicalPacket,
    build_canonical_packet,
)
from polyberg.packet_builder.renderers import render_claude_packet, render_gpt_packet

# Model targets and their renderers. Both render from the same CanonicalPacket,
# so the factual layer is identical and only framing differs.
RENDERERS = {
    "gpt": render_gpt_packet,
    "claude": render_claude_packet,
}

TARGETS = tuple(RENDERERS)

PACKET_FILENAMES = {
    "gpt": "Polyberg_Current_Research_Packet_GPT_Source.md",
    "claude": "Polyberg_Current_Research_Packet_Claude_Source.md",
}


def resolve_targets(target: str) -> list[str]:
    if target == "all":
        return list(TARGETS)
    if target not in RENDERERS:
        raise ValueError(
            f"Unknown packet target {target!r}. Use one of: {', '.join(TARGETS)}, all."
        )
    return [target]


def render_model_packet(target: str, canonical: CanonicalPacket) -> str:
    try:
        renderer = RENDERERS[target]
    except KeyError as exc:
        raise ValueError(
            f"Unknown packet target {target!r}. Use one of: {', '.join(TARGETS)}."
        ) from exc
    return renderer(canonical)


def build_model_packet(
    target: str,
    now: datetime | None = None,
    context_dir: Path | None = None,
    snapshot_path: Path | None = None,
    canonical: CanonicalPacket | None = None,
) -> str:
    if canonical is None:
        canonical = build_canonical_packet(
            now=now, context_dir=context_dir, snapshot_path=snapshot_path
        )
    return render_model_packet(target, canonical)


def write_model_packets(
    target: str,
    output_dir: Path,
    context_dir: Path | None = None,
    snapshot_path: Path | None = None,
    now: datetime | None = None,
    write_rules: bool = True,
) -> list[Path]:
    """Render the requested target(s) from one canonical object and write them.

    A single CanonicalPacket backs every variant so the factual data is
    guaranteed identical across exports. Also emits ``polymarket_rules.md`` next
    to the packets (the stable rules layer) unless ``write_rules`` is False.
    """
    targets = resolve_targets(target)
    if now is None:
        now = datetime.now(get_timezone())
    canonical = build_canonical_packet(
        now=now, context_dir=context_dir, snapshot_path=snapshot_path
    )

    output_dir.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    for name in targets:
        path = output_dir / PACKET_FILENAMES[name]
        path.write_text(render_model_packet(name, canonical), encoding="utf-8")
        written.append(path)

    if write_rules:
        rules_path = output_dir / "polymarket_rules.md"
        rules_path.write_text(build_rules(context_dir=context_dir), encoding="utf-8")

    return written
