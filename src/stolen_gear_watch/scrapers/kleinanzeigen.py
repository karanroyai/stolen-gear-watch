"""Adapter for kleinanzeigen.de (Germany, formerly eBay Kleinanzeigen).

Verified directly against a live search results page (not guessed at -
an earlier version of this adapter was written after a network timeout
prevented checking, and its title selector had in fact gone stale: the
site's been redesigned since, and `.aditem-main--top--title` no longer
exists anywhere in the markup - titles are now a plain `<h2><a>` with no
title-specific class).

Rather than just point at the new plain heading, each card also embeds a
`<script type="application/ld+json">` block with structured `title`,
`description`, and `contentUrl` (image) fields - use that as the primary
source since structured data is far less likely to break on the next
redesign than nested div/class scraping, with the heading text as a
fallback for cards that lack it. The outer `article.aditem` wrapper,
`data-adid`/`data-href` attributes, and the price/location selectors are
all still exactly as they were and don't need this treatment.
"""

from __future__ import annotations

import json
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

        title, description, image_url = self._parse_ld_json(card)
        if not title:
            heading = card.select_one("h2 a")
            title = heading.get_text(strip=True) if heading else None
        if not title:
            return None

        price_el = card.select_one(".aditem-main--middle--price-shipping--price")
        price = currency = None
        if price_el:
            # Discounted listings nest a struck-through "old price" <p> inside
            # this element - get_text() would concatenate both into one
            # digit string (e.g. "1.699 €" + "1.899 €" -> "16991899"). Take
            # only the first text node, which is the current price.
            price_text = next(price_el.stripped_strings, "")
            digits = "".join(c for c in price_text if c.isdigit())
            if digits:
                price = float(digits)
                currency = "EUR"

        location_el = card.select_one(".aditem-main--top--left")
        location = location_el.get_text(strip=True) if location_el else None

        photo_urls = []
        if image_url:
            photo_urls.append(image_url)
        else:
            img = card.find("img")
            if img and (src := img.get("src") or img.get("data-src")):
                photo_urls.append(src)

        return RawListing(
            source_site=self.site_key,
            source_id=source_id,
            url=url,
            title=title,
            description=description or "",
            price=price,
            currency=currency,
            location=location,
            photo_urls=photo_urls,
        )

    def _parse_ld_json(self, card: Tag) -> tuple[str | None, str | None, str | None]:
        script = card.find("script", type="application/ld+json")
        if not script or not script.string:
            return None, None, None
        try:
            data = json.loads(script.string)
        except json.JSONDecodeError:
            return None, None, None
        return data.get("title"), data.get("description"), data.get("contentUrl")
