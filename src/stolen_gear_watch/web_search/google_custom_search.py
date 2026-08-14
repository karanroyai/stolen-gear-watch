"""General keyword web search via Google's Custom Search JSON API -
a different problem from reverse_image (given a photo, find similar
images) or ocr (read text in a photo): given a text query, search
across a set of marketplace sites, the way a human would type
"Fujifilm X100VI" into google.com and skim results. Deliberately does
NOT scrape google.com/search directly - that's explicitly out of scope
for this project (against ToS, fragile, real risk - same reasoning as
the Google Lens decision in reverse_image/base.py). This is the
sanctioned, official alternative: a real Google Cloud API, not scraping.

IMPORTANT - this is NOT whole-web search: Google discontinued the
"search the entire web" option for newly-created Programmable Search
Engines as of January 20, 2026 (confirmed directly - see this project's
own investigation, not assumed). New engines are capped at a maximum of
50 specific domains via "Sites to search"; engines that already had
whole-web search enabled before that date keep it until January 1, 2027,
but that doesn't help a new setup. So this module searches a *curated
domain list*, not the internet at large.

That constraint has a real upside, not just a downside: the curated list
can (and does, see `_RECOMMENDED_DOMAINS` below, meant to be pasted into
the Programmable Search Engine's "Sites to search" config, not used by
the code itself) include OLX, Njuskalo, and Bolha - three sites this
project explicitly declined to build direct scrapers for because they
run active bot-detection (Cloudflare managed challenge / ShieldSquare
+hCaptcha, both confirmed live - see scrapers/ and README "Marketplace
scraping"). Google's own crawler isn't blocked by those walls, so
searching Google's index of those sites' public listing pages is
meaningfully different from scraping them directly: it's not evasion,
it's asking an official API for results Google already legitimately
crawled.

Setup: enable the "Custom Search API" in a Google Cloud project for the
key, and create a Programmable Search Engine at
https://programmablesearchengine.google.com/ with `_RECOMMENDED_DOMAINS`
(or your own list, up to 50) as its "Sites to search" for the engine ID
("cx"). Both go in .env as GOOGLE_CUSTOM_SEARCH_API_KEY and
GOOGLE_CUSTOM_SEARCH_ENGINE_ID. Free for 100 queries/day.

Because the search scope is now controlled entirely by the Programmable
Search Engine's own domain allowlist (configured on Google's side, not
in this code), there's no query-time `-site:` exclusion logic here
anymore - a curated marketplace-only domain list doesn't have the
"official retailer/manufacturer noise" problem a genuine whole-web
search would have had. What's still relevant and still applied: the
same accessory/color filters already used for marketplace listings
(matching/accessory.py, matching/color.py), since even a classifieds
site mixes new-in-box and used listings.

There's no reliable per-result post date in Custom Search's response, so
results here aren't checked against a watched item's stolen_at the way
marketplace listings are - a known gap, not silently worked around.
"""

from __future__ import annotations

import logging
from collections.abc import Iterator

from pydantic import BaseModel

from stolen_gear_watch.core.config import require_env
from stolen_gear_watch.net import PoliteHttpClient

logger = logging.getLogger(__name__)

_API_URL = "https://www.googleapis.com/customsearch/v1"

# Paste into the Programmable Search Engine's "Sites to search" - not read
# by this module at runtime, the scope restriction happens entirely on
# Google's side once the engine is configured with it. 38 domains, under
# the 50-domain cap with room to add more later.
_RECOMMENDED_DOMAINS = [
    # Already have a dedicated adapter - included here too for backup
    # coverage (catches things a stale selector or pagination limit missed).
    "willhaben.at",
    "kleinanzeigen.de",
    "kupujemprodajem.com",
    "publi24.ro",
    "bazar.bg",
    # Bot-blocked for direct scraping (Cloudflare / ShieldSquare+hCaptcha,
    # confirmed live) - this is the main reason this feature is worth
    # having: indirect coverage via Google's index, not evasion.
    "olx.pl",
    "olx.ro",
    "olx.bg",
    "olx.ua",
    "olx.ba",
    "olx.pt",
    "njuskalo.hr",
    "bolha.com",
    # Serbia, experimental/unverified direct adapter (see scrapers/limundo.py).
    "limundo.com",
    # Other major European classifieds with no adapter at all.
    "marktplaats.nl",
    "2dehands.be",
    "2ememain.be",
    "leboncoin.fr",
    "subito.it",
    "milanuncios.es",
    "tori.fi",
    "blocket.se",
    "dba.dk",
    "finn.no",
    "sbazar.cz",
    "bazos.cz",
    "bazos.sk",
    "jofogas.hu",
    "merrjep.al",
    "pazar3.mk",
    "gumtree.com",
    "preloved.co.uk",
    "vinted.com",
    "shpock.com",
    "quoka.de",
    "kalaydo.de",
    "markt.de",
    "meinestadt.de",
]


class WebSearchResult(BaseModel):
    title: str
    url: str
    snippet: str = ""
    display_link: str = ""


class GoogleCustomSearch(PoliteHttpClient):
    base_url = "https://www.googleapis.com"

    def __init__(self, rate_limit_seconds: float = 2.0) -> None:
        super().__init__(rate_limit_seconds=rate_limit_seconds, respect_robots_txt=True)
        # Credentials are read lazily on first search(), not here -
        # get_web_search() constructs this at the top of pipeline.run(),
        # outside any per-item try/except, so raising in __init__ over a
        # missing .env value would crash the entire scheduled run instead
        # of just this feature. See scrapers/ebay.py for the same lesson.
        self._api_key: str | None = None
        self._engine_id: str | None = None

    def search(self, query: str, num_results: int = 10) -> Iterator[WebSearchResult]:
        if self._api_key is None or self._engine_id is None:
            self._api_key = require_env("GOOGLE_CUSTOM_SEARCH_API_KEY")
            self._engine_id = require_env("GOOGLE_CUSTOM_SEARCH_ENGINE_ID")

        resp = self._get(
            _API_URL,
            params={
                "key": self._api_key,
                "cx": self._engine_id,
                "q": f'"{query}"',
                "num": min(num_results, 10),
            },
        )
        data = resp.json()
        for item in data.get("items", []):
            url = item.get("link")
            title = item.get("title")
            if not url or not title:
                continue
            yield WebSearchResult(
                title=title,
                url=url,
                snippet=item.get("snippet", ""),
                display_link=item.get("displayLink", ""),
            )
