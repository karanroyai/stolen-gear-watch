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
   Ships with Willhaben (AT), Kleinanzeigen (DE), Limundo (RS),
   KupujemProdajem (RS), Publi24 (RO), Bazar.bg (BG), Pazar3.mk (MK),
   Merrjep.al (AL), and eBay.
   **Willhaben is disabled by default and won't return results**: its
   robots.txt explicitly forbids automated access ("It is expressively
   forbidden to use spiders, search robots or other automatic
   methods...") and disallows the search query pattern this adapter
   needs, so `Adapter._get()` refuses every request itself - this was
   verified directly against the live robots.txt, not guessed. Limundo is
   also unverified/experimental (got an HTTP 403 during testing).
   Publi24, Bazar.bg, Pazar3.mk, and Merrjep.al were all verified live
   (permissive robots.txt, no bot-wall triggered, correctly parsed real
   search results including genuine Fujifilm X100VI matches). Pazar3.mk
   and Merrjep.al run the same underlying white-label platform under
   different domains/languages - their visible search box is a red
   herring (a plain `?q=` URL silently returns the *unfiltered* full
   listing set instead of erroring); the real search is a JSON AJAX
   endpoint, found by watching actual network requests while using the
   site, not by guessing - see
   `scrapers/_regional_classifieds_platform.py`. This project deliberately
   does not build evasion around a blocked site; if it doesn't want to be
   scraped, treat it as a manual-check target instead. **eBay uses their
   official Browse API**, not scraping - eBay's robots.txt explicitly
   sanctions "approved... official API" access even while disallowing
   HTML scraping, unlike every other site here. Needs a free
   developer.ebay.com account (`EBAY_CLIENT_ID`/`EBAY_CLIENT_SECRET` in
   `.env`); until those are set it logs a clear error each run rather
   than crashing. Verified live against real responses; queries multiple
   marketplaces per run (`EBAY_MARKETPLACE_IDS`, default
   `EBAY_DE,EBAY_AT,EBAY_PL` - the only genuine Central/Eastern European
   eBay sites, confirmed against the API's own list of supported
   marketplaces) - see `scrapers/ebay.py`'s docstring.

   **Sites considered and rejected, not just left out**: Facebook
   Marketplace (no public API, listings require a logged-in session,
   robots.txt is a blanket "automated collection prohibited" with no API
   carve-out); OLX (the dominant classifieds group across Poland,
   Romania, Bulgaria, Ukraine, and Bosnia - would have been the single
   highest-value addition, but runs a Cloudflare managed-challenge wall,
   confirmed live, that blocks even a plain robots.txt request); Njuškalo
   (Croatia) and Bolha (Slovenia) - same platform (Styria Media Group),
   both run a ShieldSquare/hCaptcha wall, also confirmed live. All three
   would require actual bot-detection evasion (CAPTCHA-solving, browser
   fingerprint spoofing) to return anything - a different category of
   thing from an informed robots.txt override, and not something this
   project builds regardless of query frequency or how reasonable the
   underlying goal is. Manual-check candidates, not future adapters -
   though see capability 5 below (keyword web search) for how OLX/
   Njuškalo/Bolha coverage exists anyway, indirectly, through Google's
   own already-crawled index rather than scraping them directly.

   See each adapter's module docstring for its verification status.

3. **Reverse image search.** Scraping Google Lens/Images directly is out
   of scope (against ToS, fragile, real risk). Instead this wraps official
   APIs - Google Cloud Vision's Web Detection and TinEye's API - both
   opt-in and requiring your own API key. With no key configured, the
   default `manual` backend just logs a direct check-it-yourself link.
   Two things get checked, both controlled by the same `reverse_image.backend`
   setting: **listing photos** scraped from marketplaces (only when a
   listing didn't already match confidently on text - no point spending an
   API call confirming what text matching already found), and **your own
   reference photos** (`watched_items.yaml`'s `reference_photos`) searched
   against the wider web every run, independent of any marketplace scrape -
   this is what actually finds a specific photo of your item turning up
   somewhere, not just "a listing that mentions the right model." Hits from
   either path are deduped and alerted the same way as stolen-registry hits.

   **HEIC note**: iPhone photos are usually `.heic`. Neither Google Vision
   nor TinEye's API is confirmed to accept HEIC directly - if you hit
   upload errors once you configure a real backend, convert reference
   photos to JPEG first.

4. **OCR serial matching on listing photos.** Generic visual similarity on
   a mass-produced camera body isn't actually useful for finding *your*
   unit specifically - every X100VI looks like every other X100VI, so
   it'd just flag every listing of that model, no better than text
   matching already does for free. What's genuinely more targeted: if a
   seller photographs the bottom plate or battery door, the serial number
   is often visible in the photo even when it's never mentioned in the ad
   text. `matching/ocr.py` reads text out of listing photos and checks it
   against the watched item's serial, controlled by its own `ocr.backend`
   setting (independent of `reverse_image.backend` - different problem,
   different choice of engine):
   - `none` (default) - disabled. No manual-check-link fallback either
     (unlike reverse image search) - logging a reminder per listing photo
     would be way too noisy given most photos never show a serial at all.
   - `google_vision` - Google Cloud Vision's text detection. Same API/
     credentials as the reverse-image Vision backend, just a different
     feature - nothing new to set up if you've already configured that.
     Costs money past the free tier.
   - `easyocr` - runs entirely locally (free, no account, no per-request
     cost), using a model built for "text in a photo" rather than scanned
     documents - a closer match to a serial etched on a camera at an angle
     than Tesseract's traditional strength. Pulls in PyTorch (a large,
     slow-to-install dependency) and downloads ~100MB of model weights on
     first use; after that, on a normal CPU it's roughly a few seconds to
     load the model once per run plus about a second per photo - fine for
     a cron job running every few hours, not fine for anything real-time.
     `pip install stolen-gear-watch[easyocr]` to enable.

5. **Keyword web search across a curated marketplace list.** Originally
   built as "just Google it" across the whole web, but Google
   **discontinued whole-web search for newly-created Programmable Search
   Engines as of January 20, 2026** (confirmed directly, not assumed -
   new engines are capped at 50 specific domains via "Sites to search";
   engines that already had whole-web search before that date keep it
   until 2027, which doesn't help a fresh setup). Deliberately does
   **not** scrape google.com/search directly either way (against ToS,
   fragile, real risk - same reasoning as the Google Lens decision
   above); uses the official **Custom Search JSON API** instead, free
   for 100 queries/day.

   The 50-domain cap has a genuine upside: `web_search/google_custom_search.py`'s
   `_RECOMMENDED_DOMAINS` (38 domains, meant to be pasted into the
   Programmable Search Engine's "Sites to search" config) includes
   **OLX, Njuškalo, and Bolha** - the three sites this project declined
   to build direct scrapers for because they run active bot-detection
   (Cloudflare / ShieldSquare+hCaptcha, confirmed live). Searching
   Google's own index of those sites isn't evasion of anything; Google's
   crawler already isn't blocked by those walls, so this is just asking
   an official API for results Google legitimately already has. The rest
   of the list rounds out coverage across other major European
   classifieds sites with no dedicated adapter (Marktplaats, Leboncoin,
   Subito, and others - see the module for the full list).

   Controlled by `web_search.backend` (`none` by default,
   `google_custom_search` to enable - needs
   `GOOGLE_CUSTOM_SEARCH_API_KEY`/`GOOGLE_CUSTOM_SEARCH_ENGINE_ID` in
   `.env`). Because the domain scope is now configured entirely on
   Google's side, there's no query-time domain filtering in this
   project's code - just the same accessory/color checks already applied
   to marketplace listings, since even a curated classifieds-only list
   mixes new-in-box and used listings. No post-date filtering here
   (`stolen_at`) - Custom Search's response doesn't reliably include one,
   a known gap, not silently worked around.

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

- **`config/settings.yaml`** - adapters enabled, rate limits, reverse-image/
  OCR/web-search backends, which stolen registries to check, whether
  Telegram alerting is on. No personal data; safe to share/commit.
- **`config/watched_items.yaml`** - the actual item(s): make, model,
  serial, description, reference photos, price range, and two optional
  filters applied before any matching logic runs on a listing - `color`
  (skip a listing whose text explicitly names a *different* color; never
  skips on color simply not being mentioned) and `stolen_at` (skip a
  listing with a known post date earlier than this - it can't be your
  item if it was posted before the theft). Both are conservative by
  design: they only ever filter on a confident negative signal, never on
  missing information, since a false negative (missing your actual
  stolen item) is worse than a little extra noise. Post dates aren't
  available from every adapter - currently Willhaben and Kleinanzeigen
  extract them, KupujemProdajem's search results don't expose one at all
  without fetching each listing's individual page. Gitignored.

  A third filter needs no config: `matching/accessory.py` skips listings
  that fuzzy-match on make/model but clearly aren't the item itself -
  accessories/parts ("Case für Fujifilm X100VI" - accessory keyword
  mentioned *before* the item's own make/model), books/manuals, rental
  offers, and want-ads/trade-requests. Same conservative philosophy:
  "Fujifilm X100VI + UV Filter" (item mentioned first, accessory as a
  bundled extra) is kept, only "[accessory] für/for [item]" word order
  gets filtered.
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
