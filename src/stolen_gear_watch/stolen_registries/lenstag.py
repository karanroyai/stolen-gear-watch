"""Checker for lenstag.com's public stolen-gear registry.

Lenstag is confirmed live and has a public "search stolen gear by serial
number" feature at /stolen - this is meant for anyone (not just Lenstag
account holders) to check gear they're about to buy, so it's a
fundamentally different scraping posture than a marketplace that doesn't
want bot traffic. However, submitting a serial through that search box
did not produce a distinct results URL during testing (likely a
client-side/JS-driven search rather than a simple GET), so this checker
takes the verified-working path instead: it fetches the public
per-brand registry browse page (`/stolen/{brand}-registry`, confirmed to
exist) and searches the rendered page text for the watched item's serial.

The brand slug is not always `make.lower()` - confirmed live: Fujifilm's
actual slug is `fuji`, not `fujifilm`. `/stolen/fujifilm-registry`
returns a 500 from Lenstag's own server (not a redirect, an error - this
looks like a broken alias on their end, not something on our side to
work around further), while `/stolen/fuji-registry` is the real page
with real content (454 real entries at the time this was checked,
including other Fujifilm thefts). `_BRAND_SLUG_OVERRIDES` exists for
exactly this kind of mismatch - add to it if another brand turns out to
need one; there's no general way to derive Lenstag's actual slug without
checking.

This means: only useful when `item.make` maps to one of Lenstag's brand
registries, and only as good as what's on that one page (Lenstag may
paginate or lazy-load long brand registries, which this simple GET won't
see - verify against the live site if a brand has many stolen entries;
Fuji's 454-entry page was confirmed to be a single unpaginated page, but
that won't hold for every brand).
"""

from __future__ import annotations

import logging
import re
from collections.abc import Iterator

from bs4 import BeautifulSoup

from stolen_gear_watch.core.models import RegistryHit, WatchedItem, normalize_serial
from stolen_gear_watch.stolen_registries.base import HttpRegistryChecker

logger = logging.getLogger(__name__)

_BRAND_SLUG_OVERRIDES = {
    "fujifilm": "fuji",
}


class LenstagChecker(HttpRegistryChecker):
    registry_key = "lenstag"
    base_url = "https://www.lenstag.com"

    def check(self, item: WatchedItem) -> Iterator[RegistryHit]:
        if not item.serial:
            logger.info(
                "lenstag: skipping %r - no serial number to check against the registry",
                item.id,
            )
            return

        naive_slug = re.sub(r"[^a-z0-9]+", "-", item.make.lower()).strip("-")
        brand_slug = _BRAND_SLUG_OVERRIDES.get(naive_slug, naive_slug)
        url = f"{self.base_url}/stolen/{brand_slug}-registry"
        try:
            resp = self._get(url)
        except Exception as exc:  # network/robots issues shouldn't crash a run
            logger.warning(
                "lenstag: could not fetch %s: %s - if this is a 500 and %r isn't in "
                "_BRAND_SLUG_OVERRIDES yet, check the live site for the real slug "
                "the way fujifilm->fuji was found.",
                url,
                exc,
                naive_slug,
            )
            return

        soup = BeautifulSoup(resp.text, "html.parser")
        page_text = soup.get_text(" ", strip=True)
        normalized_page = "".join(page_text.upper().split())
        target = normalize_serial(item.serial)

        if target in normalized_page:
            yield RegistryHit(
                watched_item_id=item.id,
                registry=self.registry_key,
                url=url,
                detail=f"Serial {item.serial} appears on {url} - verify manually before assuming a match.",
            )
