"""Adapter for publi24.ro (Romania).

Verified directly against live search results. robots.txt is unusually
permissive - explicit `Allow: /` for Googlebot, ClaudeBot, GPTBot, and
others, with only specific paths disallowed (`/Search/`, `/anunturi/?`,
account/admin paths) that don't overlap with the real search mechanism.
That mechanism isn't obvious from the URL alone: the homepage's search
box posts to `/hirdetesek?q=<query>`, not something under `/anunturi/`
or `/Search/` as might be guessed - confirmed via the page's own
`search-result-total-items`/`search-result-search-term` meta tags, which
only populate correctly for the real endpoint. Pagination is `&pag=N`
(not `page`).

Listing cards are `div.article-item` with a clean `data-articleid` UUID.
Like Kleinanzeigen, discounted listings nest an `old-price` span next to
`new-price` - only `new-price` (or the lone price if there's no
discount) is used, same "don't concatenate both" lesson learned there.

Dates are Romanian, no year shown: "azi HH:MM" (today), "ieri HH:MM"
(yesterday, inferred - not observed directly but follows the same
pattern as "azi"), or "D monthname" (e.g. "11 august") for anything
older, assumed to be the current year unless that would be in the
future (then last year - handles a search spanning a year boundary).
"""

from __future__ import annotations

import logging
import re
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta

from bs4 import BeautifulSoup, Tag

from stolen_gear_watch.core.models import RawListing, WatchedItem
from stolen_gear_watch.scrapers.base import Adapter
from stolen_gear_watch.scrapers.registry import register_adapter

logger = logging.getLogger(__name__)

_MONTHS_RO = {
    "ianuarie": 1,
    "februarie": 2,
    "martie": 3,
    "aprilie": 4,
    "mai": 5,
    "iunie": 6,
    "iulie": 7,
    "august": 8,
    "septembrie": 9,
    "octombrie": 10,
    "noiembrie": 11,
    "decembrie": 12,
}
_ABSOLUTE_DATE_RE = re.compile(r"^(\d{1,2})\s+([a-zăâîșț]+)$", re.IGNORECASE)


def _parse_posted_at(text: str) -> datetime | None:
    text = text.strip().lower()
    if text.startswith("azi"):
        return datetime.now(UTC)
    if text.startswith("ieri"):
        return datetime.now(UTC) - timedelta(days=1)

    match = _ABSOLUTE_DATE_RE.match(text)
    if not match:
        return None
    day = int(match.group(1))
    month = _MONTHS_RO.get(match.group(2))
    if month is None:
        return None

    now = datetime.now(UTC)
    year = now.year
    try:
        candidate = datetime(year, month, day, tzinfo=UTC)
    except ValueError:
        return None
    if candidate > now:
        candidate = candidate.replace(year=year - 1)
    return candidate


@register_adapter
class Publi24Adapter(Adapter):
    site_key = "publi24"
    base_url = "https://www.publi24.ro"

    def search(self, item: WatchedItem) -> Iterator[RawListing]:
        query = " ".join(filter(None, [item.make, item.model]))
        total_items = None
        yielded = 0
        for page in range(1, self.settings.max_pages + 1):
            if page > 1 and total_items is not None and yielded >= total_items:
                # A page number past the last one redirects back to page 1
                # instead of erroring or returning empty - stop before even
                # requesting it rather than silently re-yielding page 1's
                # results as "new" ones.
                return

            params = {"q": query}
            if page > 1:
                params["pag"] = page
            resp = self._get(f"{self.base_url}/hirdetesek", params=params)
            soup = BeautifulSoup(resp.text, "html.parser")

            if page == 1:
                total_meta = soup.find("meta", attrs={"name": "search-result-total-items"})
                if total_meta and total_meta.get("content", "").isdigit():
                    total_items = int(total_meta["content"])

            cards = soup.find_all("div", class_="article-item")
            if not cards:
                if page == 1:
                    logger.info(
                        "publi24: no article-item cards found for query %r "
                        "- selectors may be stale, see module docstring",
                        query,
                    )
                return

            for card in cards:
                listing = self._parse_card(card)
                if listing is not None:
                    yielded += 1
                    yield listing

    def _parse_card(self, card: Tag) -> RawListing | None:
        source_id = card.get("data-articleid")
        title_link = card.select_one(".article-title a")
        if not source_id or not title_link or not title_link.get("href"):
            return None
        url = title_link["href"]
        title = title_link.get_text(strip=True)
        if not title:
            return None

        description_el = card.select_one(".article-description")
        description = description_el.get_text(strip=True) if description_el else ""

        location_el = card.select_one(".article-location span")
        location = location_el.get_text(strip=True) if location_el else None

        date_el = card.select_one(".article-date span")
        posted_at = _parse_posted_at(date_el.get_text()) if date_el else None

        price = currency = None
        price_container = card.select_one(".article-price")
        if price_container:
            price_el = price_container.select_one(".new-price") or price_container
            price_text = next(price_el.stripped_strings, "")
            digits = "".join(c for c in price_text if c.isdigit())
            if digits:
                price = float(digits)
                currency = "RON" if "ron" in price_text.lower() else None

        photo_urls = []
        img = card.select_one(".art-img img")
        if img and img.get("src"):
            photo_urls.append(img["src"])

        return RawListing(
            source_site=self.site_key,
            source_id=source_id,
            url=url,
            title=title,
            description=description,
            price=price,
            currency=currency,
            location=location,
            posted_at=posted_at,
            photo_urls=photo_urls,
        )
