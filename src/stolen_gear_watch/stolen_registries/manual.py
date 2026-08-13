"""Fallback for stolen-gear registries (or specific search modes of one)
that can't be reasonably automated.

Stolen Camera Finder (stolencamerafinder.com) is the motivating case, but
only for its *reverse-image, sensor dust/noise-pattern* search mode: you
upload a photo and it matches against a crowd-sourced corpus. There's no
public API, and the "endpoint" is a file-upload + image processing
pipeline - automating that would mean scraping a service that isn't built
to be queried programmatically, which is exactly what this project avoids
(see README "Scraping ethics"). Its *separate* serial-number search mode
is automatable and has its own checker - see stolen_camera_finder.py.

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


STOLEN_CAMERA_FINDER_DUST_PATTERN = ManualCheckRegistry(
    registry_key="stolen_camera_finder_dust_pattern",
    name="Stolen Camera Finder (photo upload)",
    check_url="https://www.stolencamerafinder.com/",
    instructions="upload a recent photo from this camera to check for sensor dust-pattern matches "
    "(separate from the automated serial-number search - see stolen_camera_finder.py)",
)
