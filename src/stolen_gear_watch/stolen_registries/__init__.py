"""Stolen-gear registry checkers, keyed the same way as scraper adapters
in settings.yaml's `stolen_registries.enabled` list."""

from stolen_gear_watch.stolen_registries.base import RegistryChecker
from stolen_gear_watch.stolen_registries.lenstag import LenstagChecker
from stolen_gear_watch.stolen_registries.manual import STOLEN_CAMERA_FINDER

REGISTRIES: dict[str, RegistryChecker] = {
    "lenstag": LenstagChecker(),
    "stolen_camera_finder": STOLEN_CAMERA_FINDER,
}

__all__ = ["REGISTRIES", "RegistryChecker"]
