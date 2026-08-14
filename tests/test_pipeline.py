from datetime import UTC, datetime

from stolen_gear_watch.core.config import Settings
from stolen_gear_watch.core.db import Database
from stolen_gear_watch.core.models import Match, MatchType, RawListing, RegistryHit, WatchedItem
from stolen_gear_watch.pipeline import (
    _evaluate_listing,
    _run_web_search,
    _send_pending_alerts,
    _send_pending_registry_alerts,
)
from stolen_gear_watch.web_search.google_custom_search import WebSearchResult


def make_item(item_id="my-item"):
    return WatchedItem(id=item_id, category="camera_body", make="Canon", model="EOS R5")


def seed_match(db, watched_item_id="my-item"):
    listing, _ = db.upsert_listing(
        RawListing(
            source_site="testsite", source_id="1", url="https://example.com/1", title="Canon EOS R5"
        )
    )
    return db.add_match(
        Match(
            listing_id=listing.id,
            watched_item_id=watched_item_id,
            match_type=MatchType.TEXT,
            confidence=1.0,
        )
    )


def test_no_notifiers_leaves_match_unalerted(tmp_path):
    """Regression test: a match found while alerting isn't configured yet
    (e.g. no Telegram bot token) must stay unalerted, so it gets delivered
    once a notifier is added - not silently marked as sent for nothing."""
    with Database(tmp_path / "test.db") as db:
        seed_match(db)

        _send_pending_alerts(db, notifiers=[], items_by_id={"my-item": make_item()})

        assert len(db.unalerted_matches()) == 1


def test_failing_notifier_leaves_match_unalerted(tmp_path):
    class _FailingNotifier:
        def send(self, match, listing, item):
            raise RuntimeError("boom")

    with Database(tmp_path / "test.db") as db:
        seed_match(db)

        _send_pending_alerts(
            db, notifiers=[_FailingNotifier()], items_by_id={"my-item": make_item()}
        )

        assert len(db.unalerted_matches()) == 1


def test_successful_notifier_marks_match_alerted(tmp_path):
    sent = []

    class _RecordingNotifier:
        def send(self, match, listing, item):
            sent.append(match.id)

    with Database(tmp_path / "test.db") as db:
        seed_match(db)

        _send_pending_alerts(
            db, notifiers=[_RecordingNotifier()], items_by_id={"my-item": make_item()}
        )

        assert len(db.unalerted_matches()) == 0
        assert len(sent) == 1


def seed_registry_hit(db, watched_item_id="my-item"):
    return db.add_registry_hit(
        RegistryHit(watched_item_id=watched_item_id, registry="lenstag", url="https://lenstag.com/x")
    )


def test_no_notifiers_leaves_registry_hit_unalerted(tmp_path):
    """Same regression as matches: a registry hit found before alerting is
    configured must stay unalerted so it's delivered once a notifier
    exists, not lost the moment it's first seen."""
    with Database(tmp_path / "test.db") as db:
        seed_registry_hit(db)

        _send_pending_registry_alerts(db, notifiers=[], items_by_id={"my-item": make_item()})

        assert len(db.unalerted_registry_hits()) == 1


def test_successful_notifier_marks_registry_hit_alerted(tmp_path):
    sent = []

    class _RecordingNotifier:
        def send_registry_hit(self, hit, item):
            sent.append(hit.id)

    with Database(tmp_path / "test.db") as db:
        seed_registry_hit(db)

        _send_pending_registry_alerts(
            db, notifiers=[_RecordingNotifier()], items_by_id={"my-item": make_item()}
        )

        assert len(db.unalerted_registry_hits()) == 0
        assert len(sent) == 1


def test_listing_posted_before_theft_date_is_skipped(tmp_path):
    with Database(tmp_path / "test.db") as db:
        item = WatchedItem(
            id="my-item",
            category="camera_body",
            make="Canon",
            model="EOS R5",
            stolen_at=datetime(2026, 6, 1, tzinfo=UTC),
        )
        listing, _ = db.upsert_listing(
            RawListing(
                source_site="testsite",
                source_id="1",
                url="https://example.com/1",
                title="Canon EOS R5",
                posted_at=datetime(2026, 5, 1, tzinfo=UTC),  # before the theft date
            )
        )

        _evaluate_listing(listing, item, Settings(), db, image_backend=None, ocr=None)

        assert db.unalerted_matches() == []


def test_listing_posted_after_theft_date_is_evaluated_normally(tmp_path):
    with Database(tmp_path / "test.db") as db:
        item = WatchedItem(
            id="my-item",
            category="camera_body",
            make="Canon",
            model="EOS R5",
            stolen_at=datetime(2026, 6, 1, tzinfo=UTC),
        )
        listing, _ = db.upsert_listing(
            RawListing(
                source_site="testsite",
                source_id="1",
                url="https://example.com/1",
                title="Canon EOS R5",
                posted_at=datetime(2026, 6, 15, tzinfo=UTC),  # after the theft date
            )
        )

        _evaluate_listing(listing, item, Settings(), db, image_backend=None, ocr=None)

        assert len(db.unalerted_matches()) == 1


class _FakeWebSearch:
    def __init__(self, results):
        self._results = results

    def search(self, query, num_results=10):
        return self._results


def test_web_search_none_backend_is_noop(tmp_path):
    with Database(tmp_path / "test.db") as db:
        _run_web_search(Settings(), [make_item()], db, web_search=None)
        assert db.unalerted_registry_hits() == []


def test_web_search_excludes_retailer_domain(tmp_path):
    with Database(tmp_path / "test.db") as db:
        fake = _FakeWebSearch(
            [
                WebSearchResult(
                    title="Canon EOS R5",
                    url="https://www.amazon.de/canon-eos-r5",
                    display_link="www.amazon.de",
                )
            ]
        )
        _run_web_search(Settings(), [make_item()], db, web_search=fake)
        assert db.unalerted_registry_hits() == []


def test_web_search_excludes_accessory_result(tmp_path):
    with Database(tmp_path / "test.db") as db:
        fake = _FakeWebSearch(
            [WebSearchResult(title="Case für Canon EOS R5", url="https://example.com/case")]
        )
        _run_web_search(Settings(), [make_item()], db, web_search=fake)
        assert db.unalerted_registry_hits() == []


def test_web_search_keeps_genuine_result(tmp_path):
    with Database(tmp_path / "test.db") as db:
        fake = _FakeWebSearch(
            [
                WebSearchResult(
                    title="Canon EOS R5 for sale",
                    url="https://example.com/listing/1",
                    snippet="Selling my Canon EOS R5, great condition",
                    display_link="example.com",
                )
            ]
        )
        _run_web_search(Settings(), [make_item()], db, web_search=fake)
        hits = db.unalerted_registry_hits()
        assert len(hits) == 1
        assert hits[0].registry == "web_search"


def test_listing_with_conflicting_color_is_skipped(tmp_path):
    with Database(tmp_path / "test.db") as db:
        item = WatchedItem(
            id="my-item", category="camera_body", make="Canon", model="EOS R5", color="silver"
        )
        listing, _ = db.upsert_listing(
            RawListing(
                source_site="testsite",
                source_id="1",
                url="https://example.com/1",
                title="Canon EOS R5 Schwarz",
            )
        )

        _evaluate_listing(listing, item, Settings(), db, image_backend=None, ocr=None)

        assert db.unalerted_matches() == []
