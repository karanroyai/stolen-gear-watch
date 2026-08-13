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


def test_unalerted_registry_hits_and_mark_alerted(tmp_path):
    with Database(tmp_path / "test.db") as db:
        saved = db.add_registry_hit(
            RegistryHit(watched_item_id="my-item", registry="lenstag", url="https://lenstag.com/x")
        )

        assert len(db.unalerted_registry_hits()) == 1
        db.mark_registry_hit_alerted(saved.id)
        assert len(db.unalerted_registry_hits()) == 0


def test_existing_database_gains_registry_hits_alerted_at_column(tmp_path):
    """Regression test: registry_hits.alerted_at was added after the table
    already existed in shipped databases - CREATE TABLE IF NOT EXISTS alone
    doesn't add columns to an already-existing table, so opening an old
    database must not crash and must still support the new column."""
    import sqlite3

    db_path = tmp_path / "old.db"
    conn = sqlite3.connect(db_path)
    conn.execute(
        """
        CREATE TABLE registry_hits (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            watched_item_id TEXT NOT NULL,
            registry TEXT NOT NULL,
            url TEXT NOT NULL,
            detail TEXT NOT NULL DEFAULT '',
            checked_at TEXT NOT NULL,
            UNIQUE (watched_item_id, registry, url)
        )
        """
    )
    conn.commit()
    conn.close()

    with Database(db_path) as db:
        saved = db.add_registry_hit(
            RegistryHit(watched_item_id="my-item", registry="lenstag", url="https://lenstag.com/x")
        )
        assert saved is not None
        assert len(db.unalerted_registry_hits()) == 1
