from datetime import UTC, date, datetime, timedelta

from stolen_gear_watch.scrapers.kleinanzeigen import _parse_posted_at

# _parse_posted_at is pure text parsing (no network/markup dependency),
# unlike the rest of this adapter - worth testing on its own, see
# CONTRIBUTING.md "Tests" for why adapters otherwise don't get one.


def test_parses_today():
    assert _parse_posted_at("Heute, 18:12").date() == datetime.now(UTC).date()


def test_parses_yesterday():
    assert _parse_posted_at("Gestern, 11:34").date() == datetime.now(UTC).date() - timedelta(
        days=1
    )


def test_parses_absolute_date():
    assert _parse_posted_at("09.08.2026").date() == date(2026, 8, 9)


def test_unrecognized_format_returns_none():
    assert _parse_posted_at("some unexpected text") is None
