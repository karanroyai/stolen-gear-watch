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

Two backends, chosen independently of reverse_image.backend via
ocr.backend in settings.yaml (they solve different problems - you might
want local OCR without paying for any image-search API, or vice versa):

- google_vision: Google Cloud Vision's text detection. Same API/
  credentials as reverse_image/google_vision.py's web detection, just a
  different Vision feature - no separate setup if you've already
  configured that. Costs money past the free tier.
- easyocr: runs entirely locally via a deep-learning model (EasyOCR,
  https://github.com/JaidedAI/EasyOCR) - free, no account, no per-request
  cost. Chosen over Tesseract because it's built for "text in a photo"
  (scene text) rather than scanned documents, which is a much closer
  match to "serial number etched on a camera, photographed at an angle"
  than Tesseract's traditional strength. Tradeoffs: pulls in PyTorch (a
  large dependency), is slower per-image on CPU than a cloud API, and
  downloads model weights (~100MB) the first time it runs.

There's no OCR equivalent for the "manual"/"tineye" reverse-image
backends, and no manual-check-link fallback here either (unlike
reverse_image/manual.py) - logging a "go OCR this yourself" reminder for
every listing photo would be far too noisy given most photos never show
a serial at all. With ocr.backend: none (the default), this check is
just skipped.
"""

from __future__ import annotations

import logging

import requests

from stolen_gear_watch.core.config import OcrSettings

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


class EasyOcr:
    def __init__(self) -> None:
        try:
            import easyocr
        except ImportError as exc:
            raise RuntimeError(
                "easyocr is not installed. Run `pip install stolen-gear-watch[easyocr]` "
                "to enable local OCR serial matching."
            ) from exc
        # Loads (and on first run, downloads) the recognition model - do
        # this once per process, not per image.
        self._reader = easyocr.Reader(["en"])

    def extract_text(self, image_path_or_url: str) -> str:
        if image_path_or_url.startswith(("http://", "https://")):
            try:
                resp = requests.get(image_path_or_url, timeout=20)
                resp.raise_for_status()
            except requests.RequestException as exc:
                logger.warning(
                    "Could not download %s for local OCR: %s", image_path_or_url, exc
                )
                return ""
            image_input = resp.content
        else:
            image_input = image_path_or_url

        try:
            results = self._reader.readtext(image_input, detail=0)
        except Exception:
            logger.exception("EasyOCR failed on %s", image_path_or_url)
            return ""
        return " ".join(results)


def get_ocr(settings: OcrSettings) -> GoogleVisionOcr | EasyOcr | None:
    """None means "OCR matching isn't available with the current config" -
    callers should skip the check silently, not treat it as an error."""
    if settings.backend == "google_vision":
        return GoogleVisionOcr()
    if settings.backend == "easyocr":
        return EasyOcr()
    return None
