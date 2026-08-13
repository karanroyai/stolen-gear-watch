import time

import pytest
import responses

from stolen_gear_watch.core.config import ScraperSettings
from stolen_gear_watch.scrapers.ebay import _TOKEN_URL, EbayAdapter

# Only the deterministic parts get tested here (token caching, JSON
# parsing) - not a live search, since this adapter was built without
# credentials to verify a real response against. See the module
# docstring in scrapers/ebay.py.


def make_adapter():
    # respect_robots_txt=False here purely to keep these tests hermetic -
    # it skips the constructor's robots.txt fetch (api.ebay.com has none,
    # a 404, which _load_robots already handles fine live; this just
    # avoids a real network call in unit tests of unrelated logic).
    return EbayAdapter(
        ScraperSettings(enabled=True, rate_limit_seconds=0, respect_robots_txt=False)
    )


@pytest.fixture(autouse=True)
def ebay_credentials(monkeypatch):
    monkeypatch.setenv("EBAY_CLIENT_ID", "test-client-id")
    monkeypatch.setenv("EBAY_CLIENT_SECRET", "test-client-secret")


@responses.activate
def test_access_token_is_cached_across_calls():
    responses.add(
        responses.POST, _TOKEN_URL, json={"access_token": "tok-1", "expires_in": 7200}
    )
    adapter = make_adapter()

    first = adapter._get_access_token()
    second = adapter._get_access_token()

    assert first == second == "tok-1"
    assert len(responses.calls) == 1  # second call used the cache, no new HTTP request


@responses.activate
def test_access_token_is_refetched_once_expired():
    responses.add(
        responses.POST, _TOKEN_URL, json={"access_token": "tok-1", "expires_in": 7200}
    )
    adapter = make_adapter()
    adapter._get_access_token()
    adapter._token_expires_at = time.monotonic() - 1  # force expiry

    responses.add(
        responses.POST, _TOKEN_URL, json={"access_token": "tok-2", "expires_in": 7200}
    )
    second = adapter._get_access_token()

    assert second == "tok-2"
    assert len(responses.calls) == 2


def test_missing_credentials_raises_clearly(monkeypatch):
    monkeypatch.delenv("EBAY_CLIENT_ID", raising=False)
    monkeypatch.delenv("EBAY_CLIENT_SECRET", raising=False)
    adapter = make_adapter()

    with pytest.raises(RuntimeError, match="EBAY_CLIENT_ID"):
        adapter._get_access_token()


def test_parse_item_builds_raw_listing():
    adapter = make_adapter()
    summary = {
        "itemId": "v1|123456789|0",
        "itemWebUrl": "https://www.ebay.de/itm/123456789",
        "title": "Fujifilm X100VI Silber",
        "price": {"value": "1500.00", "currency": "EUR"},
        "itemLocation": {"city": "Wien", "country": "AT"},
        "image": {"imageUrl": "https://i.ebayimg.com/main.jpg"},
        "additionalImages": [{"imageUrl": "https://i.ebayimg.com/extra.jpg"}],
    }

    listing = adapter._parse_item(summary)

    assert listing.source_id == "v1|123456789|0"
    assert listing.title == "Fujifilm X100VI Silber"
    assert listing.price == 1500.0
    assert listing.currency == "EUR"
    assert listing.location == "Wien, AT"
    assert listing.photo_urls == [
        "https://i.ebayimg.com/main.jpg",
        "https://i.ebayimg.com/extra.jpg",
    ]
    assert listing.posted_at is None  # no date field in this fixture - degrades gracefully


def test_parse_item_missing_required_fields_returns_none():
    adapter = make_adapter()
    assert adapter._parse_item({"title": "no id or url"}) is None
