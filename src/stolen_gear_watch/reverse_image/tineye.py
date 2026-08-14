"""TinEye's official reverse image search API - a separate, ToS-compliant
product from scraping tineye.com's web UI.

Requires a TinEye API account (public/private key pair, not the same
thing as a tineye.com login). Install with:

    pip install stolen-gear-watch[tineye]

TinEye's `score` is a relevance ranking (roughly 0-100, highest for the
best match) rather than a calibrated probability, so it's normalized to
0-1 here for consistency with other backends but shouldn't be read as
"percent confident."
"""

from __future__ import annotations

import logging
from collections.abc import Iterator

from stolen_gear_watch.core.config import require_env
from stolen_gear_watch.reverse_image.base import ImageSearchBackend, ImageSearchResult

logger = logging.getLogger(__name__)


class TinEyeBackend(ImageSearchBackend):
    backend_key = "tineye"

    def __init__(self) -> None:
        # Deliberately does no import or credential check here - get_backend()
        # constructs this at the top of pipeline.run(), outside any per-item
        # try/except, so raising in __init__ over a missing package or .env
        # value would crash the entire scheduled run instead of just this
        # feature. See scrapers/ebay.py for the same lesson.
        self._api = None

    def _client(self):
        if self._api is None:
            try:
                from pytineye import TinEyeAPIRequest
            except ImportError as exc:
                raise RuntimeError(
                    "pytineye is not installed. Run `pip install stolen-gear-watch[tineye]` "
                    "and set TINEYE_PUBLIC_KEY/TINEYE_PRIVATE_KEY, or switch "
                    "reverse_image.backend back to 'manual' in settings.yaml."
                ) from exc
            self._api = TinEyeAPIRequest(
                api_url="https://api.tineye.com/rest/",
                public_key=require_env("TINEYE_PUBLIC_KEY"),
                private_key=require_env("TINEYE_PRIVATE_KEY"),
            )
        return self._api

    def search(self, image_path_or_url: str) -> Iterator[ImageSearchResult]:
        api = self._client()
        if image_path_or_url.startswith(("http://", "https://")):
            response = api.search_url(image_path_or_url)
        else:
            with open(image_path_or_url, "rb") as f:
                response = api.search_data(f.read())

        for match in response.matches:
            yield ImageSearchResult(
                matched_url=match.image_url,
                confidence=min(1.0, match.score / 100.0),
                description=f"TinEye match on {match.domain}",
            )
