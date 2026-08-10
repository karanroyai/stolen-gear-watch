"""Notifier interface. Telegram is the only built-in implementation, but
email/webhook notifiers can be added later without touching the pipeline
- anything that implements `send()` can be plugged in."""

from __future__ import annotations

from abc import ABC, abstractmethod

from stolen_gear_watch.core.models import Listing, Match, RegistryHit, WatchedItem


class Notifier(ABC):
    @abstractmethod
    def send(self, match: Match, listing: Listing, item: WatchedItem) -> None:
        raise NotImplementedError

    @abstractmethod
    def send_registry_hit(self, hit: RegistryHit, item: WatchedItem) -> None:
        raise NotImplementedError
