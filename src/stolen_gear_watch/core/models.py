"""Data model shared by every scraper, matcher, and notifier.

Nothing in here knows about a specific website or gear category - that's
what keeps the core reusable beyond cameras. Adapters translate
site-specific data into these types at the boundary.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field, field_validator


class WatchedItem(BaseModel):
    """One entry from the user's watched_items.yaml - the thing they lost."""

    id: str
    category: str = Field(description="e.g. camera_body, lens, bike, laptop")
    make: str
    model: str
    serial: str | None = Field(
        default=None,
        description="Exact serial number if known. Matched case-insensitively "
        "and with whitespace/dashes stripped.",
    )
    aliases: list[str] = Field(
        default_factory=list,
        description="Alternate names/model strings sellers might use "
        "(e.g. a colloquial nickname or a regional model code).",
    )
    keywords: list[str] = Field(
        default_factory=list,
        description="Extra terms to help scrapers narrow search queries "
        "(e.g. distinguishing marks, accessories bundled when stolen).",
    )
    description: str = ""
    reference_photos: list[str] = Field(
        default_factory=list,
        description="Local file paths to photos of the item, used as the "
        "query image for reverse image search.",
    )
    price_min: float | None = None
    price_max: float | None = None
    currency: str | None = None
    active: bool = True

    @field_validator("serial")
    @classmethod
    def _normalize_serial(cls, v: str | None) -> str | None:
        return normalize_serial(v) if v else v


def normalize_serial(serial: str) -> str:
    """Canonical form used for all serial comparisons: upper-case, no
    whitespace/dashes. Keeps matching robust to formatting differences
    between EXIF data, listing text, and how the owner wrote it down."""
    return "".join(serial.split()).replace("-", "").upper()


class RawListing(BaseModel):
    """What a scraper adapter hands back before it's been persisted."""

    source_site: str
    source_id: str = Field(description="Site-native listing id, used for dedup")
    url: str
    title: str
    description: str = ""
    price: float | None = None
    currency: str | None = None
    location: str | None = None
    posted_at: datetime | None = None
    photo_urls: list[str] = Field(default_factory=list)


class Listing(RawListing):
    """A RawListing once it has a database identity."""

    id: int
    first_seen_at: datetime
    last_seen_at: datetime


class MatchType(str, Enum):
    SERIAL = "serial"
    TEXT = "text"
    IMAGE = "image"
    REGISTRY = "registry"


class Match(BaseModel):
    id: int | None = None
    listing_id: int
    watched_item_id: str
    match_type: MatchType
    confidence: float = Field(ge=0.0, le=1.0)
    detail: str = ""
    created_at: datetime | None = None
    alerted_at: datetime | None = None


class RegistryHit(BaseModel):
    """Result of checking a watched item against an external stolen-gear
    registry (e.g. Lenstag), as opposed to a marketplace listing."""

    id: int | None = None
    watched_item_id: str
    registry: str
    url: str
    detail: str = ""
    checked_at: datetime | None = None
