"""Crew path smoke test — c03 acceptance pin.

The crew entry point must produce a Memo with the same schema and the
same scoring as the legacy sequential path. Same fixture in → same shape
out, regardless of orchestrator.
"""
from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from bellwether.crew import build_crew, run_crew_for_supplier
from bellwether.evidence.cache import EvidenceCache
from bellwether.extract.granite import MockExtractor
from bellwether.fixtures.loader import get_supplier
from bellwether.models import Memo
from bellwether.runner import run_supplier


def _kwargs(tmp_path: Path) -> dict:
    return dict(
        cache=EvidenceCache(tmp_path / "cache"),
        extractor=MockExtractor(),
        client=None,
        memo_dir=tmp_path / "memos",
        mock=True,
    )


def test_build_crew_imports_and_constructs():
    supplier = get_supplier("acme-electronics")
    bundle = build_crew(supplier, mock=True, memo_dir=None)
    assert len(bundle.agents) == 4
    assert [a.role for a in bundle.agents] == [
        "Researcher", "Compliance", "Analyst", "Writer",
    ]


def test_crew_path_produces_memo(tmp_path):
    supplier = get_supplier("acme-electronics")
    memo = asyncio.run(run_crew_for_supplier(supplier, **_kwargs(tmp_path)))
    assert isinstance(memo, Memo)
    assert memo.supplier.id == "acme-electronics"
    assert memo.score.score >= 0.0
    assert memo.evidence  # something landed


def test_crew_path_matches_sequential(tmp_path):
    """Same fixture in → same score on both orchestrators."""
    supplier = get_supplier("acme-electronics")
    via_crew = asyncio.run(
        run_supplier(supplier, via_crew=True, **_kwargs(tmp_path / "a"))
    )
    via_seq = asyncio.run(
        run_supplier(supplier, via_crew=False, **_kwargs(tmp_path / "b"))
    )
    assert via_crew.score.score == via_seq.score.score
    assert {s.dimension for s in via_crew.score.top_signals} == \
           {s.dimension for s in via_seq.score.top_signals}
