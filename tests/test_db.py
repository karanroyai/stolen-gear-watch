from stolen_gear_watch.core.db import Database
from stolen_gear_watch.core.models import Match, MatchType, RawListing, RegistryHit


def make_raw_listing(**overrides):
    defaults = {
        "source_site": "testsite",
        "source_id": "123",
        "url": "https://example.com/123",
        "title": "Canon EOS R5",
    }
    defaults.update(overrides)
    return RawListing(**defaults)


def test_upsert_listing_dedups_by_source_id(tmp_path):
    with Database(tmp_path / "test.db") as db:
        listing1, is_new1 = db.upsert_listing(make_raw_listing())
        listing2, is_new2 = db.upsert_listing(make_raw_listing())

        assert is_new1 is True
        assert is_new2 is False
        assert listing1.id == listing2.id


def test_add_match_rejects_duplicates(tmp_path):
    with Database(tmp_path / "test.db") as db:
        listing, _ = db.upsert_listing(make_raw_listing())
        match = Match(
            listing_id=listing.id,
            watched_item_id="my-item",
            match_type=MatchType.SERIAL,
            confidence=1.0,
        )

        first = db.add_match(match)
        second = db.add_match(match)

        assert first is not None
        assert second is None  # duplicate, already recorded


def test_unalerted_matches_and_mark_alerted(tmp_path):
    with Database(tmp_path / "test.db") as db:
        listing, _ = db.upsert_listing(make_raw_listing())
        saved = db.add_match(
            Match(
                listing_id=listing.id,
                watched_item_id="my-item",
                match_type=MatchType.TEXT,
                confidence=0.9,
            )
        )

        assert len(db.unalerted_matches()) == 1
        db.mark_alerted(saved.id)
        assert len(db.unalerted_matches()) == 0


def test_add_registry_hit_dedups(tmp_path):
    with Database(tmp_path / "test.db") as db:
        hit = RegistryHit(
            watched_item_id="my-item", registry="lenstag", url="https://lenstag.com/x"
        )
        first = db.add_registry_hit(hit)
        second = db.add_registry_hit(hit)

        assert first is not None
        assert second is None
