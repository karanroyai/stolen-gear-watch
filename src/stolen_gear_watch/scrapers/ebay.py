"""Adapter for eBay, via the official Browse API - not HTML scraping.

eBay's robots.txt (checked directly) opens with the same kind of blanket
"automated access is prohibited without permission" language as
Willhaben's or Facebook's, but with an explicit carve-out this project
can actually use: "Approved enterprise integrations must use our
official API and comply with our API License Agreement." Unlike
Facebook (no public API for Marketplace at all) or Willhaben (robots.txt
disallows the search paths outright, no sanctioned alternative), eBay
provides a real, individually-accessible path: the Buy APIs' Browse API,
free to register for at https://developer.ebay.com, with a default quota
of 5,000 calls/day - far more than a tool running a few times a day
needs. This adapter uses that, not the scraped website, so `self._get()`
talks to api.ebay.com (which has no robots.txt of its own - 404 -
correctly treated as unrestricted) rather than www.ebay.com.

STATUS: built against eBay's publicly documented Browse API schema, not
yet verified against a live response - this was written without API
credentials available to test with (see README/CONTRIBUTING for the
project's usual "verify before claiming it works" standard, which
couldn't be met here the normal way). In particular:
- `_parse_item`'s date extraction is a best-effort guess at where a
  listing start/creation date might appear in the ItemSummary search
  response schema; eBay's documentation is not fully clear on whether
  this is populated in search results vs. only in the single-item detail
  endpoint. If it's missing, this adapter simply won't populate
  `posted_at` (degrades gracefully - see pipeline.py's stolen_at filter,
  which only ever filters on a *known* date).
- Field names for price/image/location come from eBay's documented
  ItemSummary object shape; a live response should be diff'd against
  this once real credentials exist, and this docstring updated with a
  confirmed status the way willhaben.py/kleinanzeigen.py were once
  verified live.

Requires EBAY_CLIENT_ID and EBAY_CLIENT_SECRET in .env (from a free
developer.ebay.com account, "application access token" / client
credentials flow - no eBay user login involved, this is app-level
auth for public search, not acting as any particular eBay member).
Marketplace defaults to Germany (EBAY_DE); override via EBAY_MARKETPLACE_ID
in .env if a different eBay site is more relevant (there is no separate
Austrian eBay site, so EBAY_DE is the closest regional default in
Europe - a judgment call, not a verified "best" choice).
"""

from __future__ import annotations

import logging
import os
import time
from collections.abc import Iterator
from datetime import UTC, datetime

from stolen_gear_watch.core.config import require_env
from stolen_gear_watch.core.models import RawListing, WatchedItem
from stolen_gear_watch.scrapers.base import Adapter
from stolen_gear_watch.scrapers.registry import register_adapter

logger = logging.getLogger(__name__)

_TOKEN_URL = "https://api.ebay.com/identity/v1/oauth2/token"
_SEARCH_URL = "https://api.ebay.com/buy/browse/v1/item_summary/search"
_TOKEN_EXPIRY_SAFETY_MARGIN_SECONDS = 60


@register_adapter
class EbayAdapter(Adapter):
    site_key = "ebay"
    base_url = "https://api.ebay.com"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Credentials are read lazily on first search(), not here - Adapter
        # construction happens outside pipeline.py's per-adapter try/except,
        # so raising in __init__ over a missing .env value would take down
        # every other adapter's turn in the same run, not just this one.
        self._access_token: str | None = None
        self._token_expires_at: float = 0.0

    def search(self, item: WatchedItem) -> Iterator[RawListing]:
        query = " ".join(filter(None, [item.make, item.model]))
        limit = 50
        for page in range(self.settings.max_pages):
            resp = self._get(
                _SEARCH_URL,
                params={"q": query, "limit": limit, "offset": page * limit},
                headers=self._auth_headers(),
            )
            data = resp.json()
            summaries = data.get("itemSummaries", [])
            if not summaries:
                if page == 0:
                    logger.info("ebay: zero results for query %r", query)
                return

            for summary in summaries:
                listing = self._parse_item(summary)
                if listing is not None:
                    yield listing

            if page * limit + limit >= data.get("total", 0):
                return

    def _auth_headers(self) -> dict:
        token = self._get_access_token()
        marketplace_id = os.environ.get("EBAY_MARKETPLACE_ID", "EBAY_DE")
        return {
            "Authorization": f"Bearer {token}",
            "X-EBAY-C-MARKETPLACE-ID": marketplace_id,
        }

    def _get_access_token(self) -> str:
        if self._access_token and time.monotonic() < self._token_expires_at:
            return self._access_token

        client_id = require_env("EBAY_CLIENT_ID")
        client_secret = require_env("EBAY_CLIENT_SECRET")
        resp = self._post(
            _TOKEN_URL,
            data={
                "grant_type": "client_credentials",
                "scope": "https://api.ebay.com/oauth/api_scope",
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            auth=(client_id, client_secret),
        )
        payload = resp.json()
        self._access_token = payload["access_token"]
        expires_in = payload.get("expires_in", 0)
        self._token_expires_at = (
            time.monotonic() + expires_in - _TOKEN_EXPIRY_SAFETY_MARGIN_SECONDS
        )
        return self._access_token

    def _parse_item(self, summary: dict) -> RawListing | None:
        source_id = summary.get("itemId")
        url = summary.get("itemWebUrl")
        title = summary.get("title")
        if not source_id or not url or not title:
            return None

        price = currency = None
        price_obj = summary.get("price")
        if price_obj:
            try:
                price = float(price_obj["value"])
            except (KeyError, TypeError, ValueError):
                pass
            currency = price_obj.get("currency")

        location = None
        item_location = summary.get("itemLocation")
        if item_location:
            location = ", ".join(
                filter(None, [item_location.get("city"), item_location.get("country")])
            )

        posted_at = None
        # Undocumented/unconfirmed - see module docstring. Try a couple of
        # plausible field names; fall back to no date rather than guess.
        date_raw = summary.get("itemCreationDate") or summary.get("itemStartDate")
        if date_raw:
            try:
                posted_at = datetime.fromisoformat(date_raw).astimezone(UTC)
            except ValueError:
                logger.debug("ebay: could not parse date %r for item %s", date_raw, source_id)

        photo_urls = []
        image = summary.get("image")
        if image and image.get("imageUrl"):
            photo_urls.append(image["imageUrl"])
        for extra in summary.get("additionalImages", []):
            if extra.get("imageUrl"):
                photo_urls.append(extra["imageUrl"])

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
