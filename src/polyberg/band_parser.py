"""Parse numeric band boundaries from Polymarket outcome labels.

Handles the most common patterns produced by Polymarket's categorical markets:
  "10-20", "25–49"          → inclusive both ends
  "10 to 20"                → inclusive both ends
  "between 25 and 49"       → exclusive both ends (mathematical "between")
  "under 10", "<10"         → exclusive upper bound only
  "50+", "50 or more"       → inclusive lower bound only
  "over 50", "more than 50" → exclusive lower bound only
"""

from __future__ import annotations

import re
from typing import NamedTuple


class BandBounds(NamedTuple):
    low: float | None
    high: float | None
    # True = both stated bounds are inclusive; False = exclusive; None = not a numeric band
    inclusive: bool | None


_HYPHEN = re.compile(r"^(\d+(?:\.\d+)?)\s*[-–]\s*(\d+(?:\.\d+)?)$")
_TO = re.compile(r"^(\d+(?:\.\d+)?)\s+to\s+(\d+(?:\.\d+)?)$", re.IGNORECASE)
_BETWEEN = re.compile(
    r"^between\s+(\d+(?:\.\d+)?)\s+and\s+(\d+(?:\.\d+)?)$", re.IGNORECASE
)
_UNDER = re.compile(
    r"^(?:under|less\s+than|below|<)\s*(\d+(?:\.\d+)?)$", re.IGNORECASE
)
_N_PLUS = re.compile(r"^(\d+(?:\.\d+)?)\+$")
_N_OR_MORE = re.compile(r"^(\d+(?:\.\d+)?)\s+or\s+more$", re.IGNORECASE)
_OVER = re.compile(
    r"^(?:over|more\s+than|above|>)\s*(\d+(?:\.\d+)?)$", re.IGNORECASE
)

_NOT_A_BAND = BandBounds(None, None, None)


def parse_band_label(text: str) -> BandBounds:
    """Return (low, high, inclusive) for a numeric band label, or (None, None, None)."""
    t = text.strip()
    if not t:
        return _NOT_A_BAND

    m = _HYPHEN.match(t)
    if m:
        return BandBounds(float(m.group(1)), float(m.group(2)), True)

    m = _TO.match(t)
    if m:
        return BandBounds(float(m.group(1)), float(m.group(2)), True)

    m = _BETWEEN.match(t)
    if m:
        return BandBounds(float(m.group(1)), float(m.group(2)), False)

    m = _UNDER.match(t)
    if m:
        return BandBounds(None, float(m.group(1)), False)

    m = _N_PLUS.match(t)
    if m:
        return BandBounds(float(m.group(1)), None, True)

    m = _N_OR_MORE.match(t)
    if m:
        return BandBounds(float(m.group(1)), None, True)

    m = _OVER.match(t)
    if m:
        return BandBounds(float(m.group(1)), None, False)

    return _NOT_A_BAND
