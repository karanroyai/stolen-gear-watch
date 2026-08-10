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

This means: only useful when `item.make` maps to one of Lenstag's brand
registries, and only as good as what's on that one page (Lenstag may
paginate or lazy-load long brand registries, which this simple GET won't
see - verify against the live site if a brand has many stolen entries).
"""

from __future__ import annotations

import logging
import re
from collections.abc import Iterator

from bs4 import BeautifulSoup

from stolen_gear_watch.core.models import RegistryHit, WatchedItem, normalize_serial
from stolen_gear_watch.stolen_registries.base import HttpRegistryChecker

logger = logging.getLogger(__name__)


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

        brand_slug = re.sub(r"[^a-z0-9]+", "-", item.make.lower()).strip("-")
        url = f"{self.base_url}/stolen/{brand_slug}-registry"
        try:
            resp = self._get(url)
        except Exception as exc:  # network/robots issues shouldn't crash a run
            logger.warning("lenstag: could not fetch %s: %s", url, exc)
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
