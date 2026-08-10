"""Interface for checking a watched item against an external stolen-gear
registry - a different direction from marketplace scraping: instead of
"does this listing match my item," it's "does a public registry already
know about my item, or can it search on my behalf."

Not every registry can be automated. `ManualCheckRegistry` (manual.py) is
the fallback for services like Stolen Camera Finder that work via image
upload rather than a queryable search - it doesn't hit the network at
all, it just returns a pointer for the user to check by hand.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Iterator

from stolen_gear_watch.core.models import RegistryHit, WatchedItem
from stolen_gear_watch.net import PoliteHttpClient


class RegistryChecker(ABC):
    registry_key: str

    @abstractmethod
    def check(self, item: WatchedItem) -> Iterator[RegistryHit]:
        """Yield a RegistryHit for each relevant result found for `item`.
        For registries that can't be automated, yield a single RegistryHit
        pointing at where the user should check manually."""
        raise NotImplementedError


class HttpRegistryChecker(RegistryChecker, PoliteHttpClient, ABC):
    """Base for registry checkers that do make network requests."""

    def __init__(self, rate_limit_seconds: float = 3.0, contact_email: str | None = None):
        PoliteHttpClient.__init__(self, rate_limit_seconds, contact_email)
