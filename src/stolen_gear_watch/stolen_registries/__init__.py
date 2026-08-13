"""Stolen-gear registry checkers, keyed the same way as scraper adapters
in settings.yaml's `stolen_registries.enabled` list."""

from stolen_gear_watch.stolen_registries.base import RegistryChecker
from stolen_gear_watch.stolen_registries.lenstag import LenstagChecker
from stolen_gear_watch.stolen_registries.manual import STOLEN_CAMERA_FINDER_DUST_PATTERN
from stolen_gear_watch.stolen_registries.stolen_camera_finder import StolenCameraFinderChecker

REGISTRIES: dict[str, RegistryChecker] = {
    "lenstag": LenstagChecker(),
    "stolen_camera_finder": StolenCameraFinderChecker(),
    "stolen_camera_finder_dust_pattern": STOLEN_CAMERA_FINDER_DUST_PATTERN,
}

__all__ = ["REGISTRIES", "RegistryChecker"]
