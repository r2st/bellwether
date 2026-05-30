"""m06 — SERP item URL extraction must tolerate link/url/source.link shapes.

The bug: previous code accessed item["link"] hard-keyed; a single envelope
with `url` instead of `link` crashed the whole supplier's SERP phase.
"""
from __future__ import annotations

from bellwether.evidence.collectors import _serp_item_url


def test_link_key():
    assert _serp_item_url({"link": "https://example.com/a"}) == "https://example.com/a"


def test_url_key():
    assert _serp_item_url({"url": "https://example.com/b"}) == "https://example.com/b"


def test_nested_source_link():
    assert _serp_item_url({"source": {"link": "https://example.com/c"}}) == "https://example.com/c"


def test_nested_source_url():
    assert _serp_item_url({"source": {"url": "https://example.com/d"}}) == "https://example.com/d"


def test_returns_none_for_no_url():
    assert _serp_item_url({"title": "headline", "snippet": "text"}) is None


def test_ignores_non_http_values():
    # protocol-less or relative values shouldn't be returned
    assert _serp_item_url({"link": "/relative/path"}) is None
    assert _serp_item_url({"link": ""}) is None


def test_displayed_link_fallback():
    assert _serp_item_url({"displayed_link": "https://example.com/e"}) == "https://example.com/e"
