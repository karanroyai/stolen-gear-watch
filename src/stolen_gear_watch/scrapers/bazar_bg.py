"""Adapter for bazar.bg (Bulgaria).

Verified directly against live search results. robots.txt is permissive
(`Allow: /` with only login/account/a few category paths disallowed,
none overlapping search). The one "captcha" reference in the site's
pages is a reCAPTCHA key on the *login* form - unrelated to browsing or
searching, confirmed by inspecting where it actually appears.

The real search endpoint isn't the guessed `/obiavi/q/...` pattern - it's
the homepage search form's actual target, `GET /obiavi?q=<query>`,
confirmed via the page title and result count changing correctly for a
real query. Pagination is `&page=N`.

Listing cards are `a.listItemLink` (with a `data-id` and `href` already
pointing at the full ad URL - no need to build one). Prices use Bulgarian
formatting - space as thousands separator, comma as decimal separator
("1 400" = 1400, "97,15" = 97.15) - the reverse of what a locale-naive
parser might assume. Currency is whatever's in the nested `.currency`
span (usually EUR, sometimes BGN/"лв.") rather than assumed.

Dates are Bulgarian: "днес" (today), "вчера" (yesterday), "DD monthname"
for the current year, or "DD monthname YYYYг." (note the "г." = "year"
suffix) once a listing is old enough that the year is shown explicitly -
all four forms observed directly in a live sample.
"""

from __future__ import annotations

import logging
import re
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta

import requests
from bs4 import BeautifulSoup, Tag

from stolen_gear_watch.core.models import RawListing, WatchedItem
from stolen_gear_watch.scrapers.base import Adapter
from stolen_gear_watch.scrapers.registry import register_adapter

logger = logging.getLogger(__name__)

_MONTHS_BG = {
    "януари": 1,
    "февруари": 2,
    "март": 3,
    "април": 4,
    "май": 5,
    "юни": 6,
    "юли": 7,
    "август": 8,
    "септември": 9,
    "октомври": 10,
    "ноември": 11,
    "декември": 12,
}
_DATE_WITH_YEAR_RE = re.compile(r"^(\d{1,2})\s+([а-я]+)\s+(\d{4})г\.?$", re.IGNORECASE)
_DATE_NO_YEAR_RE = re.compile(r"^(\d{1,2})\s+([а-я]+)$", re.IGNORECASE)


def _parse_posted_at(text: str) -> datetime | None:
    text = text.strip().lower()
    if text == "днес":
        return datetime.now(UTC)
    if text == "вчера":
        return datetime.now(UTC) - timedelta(days=1)

    match = _DATE_WITH_YEAR_RE.match(text)
    if match:
        day, month_name, year = match.groups()
        month = _MONTHS_BG.get(month_name)
        if month is None:
            return None
        try:
            return datetime(int(year), month, int(day), tzinfo=UTC)
        except ValueError:
            return None

    match = _DATE_NO_YEAR_RE.match(text)
    if match:
        day, month_name = match.groups()
        month = _MONTHS_BG.get(month_name)
        if month is None:
            return None
        now = datetime.now(UTC)
        try:
            candidate = datetime(now.year, month, int(day), tzinfo=UTC)
        except ValueError:
            return None
        if candidate > now:
            candidate = candidate.replace(year=now.year - 1)
        return candidate

    return None


@register_adapter
class BazarBgAdapter(Adapter):
    site_key = "bazar_bg"
    base_url = "https://www.bazar.bg"

    def search(self, item: WatchedItem) -> Iterator[RawListing]:
        query = " ".join(filter(None, [item.make, item.model]))
        for page in range(1, self.settings.max_pages + 1):
            params = {"q": query}
            if page > 1:
                params["page"] = page
            try:
                resp = self._get(f"{self.base_url}/obiavi", params=params)
            except requests.HTTPError as exc:
                # A narrow-enough query fits on one page, and this site
                # 404s a page number past the end rather than returning an
                # empty result set - not an error, just "no more results".
                if page > 1 and exc.response is not None and exc.response.status_code == 404:
                    return
                raise
            soup = BeautifulSoup(resp.text, "html.parser")
            cards = soup.find_all("a", class_="listItemLink")
            if not cards:
                if page == 1:
                    logger.info(
                        "bazar_bg: no listItemLink cards found for query %r "
                        "- selectors may be stale, see module docstring",
                        query,
                    )
                return

            for card in cards:
                listing = self._parse_card(card)
                if listing is not None:
                    yield listing

    def _parse_card(self, card: Tag) -> RawListing | None:
        source_id = card.get("data-id")
        url = card.get("href")
        title_el = card.find("span", class_="title")
        title = title_el.get_text(strip=True) if title_el else None
        if not source_id or not url or not title:
            return None

        location_el = card.find("span", class_="location")
        location = location_el.get_text(strip=True) if location_el else None

        date_el = card.find("span", class_="date")
        posted_at = _parse_posted_at(date_el.get_text()) if date_el else None

        price = currency = None
        price_el = card.find("span", class_="price")
        if price_el:
            price_text = next(price_el.stripped_strings, "")
            normalized = price_text.replace(" ", "").replace("\xa0", "").replace(",", ".")
            try:
                price = float(normalized)
            except ValueError:
                price = None
            currency_el = price_el.find("span", class_="currency")
            currency = currency_el.get_text(strip=True) if currency_el else None

        photo_urls = []
        img = card.find("img")
        if img and (src := img.get("src") or img.get("data-src")):
            photo_urls.append(f"https:{src}" if src.startswith("//") else src)

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
