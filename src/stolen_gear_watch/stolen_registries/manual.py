"""Fallback for stolen-gear registries that can't be reasonably automated.

Stolen Camera Finder (stolencamerafinder.com) is the motivating case: it
works by uploading a photo and matching sensor dust/noise patterns
against a crowd-sourced corpus, not by querying a serial-number database.
There's no public API, and the "endpoint" is a file-upload + image
processing pipeline - automating that would mean scraping a service that
isn't built to be queried programmatically, which is exactly what this
project avoids (see README "Scraping ethics").

Rather than skip it silently, `ManualCheckRegistry` logs a direct,
actionable pointer every run so the user is reminded to check periodically
by hand. It never yields a RegistryHit, since it never actually checks
anything - a hit record implying "found" would be misleading.
"""

from __future__ import annotations

import logging
from collections.abc import Iterator

from stolen_gear_watch.core.models import RegistryHit, WatchedItem
from stolen_gear_watch.stolen_registries.base import RegistryChecker

logger = logging.getLogger(__name__)


class ManualCheckRegistry(RegistryChecker):
    def __init__(self, registry_key: str, name: str, check_url: str, instructions: str):
        self.registry_key = registry_key
        self.name = name
        self.check_url = check_url
        self.instructions = instructions

    def check(self, item: WatchedItem) -> Iterator[RegistryHit]:
        logger.info(
            "%s requires a manual check - %s: %s",
            self.name,
            self.instructions,
            self.check_url,
            extra={"watched_item_id": item.id, "registry": self.registry_key},
        )
        return iter(())


STOLEN_CAMERA_FINDER = ManualCheckRegistry(
    registry_key="stolen_camera_finder",
    name="Stolen Camera Finder",
    check_url="https://www.stolencamerafinder.com/",
    instructions="upload a recent photo from this camera to check for sensor dust-pattern matches",
)
