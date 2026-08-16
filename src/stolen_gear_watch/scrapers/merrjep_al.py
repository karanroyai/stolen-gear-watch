"""Adapter for Merrjep.al (Albania).

Same underlying platform as Pazar3.mk - see
`_regional_classifieds_platform.py`'s module docstring. The one real
difference confirmed live: this site's search endpoint has no locale
prefix (`/Home2/Search`, not `/mk/Home2/Search` - the `/mk/` paths on
this domain are North Macedonia-language content *within* Merrjep, a
separate thing from Pazar3.mk, and using that prefix here 404s).

robots.txt is permissive (`Allow: /`, only `/Administration/`
disallowed). Confirmed live: searching "Fujifilm X100VI" surfaces
genuine matches (e.g. "Kamera Fujifilm X100VI", 600 EUR, Tiranë).

Month abbreviations are mostly *not* directly verified - only "gush"
(August) and the today/yesterday words ("Sot"/"Dje") were actually seen
in live results across two sample queries; the other eleven are
standard Albanian abbreviations, included on the same reasoning as
eBay's undocumented-field guesses (better than never parsing a date,
but treat with more suspicion than the Macedonian adapter's map, which
is almost fully observed). An unrecognized abbreviation just yields no
date rather than a wrong one - see the base class's `_parse_posted_at`.
"""

from __future__ import annotations

from stolen_gear_watch.scrapers._regional_classifieds_platform import (
    RegionalClassifiedsAdapter,
)
from stolen_gear_watch.scrapers.registry import register_adapter

_MONTH_ABBREVS_AL = {
    "jan": 1,
    "shk": 2,
    "mar": 3,
    "pri": 4,
    "maj": 5,
    "qer": 6,
    "korr": 7,
    "gush": 8,
    "sht": 9,
    "tet": 10,
    "nën": 11,
    "dhj": 12,
}


@register_adapter
class MerrjepAlAdapter(RegionalClassifiedsAdapter):
    site_key = "merrjep_al"
    base_url = "https://www.merrjep.al"
    search_path = "/Home2/Search"
    _month_abbrevs = _MONTH_ABBREVS_AL
    _today_word = "Sot"
    _yesterday_word = "Dje"
