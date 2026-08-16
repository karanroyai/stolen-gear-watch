"""Adapter for Pazar3.mk (North Macedonia).

See `_regional_classifieds_platform.py`'s module docstring for how the
search endpoint was found and how card markup is parsed - this file just
supplies the North Macedonia-specific bits.

robots.txt is permissive (`Allow: /`, only `/mk/Administration/`,
`/al/Administration/`, `/en/Administration/` disallowed - none of which
overlap `/mk/Home2/Search`). Confirmed live: searching "Fujifilm X100VI"
surfaces genuine matching listings (e.g. an actual "Fujifilm X100VI
Digital Compact Camera... Silver" ad), not just noise.

Month abbreviations below are all confirmed directly against live
listing dates except january (јан.) - every other month (фев., мар.,
апр., мај, јун., јул., авг., септ., окт., ноем., дек.) was seen in
actual search results across two sample queries; january just didn't
happen to appear in either sample. "денес" (today) is the standard
Macedonian word matching the confirmed "вчера" (yesterday) pattern, but
only "вчера" itself was directly observed live.
"""

from __future__ import annotations

from stolen_gear_watch.scrapers._regional_classifieds_platform import (
    RegionalClassifiedsAdapter,
)
from stolen_gear_watch.scrapers.registry import register_adapter

_MONTH_ABBREVS_MK = {
    "јан": 1,
    "фев": 2,
    "мар": 3,
    "апр": 4,
    "мај": 5,
    "јун": 6,
    "јул": 7,
    "авг": 8,
    "септ": 9,
    "окт": 10,
    "ноем": 11,
    "дек": 12,
}


@register_adapter
class Pazar3MkAdapter(RegionalClassifiedsAdapter):
    site_key = "pazar3_mk"
    base_url = "https://www.pazar3.mk"
    search_path = "/mk/Home2/Search"
    _month_abbrevs = _MONTH_ABBREVS_MK
    _today_word = "денес"
    _yesterday_word = "вчера"
