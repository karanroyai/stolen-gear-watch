"""Zero-configuration fallback: don't call any image-search API, just log
a direct link so the user can check a photo by hand. This is the default
backend - reverse image search only becomes automated once the user opts
in by setting `reverse_image.backend` and an API key.

Handles two different kinds of input differently: a scraped listing photo
is a public URL, so TinEye/Lens's "search by URL" endpoints work directly.
A watched item's own reference photo is a local file with no public URL -
pointing "search by URL" at a local path produces a broken link, so that
case gets a plain "upload this file yourself" pointer instead.
"""

from __future__ import annotations

import logging
from collections.abc import Iterator
from urllib.parse import quote

from stolen_gear_watch.reverse_image.base import ImageSearchBackend, ImageSearchResult

logger = logging.getLogger(__name__)


class ManualImageSearchBackend(ImageSearchBackend):
    backend_key = "manual"

    def search(self, image_path_or_url: str) -> Iterator[ImageSearchResult]:
        if image_path_or_url.startswith(("http://", "https://")):
            encoded = quote(image_path_or_url, safe="")
            logger.info(
                "No reverse-image backend configured - check this listing photo "
                "manually: TinEye %s | Google Lens %s",
                f"https://tineye.com/search?url={encoded}",
                f"https://lens.google.com/uploadbyurl?url={encoded}",
                extra={"listing_photo": image_path_or_url},
            )
        else:
            logger.info(
                "No reverse-image backend configured - upload %s yourself to check it: "
                "TinEye https://tineye.com/ | Google Lens https://lens.google.com/",
                image_path_or_url,
                extra={"reference_photo": image_path_or_url},
            )
        return iter(())
