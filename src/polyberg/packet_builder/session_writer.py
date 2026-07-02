"""The one write pipeline behind every packet-producing command.

Ordering is the contract (see docs/INTERFACE_CONTRACT.md): the session payload
is validated IN MEMORY before anything touches the filesystem, so a contract
violation writes nothing. Artifacts are rendered from state reconstructed out
of the just-validated payload — not from the in-memory objects that built it —
which is what makes "packets are views of the JSON" enforced rather than
asserted. The manifest is written last: a session dir without manifest.json is
an abandoned session and consumers must ignore it. Mirrors receive the same
rendered strings, byte-identical to the session files.
"""

from __future__ import annotations

import json
import os
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from polyberg.config import get_catalyst_window_hours, get_max_context_age_hours, repo_path
from polyberg.lifecycle import MarketTypeFilter
from polyberg.loaders import context_path, read_text_file
from polyberg.packet_builder.collect_state import PacketState, collect_packet_state
from polyberg.packet_builder.normalize_packet_state import (
    CanonicalPacket,
    build_canonical_packet,
)
from polyberg.packet_builder.session import (
    SessionBuildParameters,
    SessionTypeFilterParameters,
    build_canonical_session,
    canonical_packet_from_session,
    new_session_id,
    packet_state_from_session,
)
from polyberg.validators import validate_canonical_session_payload

CANONICAL_SESSION_FILENAME = "canonical_session.json"
MANIFEST_FILENAME = "manifest.json"


@dataclass(frozen=True)
class SessionArtifact:
    """One rendered file inside a session dir.

    ``render`` receives the validated payload plus the state/packet
    reconstructed from it; payload-only facts (static_reference texts, build
    parameters) must be read from the payload, never closed over.
    ``mirror_to`` re-writes the identical bytes at a legacy output path.
    """

    key: str
    filename: str
    render: Callable[[dict[str, Any], PacketState, CanonicalPacket], str]
    mirror_to: Path | None = None


@dataclass(frozen=True)
class SessionResult:
    session_id: str
    session_dir: Path
    canonical_path: Path
    manifest_path: Path
    written: list[Path]
    mirrored: list[Path]


def write_session(
    artifacts: list[SessionArtifact],
    *,
    targets: list[str],
    now: datetime | None = None,
    context_dir: Path | None = None,
    snapshot_path: Path | None = None,
    include_resolved: bool = False,
    catalyst_window_hours: float | None = None,
    books_for: str = "active",
    type_filter: MarketTypeFilter | None = None,
    include_static_reference: bool = True,
    sessions_root: Path | None = None,
    latest_pointer: Path | None = None,
) -> SessionResult:
    if sessions_root is None:
        sessions_root = repo_path("reports", "sessions")
    if latest_pointer is None:
        latest_pointer = repo_path("reports", "latest_session.txt")

    # 1–2. Collect + derive. A LoaderError here writes nothing, as today.
    state = collect_packet_state(
        now=now, context_dir=context_dir, snapshot_path=snapshot_path
    )
    if catalyst_window_hours is None:
        catalyst_window_hours = get_catalyst_window_hours()
    canonical = build_canonical_packet(
        state=state,
        include_resolved=include_resolved,
        catalyst_window_hours=catalyst_window_hours,
        books_for=books_for,
        type_filter=type_filter,
    )

    # Rules files are only read when this run embeds them (write_rules paths);
    # other runs must not gain new file reads — behavior-neutral.
    static_reference_texts = None
    if include_static_reference:
        static_reference_texts = {
            "trading_principles": read_text_file(
                context_path(context_dir, "trading_principles.md")
            ),
            "stable_rules": read_text_file(context_path(context_dir, "stable_rules.md")),
        }

    build_parameters = SessionBuildParameters(
        targets=list(targets),
        include_resolved=include_resolved,
        catalyst_window_hours=float(catalyst_window_hours),
        books_for=books_for,
        type_filter=(
            SessionTypeFilterParameters(
                category=type_filter.category,
                thesis_bucket=type_filter.thesis_bucket,
                rule_key=type_filter.rule_key,
            )
            if type_filter is not None
            else None
        ),
        max_context_age_hours=get_max_context_age_hours(),
        context_dir=str(context_dir) if context_dir is not None else None,
        snapshot_path=str(snapshot_path) if snapshot_path is not None else None,
    )

    # 3. Build + validate the payload before any file or dir exists; a
    # validation failure has zero filesystem effects.
    session = build_canonical_session(
        state,
        canonical,
        session_id=new_session_id(state.now),
        build_parameters=build_parameters,
        static_reference_texts=static_reference_texts,
    )
    payload = session.model_dump(mode="json")
    validate_canonical_session_payload(payload)

    # 4. Claim the session dir; same-second runs retry with _2, _3, … and the
    # id inside the JSON/manifest always matches the final dir name.
    sessions_root.mkdir(parents=True, exist_ok=True)
    base_id = payload["session_id"]
    session_id = base_id
    suffix = 1
    while True:
        session_dir = sessions_root / session_id
        try:
            session_dir.mkdir(exist_ok=False)
            break
        except FileExistsError:
            suffix += 1
            session_id = f"{base_id}_{suffix}"
    payload["session_id"] = session_id

    # 5. The canonical artifact itself.
    canonical_path = session_dir / CANONICAL_SESSION_FILENAME
    canonical_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

    # 6. Render every artifact from state reconstructed out of the payload.
    rebuilt_state = packet_state_from_session(payload)
    rebuilt_canonical = canonical_packet_from_session(payload)
    written: list[Path] = [canonical_path]
    rendered: list[tuple[SessionArtifact, str]] = []
    for artifact in artifacts:
        text = artifact.render(payload, rebuilt_state, rebuilt_canonical)
        path = session_dir / artifact.filename
        path.write_text(text, encoding="utf-8")
        written.append(path)
        rendered.append((artifact, text))

    # 7. Manifest last — its presence marks the session complete.
    manifest = {
        "session_id": session_id,
        "created_at": payload["generated_at"],
        "files": {
            "canonical_session": CANONICAL_SESSION_FILENAME,
            **{artifact.key: artifact.filename for artifact in artifacts},
        },
    }
    manifest_path = session_dir / MANIFEST_FILENAME
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    written.append(manifest_path)

    # 8. Latest pointer: bare session_id, swapped in atomically.
    latest_pointer.parent.mkdir(parents=True, exist_ok=True)
    tmp_pointer = latest_pointer.with_name(latest_pointer.name + ".tmp")
    tmp_pointer.write_text(session_id + "\n", encoding="utf-8")
    os.replace(tmp_pointer, latest_pointer)

    # 9. Mirrors: identical bytes at today's output paths (GUI untouched).
    mirrored: list[Path] = []
    for artifact, text in rendered:
        if artifact.mirror_to is None:
            continue
        artifact.mirror_to.parent.mkdir(parents=True, exist_ok=True)
        artifact.mirror_to.write_text(text, encoding="utf-8")
        mirrored.append(artifact.mirror_to)

    return SessionResult(
        session_id=session_id,
        session_dir=session_dir,
        canonical_path=canonical_path,
        manifest_path=manifest_path,
        written=written,
        mirrored=mirrored,
    )
