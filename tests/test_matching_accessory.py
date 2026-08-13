from stolen_gear_watch.core.models import WatchedItem
from stolen_gear_watch.matching.accessory import is_likely_non_item_listing


def make_item(**overrides):
    defaults = {"id": "test-item", "category": "camera_body", "make": "Fujifilm", "model": "X100VI"}
    defaults.update(overrides)
    return WatchedItem(**defaults)


def test_accessory_before_model_is_filtered():
    item = make_item()
    assert is_likely_non_item_listing("SmallRigg Half Case für Fujifilm X100VI", item) is not None


def test_accessory_word_after_model_is_kept():
    # Real example: the item itself, with a bundled/mentioned accessory -
    # must NOT be filtered just because "Filter" appears somewhere.
    item = make_item()
    reason = is_likely_non_item_listing(
        "Neuer PreisFujifilm X100VI silver + Black Mist & UV Filter", item
    )
    assert reason is None


def test_plain_camera_listing_is_kept():
    item = make_item()
    assert is_likely_non_item_listing("Fujifilm X100VI - Top Zustand", item) is None


def test_book_title_is_filtered_even_with_model_leading():
    item = make_item()
    reason = is_likely_non_item_listing(
        "Fujifilm X100VI - Das Handbuch zur Kamera (Rheinwerk)", item
    )
    assert reason is not None


def test_rental_listing_is_filtered_regardless_of_position():
    item = make_item()
    assert is_likely_non_item_listing("Fujifilm X100VI Kamera mieten", item) is not None


def test_want_ad_is_filtered():
    item = make_item()
    assert is_likely_non_item_listing("Suche eine fujifilm x100VI", item) is not None


def test_bundled_accessory_in_title_is_kept():
    # Real example: the camera itself, described with a bundle name that
    # happens to contain "paket" but no actual accessory keyword before it.
    item = make_item()
    reason = is_likely_non_item_listing(
        "Fujifilm X100VI Schwarz - inkl. Zubehörpaket", item
    )
    assert reason is None
