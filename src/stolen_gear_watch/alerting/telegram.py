"""Telegram alerting via a plain HTTP POST to the Bot API. Deliberately
not using the `python-telegram-bot` library - we only ever send one kind
of message, so a full bot framework (built for receiving updates, polling,
webhooks) would be a lot of dependency weight for one POST request.
"""

from __future__ import annotations

import logging

import requests

from stolen_gear_watch.alerting.base import Notifier
from stolen_gear_watch.core.config import require_env
from stolen_gear_watch.core.models import Listing, Match, RegistryHit, WatchedItem

logger = logging.getLogger(__name__)

_API_URL = "https://api.telegram.org/bot{token}/sendMessage"


class TelegramNotifier(Notifier):
    def __init__(self) -> None:
        # Credentials are read lazily on first send(), not here -
        # get_notifiers() constructs this at the top of pipeline.run(),
        # outside any per-item try/except, so raising in __init__ over a
        # missing .env value would crash the entire scheduled run instead
        # of just alerting. See scrapers/ebay.py for the same lesson.
        self._token: str | None = None
        self._chat_id: str | None = None

    def _credentials(self) -> tuple[str, str]:
        if self._token is None or self._chat_id is None:
            self._token = require_env("TELEGRAM_BOT_TOKEN")
            self._chat_id = require_env("TELEGRAM_CHAT_ID")
        return self._token, self._chat_id

    def send(self, match: Match, listing: Listing, item: WatchedItem) -> None:
        self._token, self._chat_id = self._credentials()
        text = (
            f"Possible match for {item.make} {item.model} ({item.id})\n"
            f"Match type: {match.match_type.value}, confidence: {match.confidence:.2f}\n"
            f"{match.detail}\n"
            f"Listing: {listing.title}\n"
            f"{f'{listing.price} {listing.currency}' if listing.price else 'price not listed'}"
            f"{f' - {listing.location}' if listing.location else ''}\n"
            f"{listing.url}"
        )
        resp = requests.post(
            _API_URL.format(token=self._token),
            json={"chat_id": self._chat_id, "text": text, "disable_web_page_preview": False},
            timeout=15,
        )
        if not resp.ok:
            logger.error(
                "Telegram alert failed (status %d): %s", resp.status_code, resp.text
            )
            resp.raise_for_status()

    def send_registry_hit(self, hit: RegistryHit, item: WatchedItem) -> None:
        self._token, self._chat_id = self._credentials()
        text = (
            f"Possible stolen-registry hit for {item.make} {item.model} ({item.id})\n"
            f"Registry: {hit.registry}\n"
            f"{hit.detail}\n"
            f"{hit.url}"
        )
        resp = requests.post(
            _API_URL.format(token=self._token),
            json={"chat_id": self._chat_id, "text": text, "disable_web_page_preview": False},
            timeout=15,
        )
        if not resp.ok:
            logger.error(
                "Telegram registry-hit alert failed (status %d): %s",
                resp.status_code,
                resp.text,
            )
            resp.raise_for_status()
