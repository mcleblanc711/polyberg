from __future__ import annotations

# Backwards-compatible re-exports: the original `polyberg.packet_builder` module
# is now a package. Existing imports (build_packet, build_rules, write_packet)
# keep working unchanged.
from polyberg.packet_builder.api import (
    PACKET_FILENAMES,
    TARGETS,
    build_model_packet,
    render_model_packet,
    resolve_targets,
    write_model_packets,
)
from polyberg.packet_builder.legacy import build_packet, build_rules, write_packet
from polyberg.packet_builder.normalize_packet_state import (
    CanonicalPacket,
    build_canonical_packet,
)

__all__ = [
    "build_packet",
    "build_rules",
    "write_packet",
    "build_canonical_packet",
    "CanonicalPacket",
    "build_model_packet",
    "render_model_packet",
    "write_model_packets",
    "resolve_targets",
    "PACKET_FILENAMES",
    "TARGETS",
]
