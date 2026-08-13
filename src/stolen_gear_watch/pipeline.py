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
from stolen_gear_watch.matching.ocr import get_ocr
from stolen_gear_watch.matching.serial import serial_match_confidence
from stolen_gear_watch.matching.text import text_match_confidence
from stolen_gear_watch.net import RobotsDisallowedError
from stolen_gear_watch.reverse_image import get_backend

REFERENCE_PHOTO_SEARCH_REGISTRY_KEY = "reverse_image_web_search"

logger = logging.getLogger(__name__)


def run(settings: Settings, watched_items: list[WatchedItem], db: Database) -> None:
    active_items = [item for item in watched_items if item.active]
    if not active_items:
        logger.warning("No active watched items - nothing to do")
        return

    notifiers = get_notifiers(settings)
    image_backend = get_backend(settings.reverse_image)
    ocr = get_ocr(settings.reverse_image)

    items_by_id = {item.id: item for item in active_items}

    _run_scrapers(settings, active_items, db, image_backend, ocr)
    _run_registry_checks(settings, active_items, db)
    _run_reference_photo_search(settings, active_items, db, image_backend)
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
            try:
                results = image_backend.search(photo_url)
            except Exception:
                logger.exception("Reverse image search failed for %s", photo_url)
                continue
            for result in results:
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
            try:
                results = image_backend.search(photo_path)
            except Exception:
                logger.exception(
                    "Reference photo search failed for %s (item %s)", photo_path, item.id
                )
                continue
            for result in results:
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
