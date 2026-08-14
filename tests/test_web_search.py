from stolen_gear_watch.core.config import WebSearchSettings
from stolen_gear_watch.web_search import get_web_search
from stolen_gear_watch.web_search.google_custom_search import _RECOMMENDED_DOMAINS


def test_recommended_domains_within_google_limit():
    # Google caps a Programmable Search Engine's "Sites to search" at 50
    # domains for engines created after the Jan 2026 policy change (see
    # module docstring) - this list has to actually fit.
    assert len(_RECOMMENDED_DOMAINS) <= 50


def test_recommended_domains_has_no_duplicates():
    assert len(_RECOMMENDED_DOMAINS) == len(set(_RECOMMENDED_DOMAINS))


def test_get_web_search_none_by_default():
    assert get_web_search(WebSearchSettings()) is None


def test_get_web_search_none_for_unknown_backend():
    assert get_web_search(WebSearchSettings(backend="something-else")) is None
