"""Importing this package registers every built-in adapter. To add a new
site: write `your_site.py` implementing `Adapter` (see base.py), decorate
the class with `@register_adapter`, and add an import line below."""

from stolen_gear_watch.scrapers import (  # noqa: F401
    kleinanzeigen,
    kupujemprodajem,
    limundo,
    willhaben,
)
from stolen_gear_watch.scrapers.registry import available_site_keys, get_adapter

__all__ = ["available_site_keys", "get_adapter"]
