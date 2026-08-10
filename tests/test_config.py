import pytest

from stolen_gear_watch.core.config import load_settings, load_watched_items


def test_load_settings_from_example():
    settings = load_settings("config/settings.example.yaml")
    assert settings.scrapers["willhaben"].enabled is True
    assert settings.reverse_image.backend == "manual"


def test_load_watched_items_from_example():
    items = load_watched_items("config/watched_items.example.yaml")
    assert len(items) == 2
    assert items[0].make == "Canon"
    assert items[0].serial == "123456789012"


def test_missing_settings_file_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        load_settings(tmp_path / "does-not-exist.yaml")
