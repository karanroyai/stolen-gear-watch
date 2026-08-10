"""Fuzzy make/model matching for when a listing doesn't expose (or the
scraper couldn't extract) a serial number - the common case, since most
sellers don't photograph the serial plate.
"""

from __future__ import annotations

from rapidfuzz import fuzz

from stolen_gear_watch.core.models import WatchedItem


def text_match_confidence(title: str, description: str, item: WatchedItem) -> float:
    """Fuzzy-match a listing's title+description against the watched item's
    make/model/aliases. Returns 0.0-1.0; callers should treat this as
    weaker evidence than a serial match and apply a confidence threshold
    before alerting - fuzzy text matches on make/model alone are only
    useful as a hint to run reverse image search, not a standalone alert."""
    haystack = f"{title}\n{description}"
    candidates = [f"{item.make} {item.model}", *item.aliases]

    best = max(
        fuzz.token_set_ratio(haystack, candidate) for candidate in candidates
    )
    score = best / 100.0

    if item.keywords:
        keyword_hits = sum(1 for kw in item.keywords if kw.lower() in haystack.lower())
        keyword_boost = 0.05 * min(keyword_hits, 3)
        score = min(1.0, score + keyword_boost)

    return score
