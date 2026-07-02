from __future__ import annotations

from datetime import datetime
from pathlib import Path

from polyberg.lifecycle import MarketTypeFilter
from polyberg.packet_builder.legacy import render_rules_from_session
from polyberg.packet_builder.normalize_packet_state import (
    CanonicalPacket,
    build_canonical_packet,
)
from polyberg.packet_builder.renderers import render_claude_packet, render_gpt_packet
from polyberg.packet_builder.session_writer import (
    SessionArtifact,
    SessionResult,
    write_session,
)

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
    *,
    include_resolved: bool = False,
    catalyst_window_hours: float | None = None,
    books_for: str = "active",
    type_filter: MarketTypeFilter | None = None,
    sessions_root: Path | None = None,
    latest_pointer: Path | None = None,
) -> SessionResult:
    """Render the requested target(s) through the session pipeline.

    One validated canonical_session.json backs every variant: packets are
    rendered from state reconstructed out of it, so the factual data is
    guaranteed identical across exports, and mirrored byte-identical into
    ``output_dir``. Also emits ``polymarket_rules.md`` next to the packets (the
    stable rules layer) unless ``write_rules`` is False.
    """
    targets = resolve_targets(target)
    artifacts = [
        SessionArtifact(
            key=f"packet_{name}",
            filename=PACKET_FILENAMES[name],
            render=lambda payload, state, cp, _target=name: render_model_packet(_target, cp),
            mirror_to=output_dir / PACKET_FILENAMES[name],
        )
        for name in targets
    ]
    if write_rules:
        artifacts.append(
            SessionArtifact(
                key="rules",
                filename="polymarket_rules.md",
                render=render_rules_from_session,
                mirror_to=output_dir / "polymarket_rules.md",
            )
        )
    return write_session(
        artifacts,
        targets=targets,
        now=now,
        context_dir=context_dir,
        snapshot_path=snapshot_path,
        include_resolved=include_resolved,
        catalyst_window_hours=catalyst_window_hours,
        books_for=books_for,
        type_filter=type_filter,
        include_static_reference=write_rules,
        sessions_root=sessions_root,
        latest_pointer=latest_pointer,
    )
