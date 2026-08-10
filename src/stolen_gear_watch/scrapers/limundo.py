"""Adapter for limundo.com (Serbia).

STATUS: experimental / needs manual verification. A direct check of this
site's search page while building this project returned HTTP 403 for a
single plain GET request, which suggests some form of bot-detection is in
front of it too. The selectors below are a best-effort guess at a
conventional classifieds listing-card structure and have not been
confirmed against live markup.

Verify this adapter actually returns results before relying on it. If it
keeps 403ing, treat Limundo as a manual-check site rather than working
around the block - see README "Scraping ethics".
"""

from __future__ import annotations

import logging
import re
from collections.abc import Iterator

from bs4 import BeautifulSoup, Tag

from stolen_gear_watch.core.models import RawListing, WatchedItem
from stolen_gear_watch.scrapers.base import Adapter
from stolen_gear_watch.scrapers.registry import register_adapter
from stolen_gear_watch.scrapers.utils import looks_like_bot_challenge

logger = logging.getLogger(__name__)

_PRICE_RE = re.compile(r"([\d.,]+)\s*(EUR|€|RSD|din)", re.IGNORECASE)


@register_adapter
class LimundoAdapter(Adapter):
    site_key = "limundo"
    base_url = "https://www.limundo.com"

    def search(self, item: WatchedItem) -> Iterator[RawListing]:
        query = " ".join(filter(None, [item.make, item.model]))
        for page in range(1, self.settings.max_pages + 1):
            resp = self._get(
                f"{self.base_url}/Pretraga",
                params={"Keywords": query, "Page": page},
            )
            if looks_like_bot_challenge(resp.text):
                logger.warning(
                    "limundo: response for query %r looks like a bot-challenge "
                    "page, not real search results - see module docstring.",
                    query,
                )
                return

            soup = BeautifulSoup(resp.text, "html.parser")
            cards = soup.select("a[href*='/Artikal/']") or soup.select(
                "a[href*='/artikal/']"
            )
            if not cards:
                logger.info(
                    "limundo: no listing links found on page %d for query %r "
                    "- selectors are unverified, see module docstring",
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
        source_id = href.rstrip("/").rsplit("/", 1)[-1]
        url = href if href.startswith("http") else f"{self.base_url}{href}"

        title = card.get_text(strip=True)
        if not title:
            return None

        price = currency = None
        price_match = _PRICE_RE.search(card.get_text(" ", strip=True))
        if price_match:
            price = float(price_match.group(1).replace(".", "").replace(",", "."))
            currency = "EUR" if "€" in price_match.group(2) or "EUR" in price_match.group(2).upper() else "RSD"

        photo_urls = []
        img = card.find("img")
        if img and (src := img.get("src")):
            photo_urls.append(src)

        return RawListing(
            source_site=self.site_key,
            source_id=source_id,
            url=url,
            title=title,
            price=price,
            currency=currency,
            photo_urls=photo_urls,
        )
