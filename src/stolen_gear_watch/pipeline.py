"""Orchestrates one end-to-end run: scrape configured marketplaces for
each active watched item, match new listings, check stolen registries,
and alert on anything new. Invoked once per `stolen-gear-watch run` -
this module has no loop or scheduler of its own; that's cron/systemd's
job (see README "Running on a schedule").
"""

from __future__ import annotations

import logging
from pathlib import Path

from stolen_gear_watch import scrapers, stolen_registries
from stolen_gear_watch.alerting import get_notifiers
from stolen_gear_watch.core.config import Settings
from stolen_gear_watch.core.db import Database
from stolen_gear_watch.core.models import Listing, Match, MatchType, RegistryHit, WatchedItem
from stolen_gear_watch.matching.accessory import is_likely_non_item_listing
from stolen_gear_watch.matching.color import mentions_conflicting_color
from stolen_gear_watch.matching.ocr import get_ocr
from stolen_gear_watch.matching.serial import serial_match_confidence
from stolen_gear_watch.matching.text import text_match_confidence
from stolen_gear_watch.net import RobotsDisallowedError
from stolen_gear_watch.reverse_image import get_backend
from stolen_gear_watch.reverse_image.manual import ManualImageSearchBackend
from stolen_gear_watch.web_search import get_web_search
from stolen_gear_watch.web_search.google_custom_search import is_excluded_domain

REFERENCE_PHOTO_SEARCH_REGISTRY_KEY = "reverse_image_web_search"
WEB_SEARCH_REGISTRY_KEY = "web_search"

logger = logging.getLogger(__name__)


def _build_optional(factory, settings, label: str, fallback=None):
    """Belt-and-suspenders around every get_X(settings) backend factory
    called here: each one is already fixed to defer its own credential
    loading (see e.g. scrapers/ebay.py, web_search/google_custom_search.py),
    but this call site sits outside any per-item try/except - one bad
    backend construction would otherwise take down the entire scheduled
    run, not just that feature. Real incident, not a hypothetical: an
    earlier version of the web-search backend read a missing env var in
    __init__ and did exactly this."""
    try:
        return factory(settings)
    except Exception:
        logger.exception("Failed to construct %s - disabled for this run", label)
        return fallback


def run(settings: Settings, watched_items: list[WatchedItem], db: Database) -> None:
    active_items = [item for item in watched_items if item.active]
    if not active_items:
        logger.warning("No active watched items - nothing to do")
        return

    notifiers = get_notifiers(settings)
    image_backend = _build_optional(
        get_backend,
        settings.reverse_image,
        "reverse-image backend",
        fallback=ManualImageSearchBackend(),
    )
    ocr = _build_optional(get_ocr, settings.ocr, "OCR backend")
    web_search = _build_optional(get_web_search, settings.web_search, "web search backend")

    items_by_id = {item.id: item for item in active_items}

    _run_scrapers(settings, active_items, db, image_backend, ocr)
    _run_registry_checks(settings, active_items, db)
    _run_reference_photo_search(settings, active_items, db, image_backend)
    _run_web_search(settings, active_items, db, web_search)
    _send_pending_alerts(db, notifiers, items_by_id)
    _send_pending_registry_alerts(db, notifiers, items_by_id)


def _run_scrapers(settings, active_items, db, image_backend, ocr) -> None:
    for site_key, scraper_settings in settings.scrapers.items():
        if not scraper_settings.enabled:
            continue
        try:
            adapter_cls = scrapers.get_adapter(site_key)
        except KeyError:
            logger.warning("No adapter registered for site %r, skipping", site_key)
            continue

        adapter = adapter_cls(scraper_settings, contact_email=settings.scraper_contact_email)
        for item in active_items:
            run_id = db.start_run(f"{site_key}:{item.id}")
            listings_found = new_listings = 0
            error: str | None = None
            try:
                for raw in adapter.search(item):
                    listings_found += 1
                    listing, is_new = db.upsert_listing(raw)
                    if is_new:
                        new_listings += 1
                    _evaluate_listing(listing, item, settings, db, image_backend, ocr)
            except RobotsDisallowedError as exc:
                logger.warning("Stopped scraping %s: %s", site_key, exc)
                error = str(exc)
            except Exception as exc:
                logger.exception("Adapter %s failed for item %s", site_key, item.id)
                error = str(exc)
            finally:
                db.finish_run(run_id, listings_found, new_listings, error)


