"""Adapter for kupujemprodajem.com (Serbia).

VERIFY BEFORE RELYING ON THIS: the selectors below are based on the
observed public page structure at the time this was written (listing
cards are `<a>` elements linking to `/.../oglas/{id}`, with price text and
a thumbnail `<img>` inside). Classifieds sites change markup without
notice - if this adapter starts returning zero results, inspect a live
search results page and update `_parse_card` accordingly before assuming
there's nothing for sale.
"""

from __future__ import annotations

import logging
import re
from collections.abc import Iterator

from bs4 import BeautifulSoup, Tag

from stolen_gear_watch.core.models import RawListing, WatchedItem
from stolen_gear_watch.scrapers.base import Adapter
from stolen_gear_watch.scrapers.registry import register_adapter

logger = logging.getLogger(__name__)

_LISTING_HREF_RE = re.compile(r"/oglas/(?P<id>\d+)")
_PRICE_RE = re.compile(r"([\d.,]+)\s*(EUR|€|RSD|din)", re.IGNORECASE)


@register_adapter
class KupujemProdajemAdapter(Adapter):
    site_key = "kupujemprodajem"
    base_url = "https://www.kupujemprodajem.com"

    def search(self, item: WatchedItem) -> Iterator[RawListing]:
        query = " ".join(filter(None, [item.make, item.model]))
        for page in range(1, self.settings.max_pages + 1):
            resp = self._get(
                f"{self.base_url}/pretraga",
                params={"keywords": query, "page": page},
            )
            soup = BeautifulSoup(resp.text, "html.parser")
            cards = [
                a for a in soup.find_all("a", href=_LISTING_HREF_RE) if isinstance(a, Tag)
            ]
            if not cards:
                logger.info(
                    "kupujemprodajem: no listing cards found on page %d for query %r "
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
        match = _LISTING_HREF_RE.search(href)
        if not match:
            return None
        source_id = match.group("id")
        url = href if href.startswith("http") else f"{self.base_url}{href}"

        title = card.get_text(strip=True) or (card.img.get("alt") if card.img else "")
        if not title:
            return None

        price = None
        currency = None
        price_match = _PRICE_RE.search(card.get_text(" ", strip=True))
        if price_match:
            price = float(price_match.group(1).replace(".", "").replace(",", "."))
            currency = "EUR" if "€" in price_match.group(2).upper() or "EUR" in price_match.group(2).upper() else "RSD"

        photo_urls = []
        if card.img and card.img.get("src"):
            photo_urls.append(card.img["src"])

        return RawListing(
            source_site=self.site_key,
            source_id=source_id,
            url=url,
            title=title,
            price=price,
            currency=currency,
            photo_urls=photo_urls,
        )
