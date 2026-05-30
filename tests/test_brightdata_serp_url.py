"""h01 — SERP query URL must be properly percent-encoded.

The bug: queries containing `&`, `=`, `#`, spaces, or non-ASCII previously
got injected into the URL raw, so a supplier name like "Acme & Sons" silently
truncated the `q=` parameter at the unescaped ampersand.
"""
from __future__ import annotations

from bellwether.evidence.brightdata import BrightDataClient


def _client():
    return BrightDataClient(
        api_token="t",
        serp_zone="z",
        unlocker_zone="u",
        linkedin_dataset_id="d",
    )


def test_ampersand_encoded():
    url = _client()._serp_url("Acme & Sons earnings", country="us", num=10)
    assert "q=Acme+%26+Sons+earnings" in url
    # the literal ampersand from the query must NOT terminate the q= param
    assert url.count("&") == 5  # &tbm, &num, &gl, &nfpr, &brd_json


def test_brd_json_flag_present():
    # brd_json=1 makes BD return structured news/organic JSON instead of HTML
    url = _client()._serp_url("Acme", country="us", num=10)
    assert "brd_json=1" in url


def test_nfpr_flag_present():
    # nfpr=1 disables Google's "showing results for similar queries" broadening
    url = _client()._serp_url("Acme", country="us", num=10)
    assert "nfpr=1" in url


def test_spaces_encoded():
    url = _client()._serp_url("Acme Electronics layoffs", country="us", num=10)
    assert "q=Acme+Electronics+layoffs" in url


def test_unicode_encoded():
    url = _client()._serp_url("Nestlé S.A.", country="us", num=10)
    assert "q=Nestl%C3%A9+S.A." in url


def test_query_with_equals_and_hash():
    url = _client()._serp_url("X=1 #fail", country="us", num=10)
    assert "q=X%3D1+%23fail" in url


def test_country_param_preserved():
    url = _client()._serp_url("Acme", country="de", num=20)
    assert "gl=de" in url
    assert "num=20" in url
