"""General keyword web search via Google's Custom Search JSON API -
a different problem from reverse_image (given a photo, find similar
images) or ocr (read text in a photo): given a text query, search
Google's whole index, the way a human would type "Fujifilm X100VI" into
google.com and skim results. Deliberately does NOT scrape
google.com/search directly - that's explicitly out of scope for this
project (against ToS, fragile, real risk - same reasoning as the
Google Lens decision in reverse_image/base.py). This is the sanctioned,
official alternative: a real Google Cloud API, not scraping.

Setup: enable the "Custom Search API" in a Google Cloud project, get an
API key, and create a Programmable Search Engine at
https://programmablesearchengine.google.com/ configured to search the
entire web (not just specific sites) - that gives you the "cx" engine
ID. Both go in .env as GOOGLE_CUSTOM_SEARCH_API_KEY and
GOOGLE_CUSTOM_SEARCH_ENGINE_ID. Free for 100 queries/day, ~$5/1000
after - at a few queries per scheduled run, this stays in the free tier
for any reasonable run frequency.

A plain web search returns a lot of noise a marketplace-specific adapter
never has to deal with: official retailer pages, manufacturer product
pages, review articles, forum threads. Filtering that down to "actual
resale listings" uses two layers, same conservative philosophy as the
rest of this project's filters (matching/color.py, matching/accessory.py) -
only exclude on a confident signal, never on missing information:

1. Query-level: `-site:` operators for a best-effort list of known
   retailer/manufacturer domains (`_EXCLUDED_DOMAINS`), so Google itself
   never returns most of the noise in the first place.
2. Result-level: reruns matching/accessory.py's and matching/color.py's
   filters against each result's title+snippet (the same checks already
   applied to marketplace listings), plus a second domain check in case
   a retailer isn't in the query-level list yet.

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

# Best-effort, not exhaustive - a handful of the retailers/manufacturers
# most likely to show up for camera gear searches. Extend as noise shows
# up in practice, the same way matching/accessory.py's keyword lists grew.
_EXCLUDED_DOMAINS = [
    "amazon.com",
    "amazon.de",
    "amazon.co.uk",
    "fujifilm.com",
    "fujifilm-x.com",
    "bhphotovideo.com",
    "adorama.com",
    "mediamarkt.de",
    "mediamarkt.at",
    "saturn.de",
    "currys.co.uk",
    "jpc.de",
    "cyberport.de",
    "conrad.de",
    "conrad.at",
    "calumetphoto.com",
    "wexphotovideo.com",
    "parkcameras.com",
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

        exclusions = " ".join(f"-site:{domain}" for domain in _EXCLUDED_DOMAINS)
        resp = self._get(
            _API_URL,
            params={
                "key": self._api_key,
                "cx": self._engine_id,
                "q": f'"{query}" {exclusions}',
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


def is_excluded_domain(url_or_domain: str) -> bool:
    lowered = url_or_domain.lower()
    return any(domain in lowered for domain in _EXCLUDED_DOMAINS)
