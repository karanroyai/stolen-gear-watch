"""Shared "polite HTTP client" behavior: robots.txt enforcement, rate
limiting, and a User-Agent that identifies this tool and an optional
contact address. Used by both marketplace scrapers and stolen-registry
checkers so that policy (don't hit sites that disallow it, don't hammer
them) lives in exactly one place.
"""

from __future__ import annotations

import logging
import time
from urllib.parse import urljoin
from urllib.robotparser import RobotFileParser

import requests

from stolen_gear_watch import __version__

logger = logging.getLogger(__name__)

PROJECT_URL = "https://github.com/REPLACE_ME/stolen-gear-watch"


class RobotsDisallowedError(Exception):
    """Raised when robots.txt forbids fetching a URL this client needs."""


class RateLimiter:
    """Enforces a minimum delay between consecutive requests to one site."""

    def __init__(self, min_interval_seconds: float):
        self.min_interval = min_interval_seconds
        self._last_request: float | None = None

    def wait(self) -> None:
        if self._last_request is not None:
            elapsed = time.monotonic() - self._last_request
            remaining = self.min_interval - elapsed
            if remaining > 0:
                time.sleep(remaining)
        self._last_request = time.monotonic()


class PoliteHttpClient:
    """Mixin providing `self._get()`. Subclasses set `base_url` and pass a
    rate limit interval to `__init__`."""

    base_url: str

    def __init__(self, rate_limit_seconds: float, contact_email: str | None = None):
        self.contact_email = contact_email
        self._rate_limiter = RateLimiter(rate_limit_seconds)
        self._robots = self._load_robots()

    def _load_robots(self) -> RobotFileParser:
        rp = RobotFileParser()
        rp.set_url(urljoin(self.base_url, "/robots.txt"))
        try:
            rp.read()
        except OSError as exc:
            logger.warning(
                "Could not fetch robots.txt for %s (%s); proceeding cautiously "
                "but this should be investigated before relying on this client.",
                self.base_url,
                exc,
            )
        return rp

    def _user_agent(self) -> str:
        contact = f"; contact: {self.contact_email}" if self.contact_email else ""
        return f"stolen-gear-watch/{__version__} (+{PROJECT_URL}{contact})"

    def _get(self, url: str, params: dict | None = None) -> requests.Response:
        if not self._robots.can_fetch(self._user_agent(), url):
            raise RobotsDisallowedError(
                f"{url} is disallowed by {self.base_url}/robots.txt for this client"
            )
        self._rate_limiter.wait()
        resp = requests.get(
            url,
            params=params,
            headers={"User-Agent": self._user_agent()},
            timeout=20,
        )
        resp.raise_for_status()
        return resp
