"""Shared "polite HTTP client" behavior: robots.txt enforcement, rate
limiting, and a User-Agent that identifies this tool and an optional
contact address. Used by both marketplace scrapers and stolen-registry
checkers so that policy (don't hit sites that disallow it, don't hammer
them) lives in exactly one place.

Uses `protego` (the parser Scrapy uses) rather than stdlib
`urllib.robotparser` for robots.txt parsing. The stdlib parser only does
literal path-prefix matching and silently ignores `*`/`$` wildcards -
which is how most real-world robots.txt files (including every site this
project ships an adapter for) express their actual rules. Under the
stdlib parser, a rule like `Disallow: /*?*keyword=*` never matches
anything, which would make every disallowed search URL look allowed.
"""

from __future__ import annotations

import logging
import time
from urllib.parse import urljoin

import requests
from protego import Protego

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
    rate limit interval to `__init__`.

    `respect_robots_txt=False` is an explicit, informed-consent escape
    hatch - not a default, and not something adapter code should ever set
    for you. It exists because "the site's robots.txt disallows this" and
    "you have decided, for your own reasons, to proceed anyway" are two
    different facts, and this tool shouldn't quietly conflate them or
    pretend the site said yes. See ScraperSettings.respect_robots_txt and
    README "Scraping ethics" for how to turn it on.
    """

    base_url: str

    def __init__(
        self,
        rate_limit_seconds: float,
        contact_email: str | None = None,
        respect_robots_txt: bool = True,
    ):
        self.contact_email = contact_email
        self.respect_robots_txt = respect_robots_txt
        self._rate_limiter = RateLimiter(rate_limit_seconds)
        if respect_robots_txt:
            self._robots = self._load_robots()
        else:
            logger.warning(
                "respect_robots_txt is disabled for %s - proceeding against "
                "whatever that site's robots.txt says is a deliberate choice "
                "made in configuration, not something this tool verified is fine.",
                self.base_url,
            )
            self._robots = None

    def _load_robots(self) -> Protego | None:
        robots_url = urljoin(self.base_url, "/robots.txt")
        try:
            resp = requests.get(robots_url, headers={"User-Agent": self._user_agent()}, timeout=15)
            resp.raise_for_status()
        except requests.RequestException as exc:
            logger.warning(
                "Could not fetch robots.txt for %s (%s); proceeding cautiously "
                "but this should be investigated before relying on this client.",
                self.base_url,
                exc,
            )
            return None
        return Protego.parse(resp.text)

    def _user_agent(self) -> str:
        contact = f"; contact: {self.contact_email}" if self.contact_email else ""
        return f"stolen-gear-watch/{__version__} (+{PROJECT_URL}{contact})"

    def _get(
        self, url: str, params: dict | None = None, headers: dict | None = None
    ) -> requests.Response:
        # Build the exact URL requests will fetch (including the query
        # string from `params`) before checking robots.txt - a lot of
        # real-world disallow rules target query parameters specifically,
        # so checking the bare path would miss them entirely.
        full_url = requests.Request(url=url, params=params).prepare().url

        if self._robots is not None and not self._robots.can_fetch(full_url, self._user_agent()):
            raise RobotsDisallowedError(
                f"{full_url} is disallowed by {self.base_url}/robots.txt for this client"
            )
        self._rate_limiter.wait()
        resp = requests.get(
            full_url, headers={"User-Agent": self._user_agent(), **(headers or {})}, timeout=20
        )
        resp.raise_for_status()
        return resp

    def _post(
        self, url: str, data: dict | None = None, headers: dict | None = None, auth=None
    ) -> requests.Response:
        """For the rare non-GET call an official API needs (e.g. an OAuth
        token exchange) - still rate-limited, but deliberately skips the
        robots.txt check, which is meaningless for an authenticated API
        endpoint that isn't a public page anyone could crawl."""
        self._rate_limiter.wait()
        resp = requests.post(
            url,
            data=data,
            headers={"User-Agent": self._user_agent(), **(headers or {})},
            auth=auth,
            timeout=20,
        )
        resp.raise_for_status()
        return resp