def _evaluate_listing(
    listing: Listing, item: WatchedItem, settings: Settings, db: Database, image_backend, ocr
) -> None:
    haystack = f"{listing.title}\n{listing.description}"

    # Confident negative signals, checked before any matching logic runs:
    # a listing posted before the item was stolen, or one that explicitly
    # describes a conflicting color, can't be the stolen item - skip it
    # entirely rather than let text/serial/image matching still fire.
    if (
        item.stolen_at is not None
        and listing.posted_at is not None
        and listing.posted_at.date() < item.stolen_at.date()
    ):
        return
    if item.color and mentions_conflicting_color(haystack, item.color):
        return
    if (reason := is_likely_non_item_listing(listing.title, item)) is not None:
        logger.info(
            "Skipping listing %r for item %r - %s", listing.title[:80], item.id, reason
        )
        return

    if item.serial:
        confidence = serial_match_confidence(haystack, item.serial)
        if confidence > 0:
            db.add_match(
                Match(
                    listing_id=listing.id,
                    watched_item_id=item.id,
                    match_type=MatchType.SERIAL,
                    confidence=confidence,
                    detail=f"Serial {item.serial} found in listing text",
                )
            )

    text_confidence = text_match_confidence(listing.title, listing.description, item)
    if text_confidence >= settings.match_confidence_threshold:
        db.add_match(
            Match(
                listing_id=listing.id,
                watched_item_id=item.id,
                match_type=MatchType.TEXT,
                confidence=text_confidence,
                detail=f"Make/model text match ({text_confidence:.2f})",
            )
        )

    # Reverse image search is the expensive/opt-in path - only worth
    # running when the text alone wasn't already a confident match and
    # there's something to compare against.
    if text_confidence < settings.match_confidence_threshold and listing.photo_urls:
        for photo_url in listing.photo_urls:
            # search() is a generator in every real backend (yield, not
            # return) - its body, including any request/auth error, only
            # runs once iterated. The whole for-loop has to be inside the
            # try, not just the call that creates the generator, or
            # exceptions raised during iteration go uncaught. (Real
            # incident: this exact mistake in _run_web_search took down
            # an entire scheduled run - see pipeline.py's git history.)
            try:
                for result in image_backend.search(photo_url):
                    if result.confidence >= settings.reverse_image.min_confidence:
                        db.add_match(
                            Match(
                                listing_id=listing.id,
                                watched_item_id=item.id,
                                match_type=MatchType.IMAGE,
                                confidence=result.confidence,
                                detail=f"{result.description}: {result.matched_url}",
                            )
                        )
            except Exception:
                logger.exception("Reverse image search failed for %s", photo_url)
                continue

    # OCR is the other opt-in, per-photo check, gated the same way as
    # reverse image search (only worth it when text alone didn't already
    # confirm the match) - but only runs at all if `ocr` is configured
    # (see matching/ocr.py::get_ocr), and only if there's a serial to look
    # for in the first place.
    if (
        ocr is not None
        and item.serial
        and text_confidence < settings.match_confidence_threshold
        and listing.photo_urls
    ):
        for photo_url in listing.photo_urls:
            try:
                photo_text = ocr.extract_text(photo_url)
            except Exception:
                logger.exception("OCR failed for %s", photo_url)
                continue
            if not photo_text:
                continue
            ocr_confidence = serial_match_confidence(photo_text, item.serial)
            if ocr_confidence > 0:
                db.add_match(
                    Match(
                        listing_id=listing.id,
                        watched_item_id=item.id,
                        match_type=MatchType.OCR,
                        confidence=ocr_confidence,
                        detail=f"Serial {item.serial} read via OCR on listing photo: {photo_url}",
                    )
                )


def _run_registry_checks(settings: Settings, active_items, db: Database) -> None:
    for registry_key in settings.stolen_registries.enabled:
        checker = stolen_registries.REGISTRIES.get(registry_key)
        if checker is None:
            logger.warning("No registry checker registered for %r, skipping", registry_key)
            continue
        for item in active_items:
            try:
                for hit in checker.check(item):
                    db.add_registry_hit(hit)
            except Exception:
                logger.exception("Registry checker %s failed for item %s", registry_key, item.id)


