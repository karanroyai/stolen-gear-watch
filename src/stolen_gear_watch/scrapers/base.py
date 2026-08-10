"""Adapter interface for marketplace scrapers.

Adding a new site means writing one class here that implements `search()`
and registering it with `@register_adapter`. Nothing outside this package
(the pipeline, matching, alerting) knows or cares which sites exist.

Every adapter gets robots.txt enforcement and rate limiting for free via
`PoliteHttpClient.get()` (see net.py) - don't call `requests` directly
from a subclass. If robots.txt disallows the paths this adapter needs,
that's a signal to stop and either find an allowed path (e.g. a public
search API) or drop the site and document it as a manual-check target
instead.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Iterator

from stolen_gear_watch.core.config import ScraperSettings
from stolen_gear_watch.core.models import RawListing, WatchedItem
from stolen_gear_watch.net import PoliteHttpClient, RobotsDisallowedError

__all__ = ["Adapter", "RobotsDisallowedError"]


class Adapter(PoliteHttpClient, ABC):
    """One marketplace site. Subclasses set `site_key` and `base_url` and
    implement `search()` using `self._get()` for all HTTP access."""

    site_key: str

    def __init__(self, settings: ScraperSettings, contact_email: str | None = None):
        self.settings = settings
        super().__init__(
            rate_limit_seconds=settings.rate_limit_seconds,
            contact_email=contact_email,
            respect_robots_txt=settings.respect_robots_txt,
        )

    @abstractmethod
    def search(self, item: WatchedItem) -> Iterator[RawListing]:
        """Yield RawListing for results matching `item`. Implementations
        should respect `self.settings.max_pages` and stop paginating once
        results clearly stop matching the item's category/keywords."""
        raise NotImplementedError
