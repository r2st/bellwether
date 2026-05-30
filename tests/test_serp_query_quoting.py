"""SERP queries must wrap supplier.name in double quotes so Google does
exact-phrase matching. Without this, single-word or generic supplier names
("Tranquil", "Acme") pull in unrelated companies' news and the extracted
risk signals get poisoned.
"""
from __future__ import annotations

from bellwether.evidence.collectors import _quoted


def test_quoted_wraps_full_name():
    assert _quoted("Acme Electronics Manufacturing Co.") == '"Acme Electronics Manufacturing Co"'


def test_quoted_drops_trailing_period():
    # trailing periods break Google's phrase match
    assert _quoted("Foo Inc.") == '"Foo Inc"'


def test_quoted_strips_embedded_quotes():
    # an embedded " would split the phrase into two
    assert _quoted('Foo "Bar" Inc') == '"Foo Bar Inc"'


def test_quoted_preserves_internal_punctuation():
    # commas and ampersands inside the name are kept
    assert _quoted("Acme, Inc.") == '"Acme, Inc"'
    assert _quoted("Foo & Sons") == '"Foo & Sons"'


def test_quoted_strips_whitespace():
    assert _quoted("  Acme  ") == '"Acme"'
