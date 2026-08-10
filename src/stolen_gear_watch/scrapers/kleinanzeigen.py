"""Adapter for kleinanzeigen.de (Germany, formerly eBay Kleinanzeigen).

VERIFY BEFORE RELYING ON THIS: selectors target the long-standing
`article.aditem` listing-card markup this site has used for years, but a
live check while building this project got network timeouts rather than
a clean response, so the current markup could not be confirmed directly.
Inspect a live search results page and update `_parse_card` if this
starts returning zero results.
"""

from __future__ import annotations

import logging
from collections.abc import Iterator

from bs4 import BeautifulSoup, Tag

from stolen_gear_watch.core.models import RawListing, WatchedItem
from stolen_gear_watch.scrapers.base import Adapter
from stolen_gear_watch.scrapers.registry import register_adapter

logger = logging.getLogger(__name__)


@register_adapter
class KleinanzeigenAdapter(Adapter):
    site_key = "kleinanzeigen"
    base_url = "https://www.kleinanzeigen.de"

    def search(self, item: WatchedItem) -> Iterator[RawListing]:
        query = "-".join(filter(None, [item.make, item.model])).replace(" ", "-")
        for page in range(1, self.settings.max_pages + 1):
            path = f"/s-seite:{page}/{query}/k0" if page > 1 else f"/s-{query}/k0"
            resp = self._get(f"{self.base_url}{path}")
            soup = BeautifulSoup(resp.text, "html.parser")
            cards = soup.find_all("article", class_="aditem")
            if not cards:
                logger.info(
                    "kleinanzeigen: no aditem cards found on page %d for query %r "
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
        source_id = card.get("data-adid")
        href = card.get("data-href") or (card.find("a") or {}).get("href")
        if not source_id or not href:
            return None
        url = href if href.startswith("http") else f"{self.base_url}{href}"

        title_el = card.select_one(".aditem-main--top--title")
        title = title_el.get_text(strip=True) if title_el else None
        if not title:
            return None

        price_el = card.select_one(".aditem-main--middle--price-shipping--price")
        price = currency = None
        if price_el:
            price_text = price_el.get_text(strip=True)
            digits = "".join(c for c in price_text if c.isdigit())
            if digits:
                price = float(digits)
                currency = "EUR"

        location_el = card.select_one(".aditem-main--top--left")
        location = location_el.get_text(strip=True) if location_el else None

        photo_urls = []
        img = card.find("img")
        if img and (src := img.get("src") or img.get("data-src")):
            photo_urls.append(src)

        return RawListing(
            source_site=self.site_key,
            source_id=source_id,
            url=url,
            title=title,
            price=price,
            currency=currency,
            location=location,
            photo_urls=photo_urls,
        )
