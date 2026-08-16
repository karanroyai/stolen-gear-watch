"""Importing this package registers every built-in adapter. To add a new
site: write `your_site.py` implementing `Adapter` (see base.py), decorate
the class with `@register_adapter`, and add an import line below."""

from stolen_gear_watch.scrapers import (  # noqa: F401
    bazar_bg,
    ebay,
    kleinanzeigen,
    kupujemprodajem,
    limundo,
    merrjep_al,
    pazar3_mk,
    publi24,
    willhaben,
)
from stolen_gear_watch.scrapers.registry import available_site_keys, get_adapter

__all__ = ["available_site_keys", "get_adapter"]
