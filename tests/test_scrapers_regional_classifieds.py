from datetime import UTC, datetime, timedelta

from stolen_gear_watch.core.config import ScraperSettings
from stolen_gear_watch.scrapers._regional_classifieds_platform import (
    RegionalClassifiedsAdapter,
)
from stolen_gear_watch.scrapers.merrjep_al import MerrjepAlAdapter
from stolen_gear_watch.scrapers.pazar3_mk import Pazar3MkAdapter

# Pure text parsing, no network/markup dependency - see
# CONTRIBUTING.md "Tests" for why adapters otherwise don't get one.
# Shared here since both site adapters use the same base class logic.


def make_adapter(cls: type[RegionalClassifiedsAdapter]):
    # respect_robots_txt=False keeps these hermetic - see the same pattern
    # in test_scrapers_ebay.py.
    return cls(ScraperSettings(enabled=True, rate_limit_seconds=0, respect_robots_txt=False))


def test_parses_price_with_space_thousands_and_currency():
    price, currency = RegionalClassifiedsAdapter._parse_price("42 000 МКД")
    assert price == 42000.0
    assert currency == "МКД"


def test_parses_price_no_thousands_separator():
    price, currency = RegionalClassifiedsAdapter._parse_price("700 EUR")
    assert price == 700.0
    assert currency == "EUR"


def test_empty_price_text_is_none():
    assert RegionalClassifiedsAdapter._parse_price("") == (None, None)


def test_unparseable_price_text_is_none():
    price, _currency = RegionalClassifiedsAdapter._parse_price("По договор")
    assert price is None


def test_pazar3_parses_today_and_yesterday():
    adapter = make_adapter(Pazar3MkAdapter)
    assert adapter._parse_posted_at("денес 12:00").date() == datetime.now(UTC).date()
    assert adapter._parse_posted_at("вчера 09:39").date() == (
        datetime.now(UTC) - timedelta(days=1)
    ).date()


def test_pazar3_parses_day_and_month_no_year_shown():
    adapter = make_adapter(Pazar3MkAdapter)
    # Computed rather than hardcoded so this doesn't break at year
    # rollover - same reasoning as test_scrapers_bazar_bg.py.
    target = datetime.now(UTC) - timedelta(days=60)
    month_name = next(
        name for name, num in Pazar3MkAdapter._month_abbrevs.items() if num == target.month
    )

    result = adapter._parse_posted_at(f"{target.day} {month_name}. 14:30")

    assert (result.year, result.month, result.day) == (target.year, target.month, target.day)


def test_pazar3_unrecognized_format_returns_none():
    adapter = make_adapter(Pazar3MkAdapter)
    assert adapter._parse_posted_at("some unexpected text") is None
    assert adapter._parse_posted_at("") is None


def test_merrjep_parses_today_and_yesterday():
    adapter = make_adapter(MerrjepAlAdapter)
    assert adapter._parse_posted_at("Sot 08:01").date() == datetime.now(UTC).date()
    assert adapter._parse_posted_at("Dje 12:49").date() == (
        datetime.now(UTC) - timedelta(days=1)
    ).date()


def test_merrjep_parses_day_and_month_no_year_shown():
    adapter = make_adapter(MerrjepAlAdapter)
    target = datetime.now(UTC) - timedelta(days=60)
    month_name = next(
        name for name, num in MerrjepAlAdapter._month_abbrevs.items() if num == target.month
    )

    result = adapter._parse_posted_at(f"{target.day} {month_name} 09:09")

    assert (result.year, result.month, result.day) == (target.year, target.month, target.day)


def test_merrjep_unrecognized_month_returns_none():
    adapter = make_adapter(MerrjepAlAdapter)
    assert adapter._parse_posted_at("14 notamonth 09:09") is None
