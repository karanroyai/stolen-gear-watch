"""Google Cloud Vision API - Web Detection backend.

Official, ToS-compliant reverse image search. Requires a GCP project with
the Vision API enabled and a service account key referenced by the
`GOOGLE_APPLICATION_CREDENTIALS` env var (standard google-cloud-python
auth convention - see .env.example). Install with:

    pip install stolen-gear-watch[google-vision]

Web Detection doesn't return a single numeric confidence per match the
way TinEye does; it buckets results into full/partial matches and
"pages with matching images." The confidence values below are a
deliberately coarse heuristic reflecting that: full image matches are
strong evidence, partial matches and page mentions are weaker.
"""

from __future__ import annotations

import logging
from collections.abc import Iterator

from stolen_gear_watch.reverse_image.base import ImageSearchBackend, ImageSearchResult

logger = logging.getLogger(__name__)

_CONFIDENCE_FULL_MATCH = 1.0
_CONFIDENCE_PARTIAL_MATCH = 0.7
_CONFIDENCE_PAGE_MENTION = 0.5


class GoogleVisionBackend(ImageSearchBackend):
    backend_key = "google_vision"

    def __init__(self) -> None:
        try:
            from google.cloud import vision
        except ImportError as exc:
            raise RuntimeError(
                "google-cloud-vision is not installed. Run "
                "`pip install stolen-gear-watch[google-vision]` and set "
                "GOOGLE_APPLICATION_CREDENTIALS, or switch reverse_image.backend "
                "back to 'manual' in settings.yaml."
            ) from exc
        self._client = vision.ImageAnnotatorClient()
        self._vision = vision

    def search(self, image_path_or_url: str) -> Iterator[ImageSearchResult]:
        if image_path_or_url.startswith(("http://", "https://")):
            image = self._vision.Image(source=self._vision.ImageSource(image_uri=image_path_or_url))
        else:
            with open(image_path_or_url, "rb") as f:
                image = self._vision.Image(content=f.read())

        response = self._client.web_detection(image=image)
        if response.error.message:
            logger.warning(
                "Google Vision Web Detection error for %s: %s",
                image_path_or_url,
                response.error.message,
            )
            return

        annotation = response.web_detection
        for match in annotation.full_matching_images:
            yield ImageSearchResult(
                matched_url=match.url, confidence=_CONFIDENCE_FULL_MATCH, description="full image match"
            )
        for match in annotation.partial_matching_images:
            yield ImageSearchResult(
                matched_url=match.url,
                confidence=_CONFIDENCE_PARTIAL_MATCH,
                description="partial image match",
            )
        for page in annotation.pages_with_matching_images:
            yield ImageSearchResult(
                matched_url=page.url,
                confidence=_CONFIDENCE_PAGE_MENTION,
                description="page contains a matching image",
            )
