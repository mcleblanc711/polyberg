"""Tests for band boundary parsing — spec cases (d) plus surrounding coverage."""

from __future__ import annotations

import pytest

from polyberg.band_parser import BandBounds, parse_band_label


@pytest.mark.parametrize(
    "text, expected",
    [
        # --- spec case (d): inclusive vs exclusive boundary parsing ---
        # "X-Y" hyphen notation → inclusive both ends
        ("25-49", BandBounds(25.0, 49.0, True)),
        # "between X and Y" → exclusive (mathematical convention)
        ("between 25 and 49", BandBounds(25.0, 49.0, False)),
        # "under X" → no lower bound, exclusive upper
        ("under 10", BandBounds(None, 10.0, False)),
        # --- additional coverage ---
        # en-dash variant of hyphen
        ("10–20", BandBounds(10.0, 20.0, True)),
        # "X to Y" → inclusive
        ("10 to 20", BandBounds(10.0, 20.0, True)),
        # lower-bound-only patterns
        ("50+", BandBounds(50.0, None, True)),
        ("50 or more", BandBounds(50.0, None, True)),
        ("over 50", BandBounds(50.0, None, False)),
        ("more than 50", BandBounds(50.0, None, False)),
        # "<X" shorthand
        ("<10", BandBounds(None, 10.0, False)),
        # decimal bands
        ("0.5-1.5", BandBounds(0.5, 1.5, True)),
        # non-numeric / binary outcomes → all None
        ("Yes", BandBounds(None, None, None)),
        ("No", BandBounds(None, None, None)),
        ("", BandBounds(None, None, None)),
        ("some other text", BandBounds(None, None, None)),
    ],
)
def test_parse_band_label(text: str, expected: BandBounds) -> None:
    assert parse_band_label(text) == expected


def test_parse_band_label_case_insensitive() -> None:
    assert parse_band_label("UNDER 10") == BandBounds(None, 10.0, False)
    assert parse_band_label("Between 5 and 15") == BandBounds(5.0, 15.0, False)
    assert parse_band_label("50 OR MORE") == BandBounds(50.0, None, True)


def test_parse_band_label_strips_whitespace() -> None:
    assert parse_band_label("  25-49  ") == BandBounds(25.0, 49.0, True)
