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

STATUS: verified live once real credentials became available - the
OAuth client-credentials exchange, a real search (50 real Fujifilm
X100VI listings on the German marketplace, correct titles/prices/
locations/photos), and `_parse_item`'s date-field guess
(`itemCreationDate`/`itemStartDate`) all confirmed working against
actual API responses, not just documented schema.

Requires EBAY_CLIENT_ID and EBAY_CLIENT_SECRET in .env (from a free
developer.ebay.com account, "application access token" / client
credentials flow - no eBay user login involved, this is app-level
auth for public search, not acting as any particular eBay member).

Marketplaces searched are configurable via EBAY_MARKETPLACE_IDS (comma-
separated, e.g. "EBAY_DE,EBAY_AT,EBAY_PL") and default to Germany +
Austria + Poland - verified live (real API calls, not documentation
guesses) to be the actual set of Central/Eastern European sites eBay
operates. This correction matters: an earlier version of this docstring
claimed "there is no separate Austrian eBay site" - that was wrong.
EBAY_AT is real and, for this project's queries, returned several times
more listings than EBAY_DE. The full set of marketplaces the Browse API
actually supports (confirmed via a live 409 error listing them
explicitly, not eBay's marketing docs) is: EBAY_GB, EBAY_DE, EBAY_US,
EBAY_AU, EBAY_IT, EBAY_CA, EBAY_ES, EBAY_FR, EBAY_HK, EBAY_SG, EBAY_IE,
EBAY_PL, EBAY_NL, EBAY_AT, EBAY_CH, EBAY_BE. Notably absent: any
dedicated site for Czech Republic, Slovakia, Hungary, Romania, Bulgaria,
Serbia, Croatia, Slovenia, Ukraine, the Baltics, or Greece - eBay simply
doesn't operate local marketplaces there. Passing one of those codes
doesn't error, it silently falls back to EBAY_US's result set (confirmed
by comparing totals), which is worse than useless for this project, so
don't add them here even though the country names are tempting.

The legacy singular EBAY_MARKETPLACE_ID is still honored for anyone with
it already set, but EBAY_MARKETPLACE_IDS takes precedence if both are
present. The same physical item can appear via more than one marketplace
query (eBay shows plenty of listings cross-border); duplicates across
marketplaces are collapsed within a single search() call using itemId,
and the DB layer's (source_site, source_id) uniqueness collapses any
that slip through across separate runs.
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

# Verified live against the Browse API (see module docstring) - Germany,
# Austria, and Poland are the only genuine Central/Eastern European
# marketplaces eBay operates. This is the default when neither
# EBAY_MARKETPLACE_IDS nor the legacy EBAY_MARKETPLACE_ID is set.
_DEFAULT_MARKETPLACES = ("EBAY_DE", "EBAY_AT", "EBAY_PL")


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
        seen_item_ids: set[str] = set()
        for marketplace_id in self._marketplace_ids():
            for page in range(self.settings.max_pages):
                resp = self._get(
                    _SEARCH_URL,
                    params={"q": query, "limit": limit, "offset": page * limit},
                    headers=self._auth_headers(marketplace_id),
                )
                data = resp.json()
                summaries = data.get("itemSummaries", [])
                if not summaries:
                    if page == 0:
                        logger.info(
                            "ebay: zero results for query %r on %s", query, marketplace_id
                        )
                    break

                for summary in summaries:
                    item_id = summary.get("itemId")
                    # Cross-border visibility means the same listing can
                    # surface under more than one marketplace query - skip
                    # re-yielding it within this same search() call.
                    if item_id and item_id in seen_item_ids:
                        continue
                    listing = self._parse_item(summary)
                    if listing is not None:
                        if item_id:
                            seen_item_ids.add(item_id)
                        yield listing

                if page * limit + limit >= data.get("total", 0):
                    break

    def _marketplace_ids(self) -> list[str]:
        plural = os.environ.get("EBAY_MARKETPLACE_IDS")
        if plural:
            return [m.strip() for m in plural.split(",") if m.strip()]
        # Legacy single-value override, kept for anyone with it already set.
        singular = os.environ.get("EBAY_MARKETPLACE_ID")
        if singular:
            return [singular]
        return list(_DEFAULT_MARKETPLACES)

    def _auth_headers(self, marketplace_id: str) -> dict:
        token = self._get_access_token()
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
