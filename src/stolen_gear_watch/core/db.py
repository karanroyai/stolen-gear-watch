"""Thin SQLite wrapper - deliberately not an ORM.

Stores every listing we've ever seen (for dedup), every match we've found,
external registry hits, and a log of each scraper run. Plain stdlib
sqlite3 keeps this dependency-free for a tool people self-host on a
Raspberry Pi or a cron box.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import Self

from stolen_gear_watch.core.models import Listing, Match, RawListing, RegistryHit

SCHEMA_PATH = Path(__file__).parent / "schema.sql"


def _now() -> str:
    return datetime.now(UTC).isoformat()


class Database:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(self.path)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA foreign_keys = ON")
        self._migrate()

    def _migrate(self) -> None:
        self._conn.executescript(SCHEMA_PATH.read_text())
        self._add_column_if_missing("registry_hits", "alerted_at", "TEXT")
        self._conn.executescript(
            """
            CREATE INDEX IF NOT EXISTS idx_matches_unalerted
                ON matches (alerted_at) WHERE alerted_at IS NULL;
            CREATE INDEX IF NOT EXISTS idx_registry_hits_unalerted
                ON registry_hits (alerted_at) WHERE alerted_at IS NULL;
            """
        )
        self._conn.commit()

    def _add_column_if_missing(self, table: str, column: str, sql_type: str) -> None:
        # CREATE TABLE IF NOT EXISTS in schema.sql doesn't touch columns on
        # a table that already exists from an earlier version of this
        # project - handle those additively so upgrading doesn't require
        # wiping an existing database.
        existing = {row["name"] for row in self._conn.execute(f"PRAGMA table_info({table})")}
        if column not in existing:
            self._conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {sql_type}")

    def close(self) -> None:
        self._conn.close()

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    # -- listings -----------------------------------------------------

    def upsert_listing(self, raw: RawListing) -> tuple[Listing, bool]:
        """Insert a listing if new, otherwise touch last_seen_at.

        Returns (listing, is_new).
        """
        now = _now()
        cur = self._conn.execute(
            "SELECT id, first_seen_at FROM listings WHERE source_site = ? AND source_id = ?",
            (raw.source_site, raw.source_id),
        )
        row = cur.fetchone()
        if row is not None:
            self._conn.execute(
                "UPDATE listings SET last_seen_at = ? WHERE id = ?", (now, row["id"])
            )
            self._conn.commit()
            listing = Listing(
                **raw.model_dump(), id=row["id"], first_seen_at=row["first_seen_at"], last_seen_at=now
            )
            return listing, False

        cur = self._conn.execute(
            """
            INSERT INTO listings
                (source_site, source_id, url, title, description, price, currency,
                 location, posted_at, photo_urls, first_seen_at, last_seen_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                raw.source_site,
                raw.source_id,
                raw.url,
                raw.title,
                raw.description,
                raw.price,
                raw.currency,
                raw.location,
                raw.posted_at.isoformat() if raw.posted_at else None,
                json.dumps(raw.photo_urls),
                now,
                now,
            ),
        )
        self._conn.commit()
        listing = Listing(**raw.model_dump(), id=cur.lastrowid, first_seen_at=now, last_seen_at=now)
        return listing, True

    # -- matches --------------------------------------------------------

    def add_match(self, match: Match) -> Match | None:
        """Insert a match if it doesn't already exist for this
        (listing, watched_item, match_type) triple. Returns None if it was
        a duplicate (already alerted or pending) so callers don't re-alert."""
        now = _now()
        try:
            cur = self._conn.execute(
                """
                INSERT INTO matches
                    (listing_id, watched_item_id, match_type, confidence, detail, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    match.listing_id,
                    match.watched_item_id,
                    match.match_type.value,
                    match.confidence,
                    match.detail,
                    now,
                ),
            )
        except sqlite3.IntegrityError:
            return None
        self._conn.commit()
        return match.model_copy(update={"id": cur.lastrowid, "created_at": now})

    def unalerted_matches(self) -> list[Match]:
        cur = self._conn.execute("SELECT * FROM matches WHERE alerted_at IS NULL")
        return [Match(**dict(row)) for row in cur.fetchall()]

    def mark_alerted(self, match_id: int) -> None:
        self._conn.execute(
            "UPDATE matches SET alerted_at = ? WHERE id = ?", (_now(), match_id)
        )
        self._conn.commit()

    def get_listing(self, listing_id: int) -> Listing | None:
        cur = self._conn.execute("SELECT * FROM listings WHERE id = ?", (listing_id,))
        row = cur.fetchone()
        if row is None:
            return None
        data = dict(row)
        data["photo_urls"] = json.loads(data["photo_urls"])
        return Listing(**data)

    # -- registry hits ----------------------------------------------------

    def add_registry_hit(self, hit: RegistryHit) -> RegistryHit | None:
        """Insert a registry hit if it's new for this (watched_item,
        registry, url) triple. Returns None if it was a duplicate, same
        dedup contract as add_match - callers should not alert on None."""
        now = _now()
        try:
            cur = self._conn.execute(
                """
                INSERT INTO registry_hits (watched_item_id, registry, url, detail, checked_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (hit.watched_item_id, hit.registry, hit.url, hit.detail, now),
            )
        except sqlite3.IntegrityError:
            return None
        self._conn.commit()
        return hit.model_copy(update={"id": cur.lastrowid, "checked_at": now})

    def unalerted_registry_hits(self) -> list[RegistryHit]:
        cur = self._conn.execute("SELECT * FROM registry_hits WHERE alerted_at IS NULL")
        return [RegistryHit(**dict(row)) for row in cur.fetchall()]

    def mark_registry_hit_alerted(self, hit_id: int) -> None:
        self._conn.execute(
            "UPDATE registry_hits SET alerted_at = ? WHERE id = ?", (_now(), hit_id)
        )
        self._conn.commit()

    # -- run log ------------------------------------------------------------

    def start_run(self, adapter: str) -> int:
        cur = self._conn.execute(
            "INSERT INTO run_log (adapter, started_at) VALUES (?, ?)", (adapter, _now())
        )
        self._conn.commit()
        return cur.lastrowid

    def finish_run(
        self, run_id: int, listings_found: int, new_listings: int, error: str | None = None
    ) -> None:
        self._conn.execute(
            """
            UPDATE run_log
            SET finished_at = ?, listings_found = ?, new_listings = ?, error = ?
            WHERE id = ?
            """,
            (_now(), listings_found, new_listings, error, run_id),
        )
        self._conn.commit()
