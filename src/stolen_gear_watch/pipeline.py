"""Orchestrates one end-to-end run: scrape configured marketplaces for
each active watched item, match new listings, check stolen registries,
and alert on anything new. Invoked once per `stolen-gear-watch run` -
this module has no loop or scheduler of its own; that's cron/systemd's
job (see README "Running on a schedule").
"""

from __future__ import annotations

import logging

from stolen_gear_watch import scrapers, stolen_registries
from stolen_gear_watch.alerting import get_notifiers
from stolen_gear_watch.core.config import Settings
from stolen_gear_watch.core.db import Database
from stolen_gear_watch.core.models import Listing, Match, MatchType, WatchedItem
from stolen_gear_watch.matching.serial import serial_match_confidence
from stolen_gear_watch.matching.text import text_match_confidence
from stolen_gear_watch.net import RobotsDisallowedError
from stolen_gear_watch.reverse_image import get_backend

logger = logging.getLogger(__name__)


def run(settings: Settings, watched_items: list[WatchedItem], db: Database) -> None:
    active_items = [item for item in watched_items if item.active]
    if not active_items:
        logger.warning("No active watched items - nothing to do")
        return

    notifiers = get_notifiers(settings)
    image_backend = get_backend(settings.reverse_image)

    items_by_id = {item.id: item for item in active_items}

    _run_scrapers(settings, active_items, db, image_backend)
    _run_registry_checks(settings, active_items, db, notifiers)
    _send_pending_alerts(db, notifiers, items_by_id)


def _run_scrapers(settings, active_items, db, image_backend) -> None:
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
                    _evaluate_listing(listing, item, settings, db, image_backend)
            except RobotsDisallowedError as exc:
                logger.warning("Stopped scraping %s: %s", site_key, exc)
                error = str(exc)
            except Exception as exc:
                logger.exception("Adapter %s failed for item %s", site_key, item.id)
                error = str(exc)
            finally:
                db.finish_run(run_id, listings_found, new_listings, error)


def _evaluate_listing(
    listing: Listing, item: WatchedItem, settings: Settings, db: Database, image_backend
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


def _run_registry_checks(settings: Settings, active_items, db: Database, notifiers) -> None:
    for registry_key in settings.stolen_registries.enabled:
        checker = stolen_registries.REGISTRIES.get(registry_key)
        if checker is None:
            logger.warning("No registry checker registered for %r, skipping", registry_key)
            continue
        for item in active_items:
            try:
                for hit in checker.check(item):
                    saved = db.add_registry_hit(hit)
                    if saved is None:
                        continue  # already recorded, don't re-alert
                    for notifier in notifiers:
                        notifier.send_registry_hit(saved, item)
            except Exception:
                logger.exception("Registry checker %s failed for item %s", registry_key, item.id)


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
