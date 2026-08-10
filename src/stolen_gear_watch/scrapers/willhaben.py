"""Adapter for willhaben.at (Austria).

STATUS: confirmed disallowed, not just unverified. willhaben.at is
reachable fine over plain HTTP - there's no bot-detection blocking a
normal request. But its robots.txt (checked directly, not guessed at)
opens with "It is expressively forbidden to use spiders, search robots
or other automatic methods to access willhaben.at," and its `Disallow`
rules - which are almost all `*`-wildcard query-string patterns, e.g.
`Disallow: /*?*keyword=*` - do cover the search endpoint this adapter
needs. (Note: this only shows up correctly with a wildcard-aware robots
parser; stdlib `urllib.robotparser` does plain prefix matching and
silently ignores every wildcard rule, which made this site look allowed
during earlier testing - see `net.py`'s docstring.)

`Adapter._get()` enforces this automatically: every call this adapter
makes will raise `RobotsDisallowedError` before any request selectors
even matter. This class is kept as documentation of that fact and in
case willhaben.at ever relaxes the policy, but it will not return
results today. Treat Willhaben as a manual-check site.
"""

from __future__ import annotations

import logging
from collections.abc import Iterator

from bs4 import BeautifulSoup, Tag

from stolen_gear_watch.core.models import RawListing, WatchedItem
from stolen_gear_watch.scrapers.base import Adapter
from stolen_gear_watch.scrapers.registry import register_adapter
from stolen_gear_watch.scrapers.utils import looks_like_bot_challenge

logger = logging.getLogger(__name__)


@register_adapter
class WillhabenAdapter(Adapter):
    site_key = "willhaben"
    base_url = "https://www.willhaben.at"

    def search(self, item: WatchedItem) -> Iterator[RawListing]:
        query = " ".join(filter(None, [item.make, item.model]))
        for page in range(1, self.settings.max_pages + 1):
            resp = self._get(
                f"{self.base_url}/iad/kaufen-und-verkaufen/marktplatz",
                params={"keyword": query, "page": page},
            )
            if looks_like_bot_challenge(resp.text):
                logger.warning(
                    "willhaben: response for query %r looks like a bot-challenge "
                    "page, not real search results. This adapter is likely "
                    "blocked - see module docstring. Treating as a manual-check "
                    "site until a verified approach exists.",
                    query,
                )
                return

            soup = BeautifulSoup(resp.text, "html.parser")
            cards = soup.select("a[href*='/iad/kaufen-und-verkaufen/d/']")
            if not cards:
                logger.info(
                    "willhaben: no listing links found on page %d for query %r "
                    "- selectors may be stale, see module docstring",
                    page,
                    query,
                )
                return

            for card in cards:
                listing = self._parse_card(card)
                if listing is not None:
                    yield listing

    def _parse_card(self, card: Tag) -> RawListing | None:
        href = card.get("href", "")
        if not href:
            return None
        source_id = href.rstrip("/").rsplit("-", 1)[-1]
        url = href if href.startswith("http") else f"{self.base_url}{href}"

        title = card.get_text(strip=True)
        if not title:
            return None

        photo_urls = []
        img = card.find("img")
        if img and (src := img.get("src")):
            photo_urls.append(src)

        return RawListing(
            source_site=self.site_key,
            source_id=source_id,
            url=url,
            title=title,
            photo_urls=photo_urls,
        )
