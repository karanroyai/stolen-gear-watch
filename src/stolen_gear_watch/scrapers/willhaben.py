"""Adapter for willhaben.at (Austria).

STATUS: confirmed disallowed by robots.txt, not just unverified. See
README "Scraping ethics" - this adapter only runs at all if an operator
has explicitly set `respect_robots_txt: false` for it in their own
settings.yaml, an informed decision this project doesn't make for them.

Parses the `<script id="__NEXT_DATA__" type="application/json">` blob
every search results page embeds (a standard Next.js SSR hydration
payload) rather than scraping rendered HTML. Verified directly against a
live search: `props.pageProps.searchResult.advertSummaryList.advertSummary`
is a list of ads, each with an `attributes.attribute` list of
`{"name": ..., "values": [...]}` pairs - HEADING (title), BODY_DYN
(description), PRICE/AMOUNT, LOCATION, SEO_URL (path under /iad/),
ALL_IMAGE_URLS (semicolon-separated paths under
https://cache.willhaben.at/mmo/), and PUBLISHED (epoch milliseconds).
This is both more reliable than DOM scraping (structured data survives a
visual redesign that class-name scraping wouldn't) and gives a real post
date for free, which the rendered HTML doesn't expose at all.
"""

from __future__ import annotations

import json
import logging
import re
from collections.abc import Iterator
from datetime import UTC, datetime

from stolen_gear_watch.core.models import RawListing, WatchedItem
from stolen_gear_watch.scrapers.base import Adapter
from stolen_gear_watch.scrapers.registry import register_adapter
from stolen_gear_watch.scrapers.utils import looks_like_bot_challenge

logger = logging.getLogger(__name__)

_NEXT_DATA_RE = re.compile(
    r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>', re.DOTALL
)
_IMAGE_BASE = "https://cache.willhaben.at/mmo/"


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
                    "page, not real search results.",
                    query,
                )
                return

            ads = self._parse_ads(resp.text, query)
            if ads is None:
                return
            if not ads:
                logger.info(
                    "willhaben: zero ads on page %d for query %r", page, query
                )
                return

            for ad in ads:
                listing = self._parse_ad(ad)
                if listing is not None:
                    yield listing

    def _parse_ads(self, html: str, query: str) -> list[dict] | None:
        match = _NEXT_DATA_RE.search(html)
        if not match:
            logger.warning(
                "willhaben: __NEXT_DATA__ block not found for query %r - page "
                "structure may have changed, see module docstring.",
                query,
            )
            return None
        try:
            data = json.loads(match.group(1))
            return data["props"]["pageProps"]["searchResult"]["advertSummaryList"][
                "advertSummary"
            ]
        except (json.JSONDecodeError, KeyError) as exc:
            logger.warning(
                "willhaben: could not parse __NEXT_DATA__ for query %r: %s", query, exc
            )
            return None

    def _parse_ad(self, ad: dict) -> RawListing | None:
        attrs = {a["name"]: a["values"] for a in ad.get("attributes", {}).get("attribute", [])}

        def first(name: str) -> str | None:
            values = attrs.get(name)
            return values[0] if values else None

        source_id = first("ADID") or str(ad.get("id", ""))
        seo_url = first("SEO_URL")
        title = first("HEADING") or ad.get("description")
        if not source_id or not seo_url or not title:
            return None
        url = f"{self.base_url}/iad/{seo_url}"

        price = None
        price_raw = first("PRICE/AMOUNT")
        if price_raw:
            try:
                price = float(price_raw)
            except ValueError:
                pass

        posted_at = None
        published_raw = first("PUBLISHED")
        if published_raw:
            try:
                posted_at = datetime.fromtimestamp(int(published_raw) / 1000, tz=UTC)
            except (ValueError, OSError):
                pass

        photo_urls = []
        images_raw = first("ALL_IMAGE_URLS")
        if images_raw:
            photo_urls = [f"{_IMAGE_BASE}{p}" for p in images_raw.split(";") if p]

        return RawListing(
            source_site=self.site_key,
            source_id=source_id,
            url=url,
            title=title,
            description=first("BODY_DYN") or "",
            price=price,
            currency="EUR" if price is not None else None,
            location=first("LOCATION"),
            posted_at=posted_at,
            photo_urls=photo_urls,
        )
