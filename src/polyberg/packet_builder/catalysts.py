from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, datetime

from polyberg.models import MARKET_ID_RE

# Section headings used in context/recent_catalysts.md. The packet builder reads
# this human-curated markdown file; here we split it into the structured buckets
# the canonical packet object needs. We intentionally keep the parse forgiving:
# headings may drift slightly, so we match on a normalized substring.
CREDIBLE_HEADINGS = ("credible reporting watch",)
NOISY_HEADINGS = ("noisy social-media and rumour watch", "noisy social media and rumour watch")
TRADER_NOTE_HEADINGS = ("trader interpretation notes",)
UNRESOLVED_HEADINGS = ("unresolved/missing information", "unresolved missing information")

# Leading ingest stamp on a catalyst bullet, e.g. "[2026-06-04 01:04Z] …".
# This is when the entry was recorded (ingest time), not the event date inside
# the text — windowing keys on this and never on event-time content.
_TIMESTAMP_RE = re.compile(r"^\[(\d{4}-\d{2}-\d{2})[ T](\d{1,2}:\d{2})Z\]")
# Bold-wrapped market tag, e.g. "**hormuz_normal_jul31**". Validated against
# MARKET_ID_RE so bold prose (e.g. "**BREAKING:**") is not mistaken for a tag.
_BOLD_RE = re.compile(r"\*\*([^*]+)\*\*")


@dataclass(frozen=True)
class CatalystEntry:
    """A single catalyst bullet decomposed for windowing and scoping."""

    text: str
    ingested_at: datetime | None
    market_ids: tuple[str, ...]


@dataclass(frozen=True)
class ParsedCatalysts:
    credible_reporting_watch: list[str]
    noisy_social_media_watch: list[str]
    trader_notes: list[str]
    unresolved_missing_information: list[str]


def parse_catalysts(markdown: str) -> ParsedCatalysts:
    """Split the curated recent_catalysts.md into structured buckets.

    Returns top-level bullet entries (lines beginning with ``- ``) grouped under
    each known section heading. Continuation lines (multi-line tweet bodies)
    fold into the preceding entry so a single catalyst stays one entry.
    """
    sections = _split_sections(markdown)
    return ParsedCatalysts(
        credible_reporting_watch=_bullets_for(sections, CREDIBLE_HEADINGS),
        noisy_social_media_watch=_bullets_for(sections, NOISY_HEADINGS),
        trader_notes=_bullets_for(sections, TRADER_NOTE_HEADINGS),
        unresolved_missing_information=_bullets_for(sections, UNRESOLVED_HEADINGS),
    )


def parse_catalyst_entry(text: str) -> CatalystEntry:
    """Decompose a single bullet into ingest time + tagged market ids."""
    ingested_at: datetime | None = None
    match = _TIMESTAMP_RE.match(text.strip())
    if match:
        day, hm = match.group(1), match.group(2)
        try:
            hour, minute = (int(part) for part in hm.split(":"))
            year, month, dom = (int(part) for part in day.split("-"))
            ingested_at = datetime(year, month, dom, hour, minute, tzinfo=UTC)
        except ValueError:
            ingested_at = None
    market_ids = tuple(
        token
        for token in (m.strip() for m in _BOLD_RE.findall(text))
        if MARKET_ID_RE.fullmatch(token)
    )
    return CatalystEntry(text=text, ingested_at=ingested_at, market_ids=market_ids)


def _dedup_key(text: str) -> str:
    """Normalize a bullet for near-identical dedup: drop the leading ingest
    stamp, collapse whitespace, lowercase. Re-ingests of the same item under a
    new timestamp collapse to one entry."""
    without_stamp = _TIMESTAMP_RE.sub("", text.strip())
    return " ".join(without_stamp.split()).lower()


def _filter_watch_list(
    entries: list[str],
    *,
    now: datetime,
    window_hours: float,
    active_ids: Iterable[str],
) -> list[str]:
    """Keep a watch bullet iff it was ingested within the window AND tags a
    market in the active set; then drop near-identical duplicates."""
    active = set(active_ids)
    kept: list[str] = []
    seen: set[str] = set()
    for text in entries:
        entry = parse_catalyst_entry(text)
        if entry.ingested_at is None:
            continue
        age_hours = (now - entry.ingested_at.astimezone(now.tzinfo)).total_seconds() / 3600
        if age_hours > window_hours or age_hours < 0:
            continue
        if not any(market_id in active for market_id in entry.market_ids):
            continue
        key = _dedup_key(text)
        if key in seen:
            continue
        seen.add(key)
        kept.append(text)
    return kept


def filter_catalysts(
    parsed: ParsedCatalysts,
    *,
    now: datetime,
    window_hours: float,
    active_ids: Iterable[str],
) -> ParsedCatalysts:
    """Window + scope + dedup the credible/noisy watch lists.

    Trader notes and unresolved/missing information are operator notes, not
    timestamped market catalysts, so they pass through unfiltered.
    """
    active = set(active_ids)
    return ParsedCatalysts(
        credible_reporting_watch=_filter_watch_list(
            parsed.credible_reporting_watch,
            now=now,
            window_hours=window_hours,
            active_ids=active,
        ),
        noisy_social_media_watch=_filter_watch_list(
            parsed.noisy_social_media_watch,
            now=now,
            window_hours=window_hours,
            active_ids=active,
        ),
        trader_notes=list(parsed.trader_notes),
        unresolved_missing_information=list(parsed.unresolved_missing_information),
    )


def _normalize_heading(text: str) -> str:
    return text.strip().lstrip("#").strip().lower()


def _split_sections(markdown: str) -> dict[str, list[str]]:
    sections: dict[str, list[str]] = {}
    current: str | None = None
    for line in markdown.splitlines():
        if line.startswith("## "):
            current = _normalize_heading(line)
            sections.setdefault(current, [])
            continue
        if current is not None:
            sections[current].append(line)
    return sections


def _bullets_for(sections: dict[str, list[str]], headings: tuple[str, ...]) -> list[str]:
    lines: list[str] | None = None
    for key, value in sections.items():
        if any(h in key for h in headings):
            lines = value
            break
    if lines is None:
        return []
    return _group_bullets(lines)


def _group_bullets(lines: list[str]) -> list[str]:
    entries: list[str] = []
    current: list[str] = []
    for raw in lines:
        if raw.startswith("- "):
            if current:
                entries.append(_finish(current))
            current = [raw[2:].strip()]
        elif current and raw.strip():
            current.append(raw.strip())
        # blank lines between continuation text are dropped; a new "- " starts
        # the next entry.
    if current:
        entries.append(_finish(current))
    return [e for e in entries if e]


def _finish(parts: list[str]) -> str:
    return " ".join(p for p in parts if p).strip()
