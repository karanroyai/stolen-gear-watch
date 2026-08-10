"""Zero-configuration fallback: don't call any image-search API, just log
a direct link so the user can check a listing photo by hand. This is the
default backend - reverse image search only becomes automated once the
user opts in by setting `reverse_image.backend` and an API key."""

from __future__ import annotations

import logging
from collections.abc import Iterator
from urllib.parse import quote

from stolen_gear_watch.reverse_image.base import ImageSearchBackend, ImageSearchResult

logger = logging.getLogger(__name__)


class ManualImageSearchBackend(ImageSearchBackend):
    backend_key = "manual"

    def search(self, image_path_or_url: str) -> Iterator[ImageSearchResult]:
        encoded = quote(image_path_or_url, safe="")
        tineye_url = f"https://tineye.com/search?url={encoded}"
        lens_url = f"https://lens.google.com/uploadbyurl?url={encoded}"
        logger.info(
            "No reverse-image backend configured - check this listing photo "
            "manually: TinEye %s | Google Lens %s",
            tineye_url,
            lens_url,
            extra={"listing_photo": image_path_or_url},
        )
        return iter(())
