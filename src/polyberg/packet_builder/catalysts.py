from __future__ import annotations

from dataclasses import dataclass

# Section headings used in context/recent_catalysts.md. The packet builder reads
# this human-curated markdown file; here we split it into the structured buckets
# the canonical packet object needs. We intentionally keep the parse forgiving:
# headings may drift slightly, so we match on a normalized substring.
CREDIBLE_HEADINGS = ("credible reporting watch",)
NOISY_HEADINGS = ("noisy social-media and rumour watch", "noisy social media and rumour watch")
TRADER_NOTE_HEADINGS = ("trader interpretation notes",)
UNRESOLVED_HEADINGS = ("unresolved/missing information", "unresolved missing information")


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
