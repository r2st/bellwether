"""h03 — OFAC matcher must use proper CSV parsing on SDN_Name column only.

The bug: previous matcher used raw substring search over full CSV lines, so
"Acme" matched "PYROTACME LLC" (substring) and any address line with that
substring. With the sanctions pin (scorer.py), a single false positive flips
a clean supplier to "STOP — sanctions".
"""
from __future__ import annotations

from bellwether.evidence.collectors import find_ofac_hits

# Minimal CSV mimicking the SDN.CSV layout:
#   ent_num, SDN_Name, SDN_Type, Program, Title, Call_Sign, ...
SAMPLE_CSV = (
    "1001,PYROTACME LLC,Entity,SDGT,,\n"
    "1002,ACME INC,Entity,CYBER2,,\n"
    "1003,ABB-Group of Companies,Entity,FOREIGN-EO13902,,\n"
    "1004,\"AKHMEDOV, Ivan\",Individual,RUSSIA-EO14024,,\n"
    "1005,Bluewave Holding Pty Ltd,Entity,IRAN-EO13599,,\n"
)


def test_short_substring_does_not_false_positive():
    # "Acme" is 4 chars — should match ACME INC but NOT PYROTACME LLC
    hits = find_ofac_hits(SAMPLE_CSV, ["Acme"])
    names = [h["sdn_name"] for h in hits]
    assert "ACME INC" in names
    assert "PYROTACME LLC" not in names


def test_short_three_char_name_requires_exact_equality():
    # "ABB" is 3 chars — must equal the SDN_Name exactly, no substring noise
    hits = find_ofac_hits(SAMPLE_CSV, ["ABB"])
    # the only SDN with literal "ABB" name would have to be exactly "ABB"
    # "ABB-Group of Companies" → normalized "abb group of companies" — should NOT match "abb"
    assert hits == []


def test_punctuation_normalized_on_both_sides():
    # supplier "Acme, Inc." should match SDN "ACME INC" via punctuation normalization
    hits = find_ofac_hits(SAMPLE_CSV, ["Acme, Inc."])
    assert any(h["sdn_name"] == "ACME INC" for h in hits)


def test_alias_independent_of_primary():
    # primary name doesn't match; alias does
    hits = find_ofac_hits(SAMPLE_CSV, ["Definitely Not Listed", "Bluewave Holding"])
    assert any(h["sdn_name"].startswith("Bluewave") for h in hits)


def test_empty_needles_returns_nothing():
    assert find_ofac_hits(SAMPLE_CSV, []) == []
    assert find_ofac_hits(SAMPLE_CSV, ["", "  "]) == []


def test_match_reports_program_and_matched_needle():
    hits = find_ofac_hits(SAMPLE_CSV, ["Acme"])
    h = next(h for h in hits if h["sdn_name"] == "ACME INC")
    assert h["program"] == "CYBER2"
    assert h["matched_on"] == "acme"
