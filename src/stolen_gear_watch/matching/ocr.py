"""OCR-based serial matching for listing photos - reads any text visible
in a photo (e.g. a bottom plate or battery door photographed by the
seller) and checks it for the watched item's serial number.

This is a much more targeted signal than generic reverse-image/visual
similarity: it doesn't care what the camera looks like, only whether the
specific serial string is legible somewhere in the frame. Generic visual
similarity on a mass-produced camera body would flag every listing of the
same model as "similar" (every X100VI looks like every other X100VI),
which is no better than text matching already does - OCR-for-a-known-
serial is the one visual check that's actually specific to *your* unit,
not just the model.

Uses Google Cloud Vision's text detection - the same API and credentials
as reverse_image/google_vision.py's web detection, just a different
Vision feature, so there's no separate setup: if reverse_image.backend
is "google_vision" in settings.yaml, OCR matching is available too, using
GOOGLE_APPLICATION_CREDENTIALS from .env. There's no OCR equivalent for
the "manual" or "tineye" backends - with those, this check is skipped
entirely rather than logging a manual-check reminder per listing photo,
which would be far too noisy to be useful (most photos have no visible
serial at all).
"""

from __future__ import annotations

import logging

from stolen_gear_watch.core.config import ReverseImageSettings

logger = logging.getLogger(__name__)


class GoogleVisionOcr:
    def __init__(self) -> None:
        try:
            from google.cloud import vision
        except ImportError as exc:
            raise RuntimeError(
                "google-cloud-vision is not installed. Run "
                "`pip install stolen-gear-watch[google-vision]` and set "
                "GOOGLE_APPLICATION_CREDENTIALS to enable OCR serial matching."
            ) from exc
        self._client = vision.ImageAnnotatorClient()
        self._vision = vision

    def extract_text(self, image_path_or_url: str) -> str:
        """Returns all text Vision can read in the image, or "" if none
        (or the request failed - callers should treat that as "found
        nothing," not crash the run over one bad photo)."""
        if image_path_or_url.startswith(("http://", "https://")):
            image = self._vision.Image(
                source=self._vision.ImageSource(image_uri=image_path_or_url)
            )
        else:
            with open(image_path_or_url, "rb") as f:
                image = self._vision.Image(content=f.read())

        response = self._client.text_detection(image=image)
        if response.error.message:
            logger.warning(
                "Vision OCR error for %s: %s", image_path_or_url, response.error.message
            )
            return ""
        return response.full_text_annotation.text


def get_ocr(settings: ReverseImageSettings) -> GoogleVisionOcr | None:
    """None means "OCR matching isn't available with the current config" -
    callers should skip the check silently, not treat it as an error."""
    if settings.backend != "google_vision":
        return None
    return GoogleVisionOcr()
