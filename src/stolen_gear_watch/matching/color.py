"""Filters out listings whose text explicitly names a color that
conflicts with the watched item's - e.g. don't match a listing that says
"schwarz" (black) when the stolen item is silver.

Deliberately conservative: this only ever filters on a confident
*negative* signal (the text explicitly names a different color and
doesn't also mention the item's own color), never on the absence of
color information. Most listings don't spell out a color at all, and
"no color mentioned" is not evidence of the wrong color - filtering on
that would silently drop real matches.
"""

from __future__ import annotations

import re

# Synonyms per canonical color, covering the languages of currently-shipped
# adapters (German for AT/DE, Serbian for RS). Necessarily incomplete -
# camera colorways vary a lot; extend as needed.
_COLOR_SYNONYMS: dict[str, list[str]] = {
    "black": ["black", "schwarz", "crna", "crno", "crni"],
    "silver": ["silver", "silber", "srebrna", "srebrno", "srebrni"],
    "white": ["white", "weiss", "weiß", "bela", "belo", "beli"],
    "graphite": ["graphite", "graphit"],
    "champagne": ["champagne", "champagner"],
}

_WORD_TO_CANONICAL = {
    synonym: canonical
    for canonical, synonyms in _COLOR_SYNONYMS.items()
    for synonym in synonyms
}

_WORD_RE = re.compile(r"[a-zA-ZäöüÄÖÜß]+")


def mentions_conflicting_color(text: str, item_color: str) -> bool:
    """True if `text` explicitly names a color that conflicts with
    `item_color`. False if the item's color is unrecognized, if `text`
    doesn't mention any recognized color at all, or if it mentions the
    item's own color (some listings legitimately offer multiple colors)."""
    item_canonical = _WORD_TO_CANONICAL.get(item_color.lower())
    if item_canonical is None:
        return False

    mentioned = {
        canonical
        for word in _WORD_RE.findall(text.lower())
        if (canonical := _WORD_TO_CANONICAL.get(word)) is not None
    }
    if item_canonical in mentioned:
        return False
    return bool(mentioned)
