from datetime import UTC, datetime, timedelta

from stolen_gear_watch.scrapers.publi24 import _MONTHS_RO, _parse_posted_at

# Pure text parsing, no network/markup dependency - see
# CONTRIBUTING.md "Tests" for why adapters otherwise don't get one.


def test_parses_today():
    assert _parse_posted_at("azi 18:09").date() == datetime.now(UTC).date()


def test_parses_yesterday():
    assert _parse_posted_at("ieri 13:37").date() == datetime.now(UTC).date() - timedelta(days=1)


def test_parses_day_and_month_no_year_shown():
    # A month with no year shown always means "the most recent occurrence
    # of this day/month, not in the future" - use a fixed date 30 days
    # ago (always unambiguous, always in the past) rather than a
    # hardcoded month name that could be in the future depending on
    # which day tests actually run, which would flip the expected year.
    target = datetime.now(UTC) - timedelta(days=30)
    month_name = next(name for name, num in _MONTHS_RO.items() if num == target.month)

    result = _parse_posted_at(f"{target.day} {month_name}")

    assert (result.year, result.month, result.day) == (target.year, target.month, target.day)


def test_unrecognized_format_returns_none():
    assert _parse_posted_at("some unexpected text") is None
