"""Deterministically suggest the *judgment* fields for a new registry market.

The Add Market flow already auto-fills the *identifier* fields (condition_id,
token IDs, name, resolution date) from Polymarket Gamma. This module fills the
gap the TODO calls out: derive the *judgment* fields (category, thesis_bucket,
rule_key, oracle_type, preferred_side, risk_flags, notes, rule_risk) so the GUI
can present a fully pre-populated review step instead of a blank form.

No LLM is involved — the repo has no model client and the one key-dependent path
is blocked. Two deterministic strategies, in priority order:

1. **Nearest-neighbour inheritance.** Most markets the user adds are new dates or
   brackets of an *existing* event family (Hormuz transit counts, warships by
   country, peace-deal-by-date). When the new event matches an existing registry
   entry strongly enough, inherit that entry's curated judgment fields verbatim —
   this is both deterministic and high quality.
2. **Rules/keyword fallback.** With no neighbour, mine the Gamma resolution
   ``description`` + ``tags`` + ``resolution_source`` for the oracle kind, risk
   flags, and a derived ``rule_risk`` block.

Every suggested field is tagged in ``sources`` with how it was derived
(``inherited`` / ``rules`` / ``default``) so the GUI can badge confident
inheritance differently from a generic guess. Nothing here writes to disk; the
human reviews and confirms before the entry is committed.
"""

from __future__ import annotations

import re
from datetime import date

from polyberg.models import Market, MarketRegistry
from polyberg.registry_editor import market_display_name, suggest_market_id

# Slug/keyword tokens that carry no matching signal.
_STOPWORDS = frozenset(
    {
        "the", "a", "an", "of", "by", "on", "in", "to", "is", "are", "will",
        "and", "or", "for", "be", "with", "at", "this", "that", "any", "how",
        "many", "does", "do", "us", "x", "vs", "via", "end", "week", "day",
    }
)
# A bracket label that denotes one band of a negative-risk multi-outcome market.
_BAND_RE = re.compile(r"^[<>]?\s*\d+(\s*[-–]\s*\d+)?\+?\s*(ships?)?$", re.IGNORECASE)
# Tokens we never want as match signal: bare numbers, dates, month names.
_MONTHS = frozenset(
    "january february march april may june july august september october "
    "november december".split()
)


def _tokens(text: str) -> set[str]:
    """Lower-case word/keyword set, dropping stopwords, numbers, and months."""
    words = re.split(r"[^a-z0-9]+", (text or "").lower())
    out: set[str] = set()
    for w in words:
        if not w or w in _STOPWORDS or w in _MONTHS or w.isdigit():
            continue
        out.add(w)
    return out


def _candidate_keywords(candidate: dict, market: dict) -> set[str]:
    parts = [
        candidate.get("event_slug") or "",
        candidate.get("name") or "",
        market.get("question") or "",
        " ".join(candidate.get("tags") or []),
    ]
    return _tokens(" ".join(parts))


def _entry_keywords(entry: Market) -> set[str]:
    parts = [
        entry.event_slug or "",
        entry.name,
        entry.category,
        entry.thesis_bucket,
    ]
    return _tokens(" ".join(parts))


def _suggest_market_id(candidate: dict, market: dict) -> str:
    """A clean, collision-safe market_id from the event slug + bracket label.

    The event slug already carries the distinguishing date ("week-of-june-8"), so
    different weeks/brackets get distinct ids. Stopwords are dropped to keep it
    short; numbers and months are kept because they disambiguate. Falls back to
    the display-name slug if the event has no usable slug.
    """
    raw = candidate.get("event_slug") or market_display_name(candidate, market)
    tokens = [t for t in re.split(r"[^a-z0-9]+", (raw or "").lower()) if t and t not in _STOPWORDS]
    base = "_".join(tokens)
    band = (market.get("group_item_title") or "").strip()
    if band:
        band_clean = re.sub(r"[^a-z0-9]+", "_", band.lower()).strip("_")
        if band_clean:
            base = f"{base}_{band_clean}" if base else band_clean
    return base or suggest_market_id(market_display_name(candidate, market))


