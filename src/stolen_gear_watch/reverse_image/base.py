"""Reverse image search backends.

Scraping Google Lens or Google Images directly is explicitly out of scope
for this project - it's against Google's ToS, brittle, and carries real
blocking/legal risk, which is exactly the kind of scraping the README
says not to build. Instead this module wraps *official* APIs that do
roughly the same job:

- Google Cloud Vision API's Web Detection feature: given an image, returns
  pages containing matching/visually-similar images plus best-guess
  labels. This is the closest legitimate equivalent to "search by image."
- TinEye's official API: a separate, ToS-compliant product from scraping
  tineye.com's web UI.

Both require an API key and cost money past a free tier, so the default
backend (`manual`) needs no credentials at all: it just logs a direct,
prefilled link for the user to check by hand. Automation is opt-in.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Iterator

from pydantic import BaseModel


class ImageSearchResult(BaseModel):
    matched_url: str
    confidence: float
    description: str = ""


class ImageSearchBackend(ABC):
    backend_key: str

    @abstractmethod
    def search(self, image_path_or_url: str) -> Iterator[ImageSearchResult]:
        """`image_path_or_url` is a listing photo URL scraped from a
        marketplace (not a local file) in the normal pipeline, but
        implementations may also accept local paths for the reference
        photos in watched_items.yaml if useful for a given backend."""
        raise NotImplementedError