def _run_reference_photo_search(
    settings: Settings, active_items, db: Database, image_backend
) -> None:
    """Search the web (via whichever reverse_image.backend is configured)
    using each watched item's own reference photos as the query image -
    catches your camera's specific photos turning up somewhere online,
    independent of anything scraped from a marketplace. With the default
    `manual` backend this just logs a check-it-yourself link per photo,
    same as any other unconfigured backend in this project."""
    for item in active_items:
        for photo_path in item.reference_photos:
            # See the matching comment in _evaluate_listing: search() is a
            # generator, so the whole for-loop must be inside the try, not
            # just the call that creates it.
            try:
                for result in image_backend.search(photo_path):
                    if result.confidence < settings.reverse_image.min_confidence:
                        continue
                    db.add_registry_hit(
                        RegistryHit(
                            watched_item_id=item.id,
                            registry=REFERENCE_PHOTO_SEARCH_REGISTRY_KEY,
                            url=result.matched_url,
                            detail=f"{result.description} (confidence {result.confidence:.2f}) "
                            f"- from reference photo {Path(photo_path).name}",
                        )
                    )
            except Exception:
                logger.exception(
                    "Reference photo search failed for %s (item %s)", photo_path, item.id
                )
                continue


def _run_web_search(settings: Settings, active_items, db: Database, web_search) -> None:
    """General keyword web search (Google Custom Search) for each watched
    item, independent of any specific marketplace - catches resale
    listings anywhere on the web, not just the sites this project has a
    dedicated adapter for. Reuses the same accessory/color filters
    already applied to marketplace listings, plus a domain check, since
    a plain web search surfaces retailer/manufacturer noise a dedicated
    adapter never sees in the first place."""
    if web_search is None:
        return
    for item in active_items:
        query = " ".join(filter(None, [item.make, item.model]))
        if not query:
            continue
        # search() is a generator - the whole for-loop must be inside the
        # try, not just the call that creates it, or exceptions raised
        # during iteration (e.g. a missing API credential, which only
        # actually gets checked once the generator body runs) go
        # uncaught. This exact mistake here previously took down an
        # entire scheduled run - see this function's git history.
        try:
            for result in web_search.search(
                query, num_results=settings.web_search.results_per_query
            ):
                if is_excluded_domain(result.display_link or result.url):
                    continue
                haystack = f"{result.title}\n{result.snippet}"
                if item.color and mentions_conflicting_color(haystack, item.color):
                    continue
                if is_likely_non_item_listing(result.title, item) is not None:
                    continue

                db.add_registry_hit(
                    RegistryHit(
                        watched_item_id=item.id,
                        registry=WEB_SEARCH_REGISTRY_KEY,
                        url=result.url,
                        detail=f"{result.title} - {result.snippet[:150]}",
                    )
                )
        except Exception:
            logger.exception("Web search failed for item %s", item.id)
            continue


def _send_pending_alerts(
    db: Database, notifiers, items_by_id: dict[str, WatchedItem]
) -> None:
    # Only mark a match alerted once it's actually been delivered. With no
    # notifiers configured (e.g. Telegram not set up yet) or a notifier that
    # errors, matches must stay unalerted - otherwise they're lost forever
    # the moment alerting does get configured, instead of being sent then.
    for match in db.unalerted_matches():
        listing = db.get_listing(match.listing_id)
        item = items_by_id.get(match.watched_item_id)
        if listing is None or item is None:
            continue
        sent = False
        for notifier in notifiers:
            try:
                notifier.send(match, listing, item)
                sent = True
            except Exception:
                logger.exception("Failed to send alert for match %s", match.id)
        if sent:
            db.mark_alerted(match.id)


def _send_pending_registry_alerts(
    db: Database, notifiers, items_by_id: dict[str, WatchedItem]
) -> None:
    # Same deferred-delivery contract as _send_pending_alerts: a hit only
    # counts as alerted once a notifier actually sends it. registry_hits
    # covers both stolen_registries checkers (Lenstag, Stolen Camera
    # Finder) and reference-photo web-search results.
    for hit in db.unalerted_registry_hits():
        item = items_by_id.get(hit.watched_item_id)
        if item is None:
            continue
        sent = False
        for notifier in notifiers:
            try:
                notifier.send_registry_hit(hit, item)
                sent = True
            except Exception:
                logger.exception("Failed to send alert for registry hit %s", hit.id)
        if sent:
            db.mark_registry_hit_alerted(hit.id)
