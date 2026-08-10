"""Adapter registration. Site modules register themselves with
`@register_adapter` on import; `scrapers/__init__.py` imports every known
site module so this registry is fully populated as soon as the package is
imported. To add a new site: write the adapter class, decorate it, and add
one import line to `scrapers/__init__.py`.
"""

from __future__ import annotations

from stolen_gear_watch.scrapers.base import Adapter

_ADAPTERS: dict[str, type[Adapter]] = {}


def register_adapter(cls: type[Adapter]) -> type[Adapter]:
    _ADAPTERS[cls.site_key] = cls
    return cls


def get_adapter(site_key: str) -> type[Adapter]:
    try:
        return _ADAPTERS[site_key]
    except KeyError:
        available = ", ".join(sorted(_ADAPTERS)) or "(none registered)"
        raise KeyError(f"No adapter registered for {site_key!r}. Available: {available}") from None


def available_site_keys() -> list[str]:
    return sorted(_ADAPTERS)
