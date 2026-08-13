-- SQLite schema for stolen-gear-watch.
-- Applied once at startup by core/db.py; schema_version tracks what's applied
-- so future migrations can be added without wiping existing data.
--
-- Only CREATE TABLE goes here. Indexes are created separately in db.py,
-- after any ALTER TABLE column migrations run - an index on a column that
-- doesn't exist yet on an older database would fail before the migration
-- had a chance to add it.

CREATE TABLE IF NOT EXISTS schema_version (
    version INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS listings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_site TEXT NOT NULL,
    source_id TEXT NOT NULL,
    url TEXT NOT NULL,
    title TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    price REAL,
    currency TEXT,
    location TEXT,
    posted_at TEXT,
    photo_urls TEXT NOT NULL DEFAULT '[]',
    first_seen_at TEXT NOT NULL,
    last_seen_at TEXT NOT NULL,
    UNIQUE (source_site, source_id)
);

CREATE TABLE IF NOT EXISTS matches (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    listing_id INTEGER NOT NULL REFERENCES listings (id),
    watched_item_id TEXT NOT NULL,
    match_type TEXT NOT NULL,
    confidence REAL NOT NULL,
    detail TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    alerted_at TEXT,
    UNIQUE (listing_id, watched_item_id, match_type)
);

CREATE TABLE IF NOT EXISTS registry_hits (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    watched_item_id TEXT NOT NULL,
    registry TEXT NOT NULL,
    url TEXT NOT NULL,
    detail TEXT NOT NULL DEFAULT '',
    checked_at TEXT NOT NULL,
    alerted_at TEXT,
    UNIQUE (watched_item_id, registry, url)
);

CREATE TABLE IF NOT EXISTS run_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    adapter TEXT NOT NULL,
    started_at TEXT NOT NULL,
    finished_at TEXT,
    listings_found INTEGER NOT NULL DEFAULT 0,
    new_listings INTEGER NOT NULL DEFAULT 0,
    error TEXT
);