def _is_band_market(market: dict) -> bool:
    """A bucketed (negative-risk) outcome, e.g. ``50-74`` / ``<25`` / ``>60``."""
    label = (market.get("group_item_title") or "").strip()
    return bool(label) and bool(_BAND_RE.match(label))


def find_nearest(
    candidate: dict, market: dict, registry: MarketRegistry
) -> tuple[Market | None, float]:
    """Best-matching existing entry by keyword overlap, and its match score.

    An exact ``event_slug`` match (a different bracket of the same event) scores
    1.0. Otherwise the Jaccard overlap of keyword bags is used.
    """
    cand_slug = candidate.get("event_slug")
    cand_kw = _candidate_keywords(candidate, market)
    if not cand_kw:
        return None, 0.0
    best: Market | None = None
    best_score = 0.0
    for entry in registry.markets:
        if cand_slug and entry.event_slug == cand_slug:
            return entry, 1.0
        entry_kw = _entry_keywords(entry)
        if not entry_kw:
            continue
        overlap = len(cand_kw & entry_kw)
        if not overlap:
            continue
        score = overlap / len(cand_kw | entry_kw)
        if score > best_score:
            best, best_score = entry, score
    return best, best_score

# At or above this Jaccard overlap we treat the nearest entry as the same family
# and inherit its curated judgment fields.
INHERIT_THRESHOLD = 0.34


def _derive_oracle(text: str) -> tuple[str, str]:
    """Return ``(oracle_type, rule_risk_kind)`` mined from the rules text."""
    low = text.lower()
    if "portwatch" in low:
        return "IMF Portwatch data", "pure_data"
    if any(w in low for w in ("announce", "official", "statement", "declares")):
        return (
            "Official announcement OR consensus of credible reporting",
            "official_statement_required",
        )
    return "UMA resolution", "official_statement_required"


def _derive_rule_key(oracle_kind: str, is_band: bool, text: str) -> str:
    low = text.lower()
    if "portwatch" in low:
        if "7-day moving average" in low or "7 day moving average" in low:
            return "hormuz_portwatch_7dma"
        if is_band:
            return "hormuz_portwatch_count_band"
        if "any day" in low or "on any single day" in low:
            return "hormuz_portwatch_single_day_threshold"
        return "hormuz_portwatch_count"
    return ""


def _derive_risk_flags(
    *, oracle_kind: str, is_band: bool, text: str, name: str, days_to_resolve: int | None
) -> list[str]:
    low = f"{text} {name}".lower()
    flags: list[str] = []
    if oracle_kind == "pure_data":
        flags.append("pure data oracle")
    if is_band:
        flags.append("bucketed (negative-risk) market — exactly one band resolves YES")
        flags.append("band threshold/source not independently re-verified against rules page")
    if "trump" in low and any(w in low for w in ("announce", "post", "statement")):
        flags.append("Trump social post can qualify")
    if "weather" in low:
        flags.append("weather-only closures excluded")
    if oracle_kind == "official_statement_required":
        flags.append("media fallback may matter")
        flags.append("announcement-driven")
    if days_to_resolve is not None and 0 <= days_to_resolve <= 10:
        flags.append("deadline gamma (near-term)")
    return flags


def _rule_risk_block(kind: str) -> dict:
    if kind == "pure_data":
        return {
            "oracle_type": "pure_data",
            "ambiguity": "low",
            "media_fallback": False,
            "official_statement_required": False,
            "dispute_risk": "low",
        }
    return {
        "oracle_type": "official_statement_required",
        "ambiguity": "medium",
        "media_fallback": True,
        "official_statement_required": True,
        "dispute_risk": "medium",
    }


def _collapse(text: str, limit: int = 1500) -> str:
    """Trim and length-cap the resolution description for use as ``notes``."""
    collapsed = re.sub(r"[ \t]+", " ", (text or "").strip())
    collapsed = re.sub(r"\n{3,}", "\n\n", collapsed)
    if len(collapsed) > limit:
        collapsed = collapsed[: limit - 1].rstrip() + "…"
    return collapsed


def _days_until(resolution_date: object) -> int | None:
    if isinstance(resolution_date, str) and resolution_date:
        try:
            d = date.fromisoformat(resolution_date.split("T")[0])
        except ValueError:
            return None
    elif isinstance(resolution_date, date):
        d = resolution_date
    else:
        return None
    return (d - date.today()).days


