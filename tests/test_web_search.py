from stolen_gear_watch.core.config import WebSearchSettings
from stolen_gear_watch.web_search import get_web_search
from stolen_gear_watch.web_search.google_custom_search import is_excluded_domain


def test_is_excluded_domain_matches_known_retailer():
    assert is_excluded_domain("https://www.amazon.de/some-camera") is True
    assert is_excluded_domain("bhphotovideo.com") is True


def test_is_excluded_domain_false_for_unrelated_site():
    assert is_excluded_domain("https://www.kleinanzeigen.de/s-anzeige/123") is False


def test_get_web_search_none_by_default():
    assert get_web_search(WebSearchSettings()) is None


def test_get_web_search_none_for_unknown_backend():
    assert get_web_search(WebSearchSettings(backend="something-else")) is None
