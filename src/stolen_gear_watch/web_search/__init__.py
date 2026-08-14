"""General keyword web search backend selection - see
google_custom_search.py for why this exists and what it filters."""

from __future__ import annotations

from stolen_gear_watch.core.config import WebSearchSettings
from stolen_gear_watch.web_search.google_custom_search import (
    GoogleCustomSearch,
    WebSearchResult,
)

__all__ = ["WebSearchResult", "get_web_search"]


def get_web_search(settings: WebSearchSettings) -> GoogleCustomSearch | None:
    """None means "web search isn't configured" - callers should skip it
    silently, same contract as matching/ocr.py::get_ocr."""
    if settings.backend != "google_custom_search":
        return None
    return GoogleCustomSearch()
