import pytest
import responses

from stolen_gear_watch.net import PoliteHttpClient, RobotsDisallowedError


class _TestClient(PoliteHttpClient):
    base_url = "https://example.test"


@responses.activate
def test_wildcard_disallow_rule_is_enforced():
    """Regression test: stdlib urllib.robotparser silently ignores `*`
    wildcard Disallow rules (it only does literal prefix matching), which
    would make a URL like this one look allowed when the site's own
    robots.txt says otherwise. This is why net.py uses `protego` instead -
    see net.py's module docstring for the real-world case (Willhaben)
    that surfaced this."""
    responses.add(
        responses.GET,
        "https://example.test/robots.txt",
        body="User-agent: *\nDisallow: /*?*keyword=*\n",
        status=200,
    )
    client = _TestClient(rate_limit_seconds=0)

    with pytest.raises(RobotsDisallowedError):
        client._get("https://example.test/search", params={"keyword": "canon"})


@responses.activate
def test_allowed_url_passes_through():
    responses.add(
        responses.GET,
        "https://example.test/robots.txt",
        body="User-agent: *\nDisallow: /admin\n",
        status=200,
    )
    responses.add(
        responses.GET,
        "https://example.test/search?keyword=canon",
        body="ok",
        status=200,
    )
    client = _TestClient(rate_limit_seconds=0)

    resp = client._get("https://example.test/search", params={"keyword": "canon"})
    assert resp.text == "ok"


@responses.activate
def test_unreachable_robots_txt_does_not_crash(caplog):
    responses.add(responses.GET, "https://example.test/robots.txt", status=500)
    responses.add(responses.GET, "https://example.test/search", body="ok", status=200)
    client = _TestClient(rate_limit_seconds=0)

    resp = client._get("https://example.test/search")
    assert resp.text == "ok"
