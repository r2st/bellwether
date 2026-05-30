"""Client-side filter: SERP results must mention the supplier (name or alias)
in title or snippet. Backstop for when Google's quoted-phrase + nfpr=1 still
slips an unrelated company through.
"""
from __future__ import annotations

from bellwether.evidence.collectors import _mentions_supplier
from bellwether.models import Supplier


def _sup(**kw):
    return Supplier(id="x", name=kw.pop("name", "Acme Electronics Manufacturing Co."), **kw)


def test_full_name_in_title():
    s = _sup()
    assert _mentions_supplier(s, "Acme Electronics Manufacturing Co. layoffs", "")


def test_leading_two_tokens_in_title():
    # Headlines often abbreviate; "Acme Electronics" should still match
    s = _sup()
    assert _mentions_supplier(s, "Acme Electronics announces CFO transition", "")


def test_leading_two_tokens_in_snippet():
    s = _sup()
    assert _mentions_supplier(s, "Some headline", "Sources at Acme Electronics confirmed the news.")


def test_unrelated_company_rejected():
    # The Britannia / Hair-Relaxer false positive that prompted this filter
    s = _sup()
    assert not _mentions_supplier(
        s, "Britannia Appoints New CEO After Resignation",
        "The Britannia board announced a transition this week.",
    )


def test_short_substring_match_still_works_via_alias():
    s = _sup(aliases=["Acme EMS"])
    assert _mentions_supplier(s, "Acme EMS files Chapter 11", "")


def test_case_insensitive():
    s = _sup()
    assert _mentions_supplier(s, "ACME ELECTRONICS Q1 RESULTS", "")


def test_single_token_name_requires_full_match():
    # Short / generic single-word names like "Tranquil" can still match
    # if the literal token appears in text, which is the expected behavior.
    s = _sup(name="Tranquil")
    assert _mentions_supplier(s, "Tranquil Corp earnings beat estimates", "")
    assert not _mentions_supplier(s, "Hair Relaxer Lawsuit Settlement", "")
