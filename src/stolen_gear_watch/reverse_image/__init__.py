"""Reverse image search backend selection. Backends are constructed lazily
(only when selected) so an unconfigured `google-cloud-vision`/`pytineye`
dependency never breaks the default `manual` path."""

from __future__ import annotations

from stolen_gear_watch.core.config import ReverseImageSettings
from stolen_gear_watch.reverse_image.base import ImageSearchBackend, ImageSearchResult
from stolen_gear_watch.reverse_image.manual import ManualImageSearchBackend

__all__ = ["ImageSearchBackend", "ImageSearchResult", "get_backend"]


def get_backend(settings: ReverseImageSettings) -> ImageSearchBackend:
    if settings.backend == "manual":
        return ManualImageSearchBackend()
    if settings.backend == "google_vision":
        from stolen_gear_watch.reverse_image.google_vision import GoogleVisionBackend

        return GoogleVisionBackend()
    if settings.backend == "tineye":
        from stolen_gear_watch.reverse_image.tineye import TinEyeBackend

        return TinEyeBackend()
    raise ValueError(
        f"Unknown reverse_image.backend {settings.backend!r}. "
        f"Expected one of: manual, google_vision, tineye."
    )
