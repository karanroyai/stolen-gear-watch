"""Loads and validates the two config files the user maintains:

- settings.yaml: which adapters/backends are enabled, rate limits, etc.
  Safe to commit - contains no personal data.
- watched_items.yaml: the actual stolen item(s). Real file is gitignored;
  only watched_items.example.yaml ships in the repo.

Secrets (API keys, bot tokens) never live in these YAML files - they're
read from the environment (populated from .env via load_dotenv).
"""

from __future__ import annotations

import os
from pathlib import Path

import yaml
from dotenv import load_dotenv
from pydantic import BaseModel, Field

from stolen_gear_watch.core.models import WatchedItem


class ScraperSettings(BaseModel):
    enabled: bool = True
    rate_limit_seconds: float = Field(
        default=3.0, description="Minimum delay between requests to this site."
    )
    max_pages: int = 5
    respect_robots_txt: bool = Field(
        default=True,
        description="Leave this on unless you've deliberately decided otherwise for a "
        "specific site. Turning it off does not mean the site allows scraping - it means "
        "you're choosing to proceed against whatever its robots.txt says, at your own "
        "risk. See README 'Scraping ethics'.",
    )


class ReverseImageSettings(BaseModel):
    backend: str = Field(
        default="manual",
        description="manual (default, no API key needed) | google_vision | tineye",
    )
    min_confidence: float = 0.75


class TelegramSettings(BaseModel):
    enabled: bool = True


class AlertingSettings(BaseModel):
    telegram: TelegramSettings = TelegramSettings()


class StolenRegistrySettings(BaseModel):
    enabled: list[str] = Field(default_factory=lambda: ["lenstag"])


class Settings(BaseModel):
    db_path: str = "data/stolen_gear_watch.db"
    log_level: str = "INFO"
    log_format: str = Field(default="json", description="json | text")
    match_confidence_threshold: float = 0.6
    scraper_contact_email: str | None = None
    scrapers: dict[str, ScraperSettings] = Field(default_factory=dict)
    reverse_image: ReverseImageSettings = ReverseImageSettings()
    alerting: AlertingSettings = AlertingSettings()
    stolen_registries: StolenRegistrySettings = StolenRegistrySettings()


def load_env(env_path: Path | str | None = None) -> None:
    """Populate os.environ from a .env file. Safe to call multiple times."""
    load_dotenv(dotenv_path=env_path, override=False)


def require_env(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise RuntimeError(
            f"Required environment variable {name!r} is not set. "
            f"Copy .env.example to .env and fill it in."
        )
    return value


def load_settings(path: Path | str) -> Settings:
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(
            f"Settings file not found: {path}. "
            f"Copy config/settings.example.yaml to config/settings.yaml to start."
        )
    raw = yaml.safe_load(path.read_text()) or {}
    return Settings.model_validate(raw)


def load_watched_items(path: Path | str) -> list[WatchedItem]:
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(
            f"Watched items file not found: {path}. "
            f"Copy config/watched_items.example.yaml to config/watched_items.yaml "
            f"and fill in your item - keep that file out of version control."
        )
    raw = yaml.safe_load(path.read_text()) or {}
    items = raw.get("watched_items", [])
    return [WatchedItem.model_validate(item) for item in items]
