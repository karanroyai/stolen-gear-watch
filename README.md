# stolen-gear-watch

> **🚧 Work in progress - not ready for general use.** The architecture is
> in place and the core (matching, storage, alerting) works, but several
> marketplace adapters are unverified or experimental - see "What it
> actually does (and what it doesn't)" below before assuming a site will
> work. No tagged release yet. Feel free to read the code or open issues,
> but hold off on relying on this to actually watch for your stolen gear.

Watches classifieds/marketplace sites and public stolen-gear registries for
an item you've reported stolen, and alerts you on Telegram when something
looks like a match. Built for cameras first, but nothing in the core is
camera-specific - a "watched item" is just a make/model/serial/category, so
bikes, laptops, or anything else with a serial number fits the same model.

This is a scheduled batch tool, not a persistent service: you run it via
cron or a systemd timer every so often, it does one pass, and it exits.

## What it actually does (and what it doesn't)

Three capabilities, each with a different feasibility ceiling - see the
module docstrings for the full reasoning, summarized here:

1. **Serial number / EXIF matching.** Reads a serial out of your own
   photos' metadata (via `exiftool` if installed, otherwise a Pillow
   fallback with less coverage), and fuzzy-matches your watched item's
   serial/make/model against scraped listing text. Checking *external*
   stolen-gear databases is split in two: [Lenstag](https://lenstag.com)
   has a real public registry that's automated on a best-effort basis
   (see `stolen_registries/lenstag.py` for the caveats); **Stolen Camera
   Finder is not automated** - it works by uploading a photo for
   sensor-dust-pattern matching, not by querying a database, so this tool
   just gives you a direct link and reminds you to check it by hand.

2. **Marketplace scraping**, config-driven, one adapter class per site.
   Ships with Willhaben (AT), Kleinanzeigen (DE), Limundo (RS), and
   KupujemProdajem (RS). **Some of these are experimental** - Willhaben in
   particular blocked even a single automated request while this was being
   built, a strong sign of active bot-detection. This project deliberately
   does not build evasion around that; if an adapter stops working, treat
   that site as a manual-check target rather than trying to work around
   the block. See each adapter's module docstring for its verification
   status.

3. **Reverse image search.** Scraping Google Lens/Images directly is out
   of scope (against ToS, fragile, real risk). Instead this wraps official
   APIs - Google Cloud Vision's Web Detection and TinEye's API - both
   opt-in and requiring your own API key. With no key configured, the
   default `manual` backend just logs a direct TinEye/Lens link per photo
   so you can check by hand.

## Quick start

```bash
git clone <this repo>
cd stolen-gear-watch
python3 -m venv .venv && source .venv/bin/activate
pip install -e .

# optional but recommended: better EXIF/serial extraction
# Debian/Ubuntu: sudo apt install libimage-exiftool-perl
# macOS: brew install exiftool

stolen-gear-watch init   # copies example config into config/*.yaml and .env
```

Then:

1. Edit `config/watched_items.yaml` with your real item(s). **This file is
   gitignored - never commit it.**
2. Edit `config/settings.yaml` to enable/disable adapters and set rate limits.
3. Edit `.env`:
   - Message [@BotFather](https://t.me/BotFather) to create a Telegram bot,
     get the token, put it in `TELEGRAM_BOT_TOKEN`.
   - Message your new bot once, then visit
     `https://api.telegram.org/bot<token>/getUpdates` to find your chat id,
     put it in `TELEGRAM_CHAT_ID`.
4. Run it once by hand to check everything's wired up:

```bash
stolen-gear-watch run
```

To check a serial before buying used gear, without touching the scrapers:

```bash
stolen-gear-watch check-serial 123456789012 --make Canon --model "EOS R5"
```

## Running on a schedule

No daemon mode by design - use cron:

```cron
# every 3 hours
0 */3 * * * cd /path/to/stolen-gear-watch && .venv/bin/stolen-gear-watch run >> logs/run.log 2>&1
```

or a systemd timer (`stolen-gear-watch.service` + `stolen-gear-watch.timer`
in the usual `~/.config/systemd/user/` location) if you want journald
logging and don't want a crontab.

## Configuration reference

- **`config/settings.yaml`** - adapters enabled, rate limits, reverse-image
  backend, which stolen registries to check, whether Telegram alerting is
  on. No personal data; safe to share/commit.
- **`config/watched_items.yaml`** - the actual item(s): make, model,
  serial, description, reference photos, price range. Gitignored.
- **`.env`** - all secrets (Telegram bot token/chat id, reverse-image API
  keys). Gitignored. Copy from `.env.example`.

## Adding a new marketplace

Write one class in `src/stolen_gear_watch/scrapers/your_site.py`
implementing `Adapter` (see `scrapers/base.py`), decorate it with
`@register_adapter`, add one import line to `scrapers/__init__.py`, and add
an entry under `scrapers:` in `settings.yaml`. Nothing else in the codebase
needs to change - the pipeline, matching, and alerting are all
adapter-agnostic.

Before writing one: check the site's `robots.txt` (the base `Adapter`
class enforces it automatically via `self._get()` - disallowed paths raise
`RobotsDisallowedError` rather than silently proceeding) and don't build
around active bot-detection. If a site doesn't want to be scraped, the
right answer is a documented manual-check step, not a workaround - see
`stolen_registries/manual.py` for the pattern.

## Scraping ethics

- Every request goes through `robots.txt` checking and per-site rate
  limiting (`net.py`), never raw `requests` calls from adapter code.
- The User-Agent identifies this tool and an optional contact email
  (`SCRAPER_CONTACT_EMAIL` in `.env`) so a site operator can reach you.
- No CAPTCHA solving, no residential proxies, no browser fingerprint
  spoofing to get around detection. If an adapter is blocked, it's
  documented as experimental/manual rather than worked around.

## Development

```bash
pip install -e ".[dev]"
pytest
ruff check .
```

## License

MIT - see [LICENSE](LICENSE).