def suggest_for_market(candidate: dict, market: dict, registry: MarketRegistry) -> dict:
    """Suggest every judgment field for one normalized market.

    Returns a dict with the suggested values, a ``sources`` map keyed by field
    (``inherited`` / ``rules`` / ``default``), and ``matched_market_id`` naming
    the entry we inherited from (or ``None``). Nothing is written.
    """
    display = market_display_name(candidate, market) or (market.get("question") or "")
    description = market.get("description") or ""
    resolution_source = candidate.get("resolution_source") or ""
    is_band = _is_band_market(market)
    days = _days_until(market.get("resolution_date"))

    sources: dict[str, str] = {}
    out: dict[str, object] = {"market_id": _suggest_market_id(candidate, market)}
    sources["market_id"] = "default"

    neighbour, score = find_nearest(candidate, market, registry)
    inherit = neighbour is not None and score >= INHERIT_THRESHOLD

    if inherit and neighbour is not None:
        out["category"] = neighbour.category
        out["thesis_bucket"] = neighbour.thesis_bucket
        out["rule_key"] = neighbour.rule_key
        out["oracle_type"] = neighbour.oracle_type
        out["risk_flags"] = list(neighbour.risk_flags)
        out["rule_risk"] = neighbour.rule_risk.model_dump() if neighbour.rule_risk else None
        inherited_fields = (
            "category", "thesis_bucket", "rule_key", "oracle_type", "risk_flags", "rule_risk"
        )
        for f in inherited_fields:
            sources[f] = "inherited"
        # A sibling band's YES side is specific to *its* band, not this one —
        # never inherit it. Otherwise inherit the family's standing side.
        if is_band:
            out["preferred_side"] = "NO"
            sources["preferred_side"] = "default"
        else:
            out["preferred_side"] = neighbour.preferred_side
            sources["preferred_side"] = "inherited"
    else:
        oracle_type, oracle_kind = _derive_oracle(f"{description} {resolution_source}")
        out["oracle_type"] = oracle_type
        out["rule_key"] = _derive_rule_key(oracle_kind, is_band, description)
        out["risk_flags"] = _derive_risk_flags(
            oracle_kind=oracle_kind,
            is_band=is_band,
            text=description,
            name=display,
            days_to_resolve=days,
        )
        out["rule_risk"] = _rule_risk_block(oracle_kind)
        out["category"] = _suggest_category(candidate)
        out["thesis_bucket"] = _suggest_thesis_bucket(candidate)
        out["preferred_side"] = "NO"
        sources["oracle_type"] = "rules"
        sources["rule_key"] = "rules" if out["rule_key"] else "default"
        sources["risk_flags"] = "rules" if out["risk_flags"] else "default"
        sources["rule_risk"] = "rules"
        sources["category"] = "rules" if out["category"] else "default"
        sources["thesis_bucket"] = "rules" if out["thesis_bucket"] else "default"
        sources["preferred_side"] = "default"

    out["notes"] = _collapse(description)
    sources["notes"] = "rules" if description else "default"

    out["sources"] = sources
    out["matched_market_id"] = neighbour.market_id if inherit and neighbour else None
    out["match_score"] = round(score, 3)
    return out


# Tag → category guesses for the rules fallback (no neighbour to inherit from).
_TAG_CATEGORY = {
    "hormuz": "core_hormuz",
    "strait of hormuz": "core_hormuz",
    "iran": "iran_us_diplomacy",
}


def _suggest_category(candidate: dict) -> str:
    tags = [t.lower() for t in (candidate.get("tags") or [])]
    for tag in tags:
        if tag in _TAG_CATEGORY:
            return _TAG_CATEGORY[tag]
    # Fall back to a slugified most-specific tag, else empty for the human.
    for tag in candidate.get("tags") or []:
        cleaned = suggest_market_id(tag)
        if cleaned and cleaned != "new_market":
            return cleaned
    return ""


def _suggest_thesis_bucket(candidate: dict) -> str:
    tags = [t.lower() for t in (candidate.get("tags") or [])]
    if "iran" in tags or "hormuz" in tags or "strait of hormuz" in tags:
        return "Iran conflict"
    return ""
