"""End-to-end pipeline for one supplier.

By default, work is orchestrated through the four-agent CrewAI crew
(`bellwether.crew`) so the demo's "researcher → compliance → analyst →
writer" beat is honest. The crew's deterministic runner exercises the
same pipeline pieces as the legacy sequential implementation kept below
under `--no-crew`.
"""
from __future__ import annotations

import asyncio
from pathlib import Path

from .crew import run_crew_for_supplier
from .evidence.brightdata import BrightDataClient
from .evidence.cache import EvidenceCache
from .evidence.collectors import collect_all
from .extract.granite import Extractor
from .memo.writer import write_memo
from .models import Memo, Supplier
from .score.scorer import score_supplier


async def run_supplier(
    supplier: Supplier,
    *,
    cache: EvidenceCache,
    extractor: Extractor,
    client: BrightDataClient | None,
    memo_dir: Path | None = None,
    mock: bool = False,
    via_crew: bool = True,
) -> Memo:
    """Run one supplier end-to-end. `via_crew=True` (default) routes through
    the CrewAI crew; pass `via_crew=False` to use the linear pipeline directly."""
    if via_crew:
        return await run_crew_for_supplier(
            supplier,
            cache=cache,
            extractor=extractor,
            client=client,
            memo_dir=memo_dir,
            mock=mock,
        )
    evidence = await collect_all(supplier, cache, client, mock=mock)
    signals = extractor.extract(supplier.name, evidence)
    score = score_supplier(supplier.id, signals)
    return write_memo(supplier, score, evidence, out_dir=memo_dir)


def run_supplier_sync(supplier: Supplier, **kw) -> Memo:
    return asyncio.run(run_supplier(supplier, **kw))
