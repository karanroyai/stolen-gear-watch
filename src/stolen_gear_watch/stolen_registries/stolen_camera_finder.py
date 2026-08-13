"""Checker for stolencamerafinder.com's serial-number search.

Earlier documentation in this project (see manual.py's history) treated
this service as entirely unautomatable, on the assumption it only does
reverse-image sensor-dust-pattern matching via photo upload. That was
wrong: it also has a separate, simpler manual serial-number search, which
crawls Flickr (via Flickr's own API) and other photo-sharing sites for
EXIF serial numbers embedded in publicly posted photos - exactly "has my
camera's serial shown up in an image anywhere."

Verified directly against the live site: the search page ships a
JS-driven form for interactive use, but also a plain server-rendered
fallback - `GET /search?serial=<value>&searchType=NOSCRIPT` - which
robots.txt does not disallow (only `/listmodels.do`, `/reportcamerasighting`,
`/addcamera`, `/exifreader.jsp`, `/changelog.jsp` are blocked). A
no-match response contains the literal string "Sorry, no results found
this time." - confirmed with both a nonsense test serial and a real one.

Note: their own "no results" page advertises a paid "Pro" tier for
automatic email alerts on new matches. This checker gets the same
outcome for free by being polled on whatever schedule `stolen-gear-watch
run` is already on (cron/systemd timer) - it's just doing the same
search a human would, periodically, instead of paying them to watch for
you.

The exact markup for a *successful* match was not observed during
development (no test serial with real hits was available) - if the
"no results" string is absent, this treats the response as a probable
hit and extracts what look like result links; if none can be confidently
extracted, it still surfaces a single hit pointing at the search page
itself rather than silently dropping a possible match.
"""

from __future__ import annotations

import logging
from collections.abc import Iterator
from urllib.parse import urlencode

from bs4 import BeautifulSoup

from stolen_gear_watch.core.models import RegistryHit, WatchedItem
from stolen_gear_watch.stolen_registries.base import HttpRegistryChecker

logger = logging.getLogger(__name__)

_NO_RESULTS_TEXT = "Sorry, no results found this time."


class StolenCameraFinderChecker(HttpRegistryChecker):
    registry_key = "stolen_camera_finder"
    base_url = "https://www.stolencamerafinder.com"

    def check(self, item: WatchedItem) -> Iterator[RegistryHit]:
        if not item.serial:
            logger.info(
                "stolen_camera_finder: skipping %r - no serial number to search",
                item.id,
            )
            return

        params = {"serial": item.serial, "searchType": "NOSCRIPT"}
        search_url = f"{self.base_url}/search?{urlencode(params)}"
        try:
            resp = self._get(f"{self.base_url}/search", params=params)
        except Exception as exc:  # network/robots issues shouldn't crash a run
            logger.warning("stolen_camera_finder: could not fetch %s: %s", search_url, exc)
            return

        if _NO_RESULTS_TEXT in resp.text:
            return

        soup = BeautifulSoup(resp.text, "html.parser")
        results_div = soup.find("div", id="search-results")
        links = []
        if results_div is not None:
            links = [
                a["href"]
                for a in results_div.find_all("a", href=True)
                if a["href"].startswith("http") and "/pricing" not in a["href"]
            ]

        if links:
            for link in dict.fromkeys(links):  # dedupe, preserve order
                yield RegistryHit(
                    watched_item_id=item.id,
                    registry=self.registry_key,
                    url=link,
                    detail=f"Possible photo match for serial {item.serial} - verify manually.",
                )
        else:
            logger.warning(
                "stolen_camera_finder: response for serial %r didn't contain the known "
                "'no results' text but no result links were found either - page structure "
                "may have changed. Surfacing the search page itself so this isn't silently "
                "dropped; verify manually.",
                item.serial,
            )
            yield RegistryHit(
                watched_item_id=item.id,
                registry=self.registry_key,
                url=search_url,
                detail=(
                    f"Possible match for serial {item.serial} - result page structure "
                    "wasn't recognized, check this search manually."
                ),
            )
