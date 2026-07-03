"""Guard the hard safety boundary at the code level.

Scope is deliberate: the execution-shaped identifier scan covers only
packet_builder/ (ladder/ legitimately contains a cancel-only ``cancel_order``);
the execution_allowed flip scan covers all of src/polyberg/.
"""

from __future__ import annotations

import re
from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / "src" / "polyberg"

# Word boundaries keep legitimate uses like no_market_orders out of scope.
FORBIDDEN_IDENTIFIERS = re.compile(
    r"\b(place_order|cancel_order|sign_order|market_order|private_key)\b"
)

# Matches execution_allowed=True, execution_allowed = True, and
# "execution_allowed": True — no code path may flip the pinned const.
EXECUTION_ALLOWED_TRUE = re.compile(r"execution_allowed[\"']?\s*[:=]\s*True")


def _py_files(root: Path) -> list[Path]:
    return sorted(root.rglob("*.py"))


def test_packet_builder_has_no_forbidden_identifiers() -> None:
    offenders: list[str] = []
    for path in _py_files(SRC / "packet_builder"):
        text = path.read_text(encoding="utf-8")
        offenders.extend(
            f"{path.relative_to(SRC)}: {match.group(0)}"
            for match in FORBIDDEN_IDENTIFIERS.finditer(text)
        )
    assert offenders == []


def test_no_code_path_sets_execution_allowed_true_src_wide() -> None:
    offenders = [
        str(path.relative_to(SRC))
        for path in _py_files(SRC)
        if EXECUTION_ALLOWED_TRUE.search(path.read_text(encoding="utf-8"))
    ]
    assert offenders == []
