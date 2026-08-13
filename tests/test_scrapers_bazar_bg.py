from datetime import UTC, date, datetime, timedelta

from stolen_gear_watch.scrapers.bazar_bg import _MONTHS_BG, _parse_posted_at

# Pure text parsing, no network/markup dependency - see
# CONTRIBUTING.md "Tests" for why adapters otherwise don't get one.


def test_parses_today():
    assert _parse_posted_at("днес").date() == datetime.now(UTC).date()


def test_parses_yesterday():
    assert _parse_posted_at("вчера").date() == datetime.now(UTC).date() - timedelta(days=1)


def test_parses_day_and_month_no_year_shown():
    # See test_scrapers_publi24.py for why this uses a computed date
    # rather than a hardcoded month name.
    target = datetime.now(UTC) - timedelta(days=30)
    month_name = next(name for name, num in _MONTHS_BG.items() if num == target.month)

    result = _parse_posted_at(f"{target.day:02d} {month_name}")

    assert (result.year, result.month, result.day) == (target.year, target.month, target.day)


def test_parses_explicit_year():
    assert _parse_posted_at("12 октомври 2025г.").date() == date(2025, 10, 12)


def test_unrecognized_format_returns_none():
    assert _parse_posted_at("some unexpected text") is None
    assert _parse_posted_at("{{sort_date.date.long}}") is None  # seen live - unrendered template
