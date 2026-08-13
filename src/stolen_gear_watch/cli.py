"""Command-line entrypoint. Installed as the `stolen-gear-watch` script
(see pyproject.toml `[project.scripts]`)."""

from __future__ import annotations

import shutil
from pathlib import Path

import typer

from stolen_gear_watch import pipeline, stolen_registries
from stolen_gear_watch.core.config import load_env, load_settings, load_watched_items
from stolen_gear_watch.core.db import Database
from stolen_gear_watch.core.logging_setup import configure_logging
from stolen_gear_watch.core.models import WatchedItem
from stolen_gear_watch.matching.exif import extract_serial

app = typer.Typer(help="Watch marketplaces and stolen-gear registries for items reported stolen.")

_DEFAULT_SETTINGS = Path("config/settings.yaml")
_DEFAULT_WATCHED_ITEMS = Path("config/watched_items.yaml")
_DEFAULT_ENV = Path(".env")


@app.command()
def run(
    settings_path: Path = typer.Option(_DEFAULT_SETTINGS, "--settings"),
    watched_items_path: Path = typer.Option(_DEFAULT_WATCHED_ITEMS, "--watched-items"),
    env_path: Path = typer.Option(_DEFAULT_ENV, "--env"),
) -> None:
    """Run one full pass: scrape configured marketplaces, check stolen
    registries, alert on anything new. Intended to be invoked by cron or a
    systemd timer, not run as a persistent loop."""
    load_env(env_path if env_path.exists() else None)
    settings = load_settings(settings_path)
    configure_logging(settings.log_level, settings.log_format)
    watched_items = load_watched_items(watched_items_path)

    with Database(settings.db_path) as db:
        pipeline.run(settings, watched_items, db)


@app.command("check-serial")
def check_serial(
    serial: str = typer.Argument(..., help="Serial number to check"),
    make: str = typer.Option(..., help="e.g. Canon"),
    model: str = typer.Option(..., help="e.g. EOS R5"),
    settings_path: Path = typer.Option(_DEFAULT_SETTINGS, "--settings"),
    env_path: Path = typer.Option(_DEFAULT_ENV, "--env"),
) -> None:
    """One-off lookup: check a serial (e.g. before buying used gear)
    against the configured stolen-gear registries. Does not touch
    marketplace scrapers or the database - prints results directly."""
    load_env(env_path if env_path.exists() else None)
    settings = load_settings(settings_path)
    configure_logging(settings.log_level, settings.log_format)

    candidate = WatchedItem(id="cli-check", category="camera_body", make=make, model=model, serial=serial)

    found_any = False
    for registry_key in settings.stolen_registries.enabled:
        checker = stolen_registries.REGISTRIES.get(registry_key)
        if checker is None:
            typer.echo(f"[skip] no checker registered for {registry_key!r}")
            continue
        for hit in checker.check(candidate):
            found_any = True
            typer.secho(f"[{hit.registry}] {hit.detail}\n  {hit.url}", fg=typer.colors.RED)

    if not found_any:
        typer.secho(
            "No automated hits. Some registries (e.g. Stolen Camera Finder) can't be "
            "checked automatically - see the log output above for manual-check links.",
            fg=typer.colors.YELLOW,
        )


@app.command("check-exif")
def check_exif(
    photo_paths: list[Path] = typer.Argument(..., help="One or more photo files to inspect"),
) -> None:
    """Extract a serial number from photo EXIF metadata, e.g. to check
    what your camera actually writes before putting a serial in
    watched_items.yaml. Uses exiftool if it's installed (much better
    vendor MakerNote coverage), otherwise falls back to Pillow."""
    for path in photo_paths:
        if not path.exists():
            typer.secho(f"[skip] {path} does not exist", fg=typer.colors.YELLOW)
            continue
        serial = extract_serial(path)
        if serial:
            typer.secho(f"{path}: {serial}", fg=typer.colors.GREEN)
        else:
            typer.secho(f"{path}: no serial found", fg=typer.colors.YELLOW)


@app.command()
def init() -> None:
    """Copy example config files into place if they don't already exist."""
    pairs = [
        (Path("config/settings.example.yaml"), _DEFAULT_SETTINGS),
        (Path("config/watched_items.example.yaml"), _DEFAULT_WATCHED_ITEMS),
        (Path(".env.example"), _DEFAULT_ENV),
    ]
    for src, dest in pairs:
        if dest.exists():
            typer.echo(f"[skip] {dest} already exists")
            continue
        if not src.exists():
            typer.secho(f"[warn] {src} not found, skipping", fg=typer.colors.YELLOW)
            continue
        shutil.copy(src, dest)
        typer.echo(f"[created] {dest}")
    typer.echo("Now edit config/watched_items.yaml and .env with your real details.")


if __name__ == "__main__":
    app()
