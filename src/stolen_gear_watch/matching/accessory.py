"""Filters out listings that clearly aren't the item itself for sale -
accessories/parts for it, a book/manual about it, a rental offer, or a
want-ad/trade-request for one. All three are common noise in fuzzy
make/model text matching: "SmallRigg Half Case für Fujifilm X100VI"
matches "Fujifilm X100VI" just as well as an actual camera listing does.

Same conservative philosophy as matching/color.py and the stolen_at/color
pre-filters in pipeline.py: only filters on a fairly confident signal,
and always errs toward keeping an ambiguous listing - a false negative
(hiding the real listing) is worse than a little extra noise.

Three signal types, checked in order:

1. Unconditional keywords (book/manual, rental) - these essentially never
   appear in a genuine "I'm selling this exact item" title regardless of
   where they appear, so position doesn't matter.
2. Leading want-ad words ("Suche...", "Tausche...") - only checked at the
   start of the title, since these words could plausibly appear later in
   a real listing without being its actual subject.
3. Accessory keywords mentioned *before* the item's own make/model in the
   title - "Case für Fujifilm X100VI" (accessory-first) is almost always
   an accessory listing; "Fujifilm X100VI + UV Filter" (item-first,
   accessory mentioned as a bundled extra) is almost always the real
   item. Position relative to the make/model is a much better signal
   than keyword presence alone.
"""

from __future__ import annotations

import re

from stolen_gear_watch.core.models import WatchedItem

_UNCONDITIONAL_NOISE_KEYWORDS = [
    "handbuch",
    "anleitung",
    "mieten",
    "miete",
    "vermiete",
    "verleih",
]

_LEADING_NOISE_KEYWORDS = {"suche", "gesucht", "tausche", "kaufe"}

_ACCESSORY_KEYWORDS = [
    "tasche",
    "hülle",
    "huelle",
    "case",
    "filter",
    "gegenlichtblende",
    "objektivdeckel",
    "deckel",
    "akku",
    "battery",
    "ladegerät",
    "ladegeraet",
    "charger",
    "gurt",
    "strap",
    "cage",
    "adapter",
    "schutzfolie",
]


def _word_position(text: str, word: str) -> int | None:
    match = re.search(rf"\b{re.escape(word)}\b", text)
    return match.start() if match else None


def is_likely_non_item_listing(title: str, item: WatchedItem) -> str | None:
    """None if the listing looks like the item itself; otherwise a short
    human-readable reason it was skipped."""
    lowered = title.lower()

    for keyword in _UNCONDITIONAL_NOISE_KEYWORDS:
        if _word_position(lowered, keyword) is not None:
            return f"title contains {keyword!r} - looks like a book/manual or rental, not the item"

    words = lowered.split()
    if words and words[0].strip(":,-") in _LEADING_NOISE_KEYWORDS:
        return f"title starts with {words[0]!r} - looks like a want-ad, not something for sale"

    item_positions = [
        pos
        for term in (item.make, item.model)
        if term and (pos := _word_position(lowered, term.lower())) is not None
    ]
    item_pos = min(item_positions) if item_positions else None

    for keyword in _ACCESSORY_KEYWORDS:
        keyword_pos = _word_position(lowered, keyword)
        if keyword_pos is not None and (item_pos is None or keyword_pos < item_pos):
            return f"title mentions {keyword!r} before the item's own make/model - looks like an accessory"

    return None
