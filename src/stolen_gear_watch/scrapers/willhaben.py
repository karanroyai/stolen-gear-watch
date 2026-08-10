"""Adapter for willhaben.at (Austria).

STATUS: experimental / needs manual verification. While building this
project, automated fetches to willhaben.at were blocked outright (not
just slow - refused) even for a single robots.txt request, which is a
strong signal they run active bot-detection in front of the site. A
plain `requests`-based adapter may simply not work here regardless of
how correct the selectors are.

Rather than guess at evasion techniques (which this project deliberately
won't build - see README "Scraping ethics"), this adapter does its best
with a normal HTTP GET and explicitly detects and logs when it looks like
it hit a bot-challenge page, so failures are visible instead of silently
returning zero results. If this keeps failing for you, treat Willhaben as
a manual-check site: search it yourself periodically, or contribute a
verified adapter if you find a working approach that doesn't cross into
active evasion.
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
