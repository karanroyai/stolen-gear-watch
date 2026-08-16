"""Shared base for classifieds sites built on the same white-label
platform - discovered live while investigating Pazar3.mk (North
Macedonia) and Merrjep.al (Albania): both serve visually identical
pages (same OpenGraphics naming, same `row-listing`/`Link_vis`/
`list-price` markup, same `Home2/Search` AJAX endpoint returning
`{"Html": "...", "Result": {...}}`), just under different domains,
languages, and locale-prefixed paths.

The homepage's visible search form is a red herring - it doesn't do a
plain GET with the query in the URL; it fires an XHR to
`{base_url}{search_path}?Search=<query>&...` (confirmed via Playwright's
request log while actually typing into the box and submitting - a plain
`?q=<query>` GET, which looks plausible and is what a first guess would
be, silently returns the *unfiltered* full listing set instead of an
error, which would have been a much harder bug to notice than a clean
404). The endpoint requires `X-Requested-With: XMLHttpRequest` - without
it, GETs to `Home2/Search` 302-redirect to the plain search page
instead of serving JSON.

Card markup (identical on both sites): `div.row-listing[data-product-id]`
containing `h2 a.Link_vis` (title + detail URL), `p.list-price` (price
text, space-thousands, currency as a trailing token - "700 EUR" /
"42 000 МКД"), an `img[data-src]` (the real image URL - `src` is always
a lazyload placeholder), and `.title.span-col-title > a.link-html.nobold`
breadcrumb-style links where the *last* one is the most specific known
location (this project doesn't need more granularity than that, so no
attempt is made to distinguish city from municipality/neighborhood).

Dates are `<day> <month-abbrev>. <HH:MM>` (no year - assume current
year, roll back one if that would be in the future) or a "today"/
"yesterday" word + time. Only the month abbreviations actually observed
live are mapped; unrecognized ones fall back to no date rather than a
guessed parse, same convention as bazar_bg.py's date handling.

Pagination is `&Page=N`; confirmed live that page 2 returns a distinct
set of `data-product-id`s (not a repeat of page 1).
"""

from __future__ import annotations

import logging
import re
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from typing import ClassVar

from bs4 import BeautifulSoup, Tag

from stolen_gear_watch.core.models import RawListing, WatchedItem
from stolen_gear_watch.scrapers.base import Adapter

logger = logging.getLogger(__name__)

_SEARCH_TYPES = [
    "ForSale",
    "ForBuy",
    "ForRent",
    "WantingForRent",
    "WorkIsWanted",
    "WorkIsGiven",
    "Exchange",
]


class RegionalClassifiedsAdapter(Adapter):
    """Base class - subclasses set `site_key`, `base_url`, `search_path`,
    `_month_abbrevs`, `_today_word`, and `_yesterday_word`."""

    search_path: str
    _month_abbrevs: ClassVar[dict[str, int]] = {}
    _today_word: str = ""
    _yesterday_word: str = ""

    def search(self, item: WatchedItem) -> Iterator[RawListing]:
        query = " ".join(filter(None, [item.make, item.model]))
        seen_ids: set[str] = set()
        for page in range(1, self.settings.max_pages + 1):
            params = {
                "Search": query,
                "CategoryId": "0",
                "LocationId": "0",
                "Sort": "DateDesc",
                "Page": str(page),
                "Display": "Pictures",
                "IsOnline": "false",
                "ImagesOnly": "false",
                "IsCargoEnabled": "false",
                "Types": _SEARCH_TYPES,
                "NearLocation": "False",
            }
            resp = self._get(
                f"{self.base_url}{self.search_path}",
                params=params,
                headers={"X-Requested-With": "XMLHttpRequest"},
            )
            data = resp.json()
            soup = BeautifulSoup(data.get("Html", ""), "html.parser")
            cards = soup.find_all("div", class_="row-listing")
            if not cards:
                if page == 1:
                    logger.info(
                        "%s: no row-listing cards found for query %r - selectors may be "
                        "stale, see _regional_classifieds_platform.py's module docstring",
                        self.site_key,
                        query,
                    )
                return

            new_this_page = 0
            for card in cards:
                source_id = card.get("data-product-id")
                if not source_id or source_id in seen_ids:
                    continue
                seen_ids.add(source_id)
                new_this_page += 1
                listing = self._parse_card(card, source_id)
                if listing is not None:
                    yield listing

            # The site has been observed to just re-serve page 1 rather
            # than erroring past the real last page - stop once a "new"
            # page brings nothing we haven't already seen.
            if new_this_page == 0:
                return

    def _parse_card(self, card: Tag, source_id: str) -> RawListing | None:
        title_el = card.select_one("h2 a.Link_vis")
        if title_el is None:
            return None
        title = title_el.get_text(strip=True)
        href = title_el.get("href")
        if not title or not href:
            return None
        url = href if href.startswith("http") else f"{self.base_url}{href}"

        price = currency = None
        price_el = card.select_one("p.list-price")
        if price_el:
            price, currency = self._parse_price(price_el.get_text(strip=True))

        loc_links = card.select(".title.span-col-title > a.link-html.nobold")
        location = loc_links[-1].get_text(strip=True) if loc_links else None

        posted_at = None
        date_el = card.select_one(".title.span-col-title > span.pull-right")
        if date_el:
            posted_at = self._parse_posted_at(date_el.get_text(strip=True))

        photo_urls = []
        img = card.select_one("img[data-src]")
        if img and img.get("data-src"):
            photo_urls.append(img["data-src"])

        return RawListing(
            source_site=self.site_key,
            source_id=source_id,
            url=url,
            title=title,
            price=price,
            currency=currency,
            location=location,
            posted_at=posted_at,
            photo_urls=photo_urls,
        )

    @staticmethod
    def _parse_price(text: str) -> tuple[float | None, str | None]:
        text = text.strip()
        if not text:
            return None, None
        match = re.match(r"^([\d\s.,]+)\s*([A-Za-zА-Яа-я]+)?$", text)
        if not match:
            return None, None
        number_part, currency = match.groups()
        normalized = number_part.replace(" ", "").replace("\xa0", "").replace(",", ".")
        try:
            price = float(normalized)
        except ValueError:
            return None, currency
        return price, currency

    def _parse_posted_at(self, text: str) -> datetime | None:
        text = text.strip()
        parts = text.split(" ", 1)
        if len(parts) != 2:
            return None
        day_or_word, rest = parts

        if self._today_word and day_or_word == self._today_word:
            return datetime.now(UTC)
        if self._yesterday_word and day_or_word == self._yesterday_word:
            return datetime.now(UTC) - timedelta(days=1)

        # "<day> <month-abbrev>. <HH:MM>" - rest is "<month-abbrev>. <HH:MM>"
        rest_parts = rest.rsplit(" ", 1)
        if len(rest_parts) != 2:
            return None
        month_raw, _time_part = rest_parts
        month = self._month_abbrevs.get(month_raw.strip().rstrip("."))
        if month is None:
            return None
        try:
            day = int(day_or_word)
        except ValueError:
            return None

        now = datetime.now(UTC)
        try:
            candidate = datetime(now.year, month, day, tzinfo=UTC)
        except ValueError:
            return None
        if candidate > now:
            candidate = candidate.replace(year=now.year - 1)
        return candidate
