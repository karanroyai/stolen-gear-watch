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
   fallback with less coverage; `stolen-gear-watch check-exif <photo>` runs
   this from the CLI), and fuzzy-matches your watched item's serial/make/model
   against scraped listing text. Checking *external* stolen-gear databases:
   [Lenstag](https://lenstag.com) has a real public registry that's
   automated on a best-effort basis (see `stolen_registries/lenstag.py` for
   the caveats). **Stolen Camera Finder** turns out to have two separate
   search modes - its serial-number search is automated the same way
   (`stolen_registries/stolen_camera_finder.py`, verified against a real
   server-rendered fallback endpoint their site ships); its reverse-image
   *sensor-dust-pattern* search genuinely isn't automatable (needs a photo
   upload against a service with no API), so that one still just gives you
   a direct link and reminds you to check it by hand.

2. **Marketplace scraping**, config-driven, one adapter class per site.
   Ships with Willhaben (AT), Kleinanzeigen (DE), Limundo (RS), and
   KupujemProdajem (RS). **Willhaben is disabled by default and won't
   return results**: its robots.txt explicitly forbids automated access
   ("It is expressively forbidden to use spiders, search robots or other
   automatic methods...") and disallows the search query pattern this
   adapter needs, so `Adapter._get()` refuses every request itself -
   this was verified directly against the live robots.txt, not guessed.
   Limundo is also unverified/experimental (got an HTTP 403 during
   testing). This project deliberately does not build evasion around
   either case; if a site doesn't want to be scraped, treat it as a
   manual-check target. See each adapter's module docstring for its
   verification status.

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
  Parsing uses `protego`, not stdlib `urllib.robotparser` - the stdlib
  parser only does literal prefix matching and silently ignores `*`/`$`
  wildcards, which is how most real robots.txt files actually express
  their rules (Willhaben's is a good example - see `scrapers/willhaben.py`).
- The User-Agent identifies this tool and an optional contact email
  (`SCRAPER_CONTACT_EMAIL` in `.env`) so a site operator can reach you.
- No CAPTCHA solving, no residential proxies, no browser fingerprint
  spoofing to get around detection. If an adapter is blocked, it's
  documented as experimental/manual rather than worked around.
- `respect_robots_txt` (per adapter, in `settings.yaml`) defaults to
  `true` everywhere and isn't set to `false` anywhere in the shipped
  example config. It's an explicit, opt-in escape hatch for operators who
  decide - for themselves, for their own reasons - to scrape a site
  despite what its robots.txt says, same idea as Scrapy's
  `ROBOTSTXT_OBEY`. Turning it off doesn't mean the site allows it; it
  means you're choosing to proceed anyway, at your own risk (possible
  ToS violation, IP/account bans, and depending on jurisdiction real
  legal exposure - this project doesn't have a legal opinion on that for
  you). This tool will never turn it off for you or suggest a site-specific
  default of `false`.

## Development

```bash
pip install -e ".[dev]"
pytest
ruff check .
```

## License

MIT - see [LICENSE](LICENSE).
