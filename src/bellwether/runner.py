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
from .extract.granite import Extractor, GraniteExtractor, MockExtractor
from .memo.writer import write_memo
from .models import Memo, Supplier
from .score.scorer import score_supplier


def _extraction_meta(extractor: Extractor) -> tuple[str, str]:
    """Best-effort (model, provider) tuple for an extractor — surfaced in audit HTML."""
    if isinstance(extractor, GraniteExtractor):
        model = getattr(extractor, "model", "ibm-granite/granite")
        base = str(getattr(extractor.client, "base_url", ""))
        host = "openrouter" if "openrouter" in base else "amd-mi300x"
        return model, host
    if isinstance(extractor, MockExtractor):
        return "regex-rules", "mock"
    return getattr(extractor, "__class__", type(extractor)).__name__, "unknown"


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
        memo = await run_crew_for_supplier(
            supplier,
            cache=cache,
            extractor=extractor,
            client=client,
            memo_dir=memo_dir,
            mock=mock,
        )
    else:
        evidence = await collect_all(supplier, cache, client, mock=mock)
        signals = extractor.extract(supplier.name, evidence)
        score = score_supplier(supplier.id, signals)
        memo = write_memo(supplier, score, evidence, out_dir=memo_dir)

    model, provider = _extraction_meta(extractor)
    memo.extraction_model = model
    memo.extraction_provider = provider
    return memo


def run_supplier_sync(supplier: Supplier, **kw) -> Memo:
    return asyncio.run(run_supplier(supplier, **kw))
