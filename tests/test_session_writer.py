"""write_session pipeline tests: dir layout, manifest, pointer, collision
suffixes, mirror byte-equality, and validation-failure atomicity.

Reads use the real repo context (the test_dual_packets.py convention); every
write goes to tmp_path roots so no test touches reports/.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta

import pytest

from polyberg.config import get_timezone, repo_path
from polyberg.packet_builder.renderers import render_claude_packet, render_gpt_packet
from polyberg.packet_builder.session import SESSION_ID_RE
from polyberg.packet_builder.session_writer import SessionArtifact, write_session
from polyberg.validators import (
    ResponseValidationError,
    validate_canonical_session,
    validate_json_file,
)

_NOW = datetime(2026, 6, 22, 12, 0, tzinfo=get_timezone())


def _artifacts(tmp_path) -> list[SessionArtifact]:
    return [
        SessionArtifact(
            key="packet_gpt",
            filename="packet_gpt.md",
            render=lambda payload, state, cp: render_gpt_packet(cp),
            mirror_to=tmp_path / "generated" / "packet_gpt.md",
        ),
        SessionArtifact(
            key="packet_claude",
            filename="packet_claude.md",
            render=lambda payload, state, cp: render_claude_packet(cp),
        ),
        # Payload-reading artifact: static_reference texts come from the JSON,
        # not from a closure over the loading code.
        SessionArtifact(
            key="rules",
            filename="rules.md",
            render=lambda payload, state, cp: (
                payload["static_reference"]["trading_principles"]
                + payload["static_reference"]["stable_rules"]
            ),
            mirror_to=tmp_path / "generated" / "rules.md",
        ),
    ]


def _write(tmp_path, *, now: datetime = _NOW, artifacts=None, **kwargs):
    return write_session(
        artifacts if artifacts is not None else _artifacts(tmp_path),
        targets=["gpt", "claude"],
        now=now,
        sessions_root=tmp_path / "sessions",
        latest_pointer=tmp_path / "latest_session.txt",
        **kwargs,
    )


def test_session_dir_layout_and_on_disk_validation(tmp_path) -> None:
    result = _write(tmp_path)

    assert result.session_dir == tmp_path / "sessions" / result.session_id
    assert SESSION_ID_RE.fullmatch(result.session_id)
    assert result.canonical_path == result.session_dir / "canonical_session.json"
    validate_canonical_session(result.canonical_path)

    payload = json.loads(result.canonical_path.read_text(encoding="utf-8"))
    assert payload["session_id"] == result.session_id
    assert payload["generated_at"] == _NOW.isoformat()
    for path in result.written:
        assert path.exists()
        assert path.parent == result.session_dir


def test_manifest_lists_existing_files_and_matches_generated_at(tmp_path) -> None:
    result = _write(tmp_path)

    validate_json_file(
        result.manifest_path, repo_path("schemas", "session_manifest.schema.json")
    )
    manifest = json.loads(result.manifest_path.read_text(encoding="utf-8"))
    assert manifest["session_id"] == result.session_id
    assert manifest["created_at"] == _NOW.isoformat()
    assert manifest["files"]["canonical_session"] == "canonical_session.json"
    # Every listed file is a session-dir-relative name that exists; the
    # manifest itself is not listed (written last = completeness marker).
    assert "manifest" not in manifest["files"]
    for filename in manifest["files"].values():
        assert (result.session_dir / filename).exists()
    assert set(manifest["files"]) == {"canonical_session", "packet_gpt", "packet_claude", "rules"}


def test_latest_pointer_contains_bare_session_id(tmp_path) -> None:
    result = _write(tmp_path)
    pointer = (tmp_path / "latest_session.txt").read_text(encoding="utf-8")
    assert pointer == result.session_id + "\n"


def test_mirrors_are_byte_identical_to_session_files(tmp_path) -> None:
    result = _write(tmp_path)

    assert result.mirrored == [
        tmp_path / "generated" / "packet_gpt.md",
        tmp_path / "generated" / "rules.md",
    ]
    for mirror, session_name in [
        (result.mirrored[0], "packet_gpt.md"),
        (result.mirrored[1], "rules.md"),
    ]:
        assert mirror.read_bytes() == (result.session_dir / session_name).read_bytes()
    # No mirror requested for the claude artifact.
    assert not (tmp_path / "generated" / "packet_claude.md").exists()


def test_validation_failure_writes_nothing(tmp_path, monkeypatch) -> None:
    def _boom(payload, source="canonical_session payload") -> None:
        raise ResponseValidationError("forced failure")

    monkeypatch.setattr(
        "polyberg.packet_builder.session_writer.validate_canonical_session_payload",
        _boom,
    )
    with pytest.raises(ResponseValidationError, match="forced failure"):
        _write(tmp_path)

    assert not (tmp_path / "sessions").exists()
    assert not (tmp_path / "latest_session.txt").exists()
    assert not (tmp_path / "generated").exists()


def test_same_second_runs_get_suffixed_dirs_and_stay_consistent(tmp_path) -> None:
    first = _write(tmp_path)
    second = _write(tmp_path)
    third = _write(tmp_path)

    assert second.session_id == first.session_id + "_2"
    assert third.session_id == first.session_id + "_3"
    for result in (first, second, third):
        validate_canonical_session(result.canonical_path)
        payload = json.loads(result.canonical_path.read_text(encoding="utf-8"))
        manifest = json.loads(result.manifest_path.read_text(encoding="utf-8"))
        # id inside JSON and manifest always matches the final dir name
        assert payload["session_id"] == result.session_dir.name
        assert manifest["session_id"] == result.session_dir.name
    # pointer tracks the newest run
    pointer = (tmp_path / "latest_session.txt").read_text(encoding="utf-8")
    assert pointer == third.session_id + "\n"


def test_next_second_run_gets_unsuffixed_dir(tmp_path) -> None:
    first = _write(tmp_path)
    later = _write(tmp_path, now=_NOW + timedelta(seconds=1))
    assert later.session_id != first.session_id
    assert not later.session_id.startswith(first.session_id)


def test_without_static_reference_no_rules_are_embedded(tmp_path) -> None:
    artifacts = [
        SessionArtifact(
            key="packet_gpt",
            filename="packet_gpt.md",
            render=lambda payload, state, cp: render_gpt_packet(cp),
        )
    ]
    result = _write(tmp_path, artifacts=artifacts, include_static_reference=False)
    payload = json.loads(result.canonical_path.read_text(encoding="utf-8"))
    assert payload["static_reference"] == {}
    assert payload["source_timestamps"]["static_reference"] == {}


def test_write_model_packets_end_to_end_mirrored_filenames_unchanged(tmp_path) -> None:
    from polyberg.packet_builder import PACKET_FILENAMES, write_model_packets

    out = tmp_path / "generated"
    result = write_model_packets(
        target="all",
        output_dir=out,
        sessions_root=tmp_path / "sessions",
        latest_pointer=tmp_path / "latest_session.txt",
    )
    assert [p.name for p in result.mirrored] == [
        PACKET_FILENAMES["gpt"],
        PACKET_FILENAMES["claude"],
        "polymarket_rules.md",
    ]
    validate_canonical_session(result.canonical_path)
    for mirror in result.mirrored:
        assert mirror.parent == out
        assert mirror.read_bytes() == (result.session_dir / mirror.name).read_bytes()


def test_write_packet_end_to_end_mirrored_filenames_unchanged(tmp_path) -> None:
    from polyberg.packet_builder import write_packet

    output = tmp_path / "generated" / "packet.md"
    result = write_packet(
        output,
        sessions_root=tmp_path / "sessions",
        latest_pointer=tmp_path / "latest_session.txt",
    )
    assert result.mirrored == [output, output.parent / "polymarket_rules.md"]
    validate_canonical_session(result.canonical_path)
    for mirror in result.mirrored:
        assert mirror.read_bytes() == (result.session_dir / mirror.name).read_bytes()
    # legacy target list recorded
    payload = json.loads(result.canonical_path.read_text(encoding="utf-8"))
    assert payload["build_parameters"]["targets"] == ["legacy"]


def test_build_parameters_recorded(tmp_path) -> None:
    result = _write(tmp_path, include_resolved=True, catalyst_window_hours=12.0)
    payload = json.loads(result.canonical_path.read_text(encoding="utf-8"))
    params = payload["build_parameters"]
    assert params["targets"] == ["gpt", "claude"]
    assert params["include_resolved"] is True
    assert params["catalyst_window_hours"] == 12.0
    assert params["books_for"] == "active"
    assert params["type_filter"] is None
    assert params["context_dir"] is None
    assert params["snapshot_path"] is None
