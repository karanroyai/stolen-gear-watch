# Contributing

Bug reports, adapter fixes, and new marketplace adapters are all welcome.
This doc focuses on the most common contribution: adding a new site.

## Adding a new marketplace adapter

Adding a site should never require touching the pipeline, matching, or
alerting code - only `scrapers/`. If you find yourself editing anything
outside that directory to add a site, that's a sign the `Adapter`
interface is missing something; open an issue before working around it.

### 1. Check the site's policy before writing any code

- Read `https://<site>/robots.txt` yourself, including any `*`/`$`
  wildcard rules and free-text comments - don't just trust
  `self._robots.can_fetch()` returning `True` while writing the adapter as
  proof the site is fine with it. It's checked with `protego`
  specifically because wildcard rules (very common - see Willhaben's
  robots.txt) are how sites actually express "don't hit this search
  endpoint," and a naive parser would miss that. If the paths you need are
  disallowed, stop - don't build the adapter. Either find an allowed path
  (an official search API, an RSS/JSON feed) or skip the site.
- Look for active bot-detection (CAPTCHAs, "attention required" pages,
  requests that get blocked outright even for a single GET). If you hit
  that, don't try to work around it - see "What we won't merge" below.
- Prefer a documented API or structured feed over scraping HTML if the
  site has one.

### 2. Write the adapter

Create `src/stolen_gear_watch/scrapers/your_site.py`:

```python
from collections.abc import Iterator

from stolen_gear_watch.core.models import RawListing, WatchedItem
from stolen_gear_watch.scrapers.base import Adapter
from stolen_gear_watch.scrapers.registry import register_adapter


@register_adapter
class YourSiteAdapter(Adapter):
    site_key = "your_site"          # matches the key used in settings.yaml
    base_url = "https://www.your-site.example"

    def search(self, item: WatchedItem) -> Iterator[RawListing]:
        for page in range(1, self.settings.max_pages + 1):
            resp = self._get(f"{self.base_url}/search", params={"q": ..., "page": page})
            # parse resp.text (BeautifulSoup) or resp.json(), yield RawListing(...)
```

Rules for the body of `search()`:

- **Always use `self._get()`**, never `requests` directly. It enforces
  robots.txt and the per-site rate limit from `settings.yaml` for you -
  see `net.py` if you want to understand what it's doing.
- **Respect `self.settings.max_pages`.** Don't paginate indefinitely.
- **Stop cleanly when results run out or look wrong**, and log why
  (`logger.info(...)` for "no cards found, selectors may be stale",
  `logger.warning(...)` for "this looks like a bot-challenge page" - see
  `willhaben.py` and `scrapers/utils.py::looks_like_bot_challenge` for the
  pattern). A silent empty result set is a debugging trap for whoever
  configures this adapter next.
- **Every `RawListing` needs a stable `source_id`** unique within that
  site (the site's own listing id, not a hash of the URL) - this is what
  dedup in the database keys off of.

### 3. Register it

Add one import line to `scrapers/__init__.py`:

```python
from stolen_gear_watch.scrapers import your_site  # noqa: F401
```

The `@register_adapter` decorator does the rest - `get_adapter("your_site")`
and `available_site_keys()` pick it up automatically.

### 4. Wire it into example config

Add an entry to `config/settings.example.yaml` under `scrapers:` so users
can discover and enable it:

```yaml
scrapers:
  your_site:
    enabled: false   # default to off until it's been verified against live data
    rate_limit_seconds: 5
    max_pages: 3
```

### 5. Document its verification status

Every adapter's module docstring should say plainly how confident it is:
verified against live markup on a specific date, or best-effort/unverified
because the site blocked or 403'd testing. See `kupujemprodajem.py` (built
against a confirmed live page) vs. `willhaben.py`/`limundo.py`
(best-effort, blocked during development) for the tone to match. Don't
present a guessed CSS selector as if it were confirmed working.

### 6. Tests

Not required for the adapter itself. This project isn't aiming for high
test coverage on individual scrapers - marketplace HTML changes out from
under you regardless of how well-tested the parsing code was, and it gets
fixed ad hoc when someone notices an adapter returning nothing. `tests/`
is reserved for the structural stuff that doesn't drift on its own:
`core/` (models, config, db), `matching/`, and shared infrastructure like
`net.py`'s robots.txt/rate-limit enforcement. If you're adding to one of
those, a test is expected; if you're adding a marketplace adapter, it
isn't.

## What we won't merge

- Anything that works around bot-detection: CAPTCHA solving, residential
  proxies, browser fingerprint spoofing, headless-browser evasion tricks.
  If a site actively blocks automated access, the right outcome is an
  adapter documented as experimental/manual-check (see
  `stolen_registries/manual.py` for the pattern used for services that
  can't be automated at all), not a workaround.
- Adapters that ignore `robots.txt` or hardcode around the `Adapter` base
  class's robots/rate-limit enforcement.
- Scraping Google Images/Lens directly (see `reverse_image/base.py` for
  why - use the official Vision/TinEye API backends instead).

## Other extension points

The same registration pattern is used elsewhere if you'd rather
contribute one of these instead of a marketplace adapter:

- **Stolen-gear registries** (`stolen_registries/`): implement
  `RegistryChecker`, add it to the `REGISTRIES` dict in
  `stolen_registries/__init__.py`.
- **Reverse image search backends** (`reverse_image/`): implement
  `ImageSearchBackend`, wire it into `reverse_image/__init__.py::get_backend`.
- **Alerting** (`alerting/`): implement `Notifier` (e.g. email, a generic
  webhook), wire it into `alerting/__init__.py::get_notifiers`.

## Development setup

```bash
pip install -e ".[dev]"
pytest
ruff check .
```
