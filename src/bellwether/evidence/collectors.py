"""Per-source evidence collectors.

Each collector takes a Supplier, returns a list of EvidenceRecords, and
writes through the EvidenceCache. Mock mode bypasses Bright Data and
reads from packaged fixtures so the pipeline runs without tokens.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

from ..models import EvidenceRecord, Supplier
from .brightdata import BrightDataClient
from .cache import EvidenceCache

FIXTURE_ROOT = Path(__file__).resolve().parent.parent / "fixtures" / "evidence"


def _record(
    supplier_id: str,
    source_url: str,
    source_type: str,
    scraper_id: str,
    snippet: str,
    title: str | None = None,
    published_at: datetime | None = None,
    raw: dict | None = None,
) -> EvidenceRecord:
    fetched_at = datetime.now(timezone.utc)
    return EvidenceRecord(
        id=EvidenceRecord.make_id(source_url, fetched_at),
        supplier_id=supplier_id,
        source_url=source_url,
        source_type=source_type,  # type: ignore[arg-type]
        scraper_id=scraper_id,
        fetched_at=fetched_at,
        title=title,
        snippet=snippet,
        published_at=published_at,
        raw=raw or {},
    )


# ─── Mock collectors ──────────────────────────────────────────────────

def _load_fixture(supplier_id: str, name: str) -> list[dict] | None:
    path = FIXTURE_ROOT / supplier_id / f"{name}.json"
    if not path.exists():
        return None
    return json.loads(path.read_text())


def collect_mock(supplier: Supplier, cache: EvidenceCache) -> list[EvidenceRecord]:
    out: list[EvidenceRecord] = []
    for name, source_type, scraper_id in (
        ("serp", "serp", "fixture:serp"),
        ("linkedin", "linkedin", "fixture:linkedin"),
        ("sanctions", "sanctions", "fixture:ofac"),
    ):
        items = _load_fixture(supplier.id, name) or []
        for item in items:
            rec = _record(
                supplier_id=supplier.id,
                source_url=item["source_url"],
                source_type=source_type,
                scraper_id=scraper_id,
                snippet=item["snippet"],
                title=item.get("title"),
                published_at=_parse_dt(item.get("published_at")),
                raw=item,
            )
            cache.put(rec)
            out.append(rec)
    return out


def _parse_dt(s: str | None) -> datetime | None:
    if not s:
        return None
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError:
        return None


# ─── Live collectors ──────────────────────────────────────────────────

async def collect_live(
    supplier: Supplier, cache: EvidenceCache, client: BrightDataClient
) -> list[EvidenceRecord]:
    out: list[EvidenceRecord] = []
    out.extend(await _serp(supplier, cache, client))
    out.extend(await _linkedin(supplier, cache, client))
    out.extend(_sanctions(supplier, cache))
    return out


async def _serp(
    supplier: Supplier, cache: EvidenceCache, client: BrightDataClient
) -> list[EvidenceRecord]:
    queries = [
        f"{supplier.name} layoffs",
        f"{supplier.name} lawsuit",
        f"{supplier.name} CEO OR CFO departure",
        f"{supplier.name} earnings",
    ]
    out: list[EvidenceRecord] = []
    for q in queries:
        try:
            envelope = await client.serp(q)
        except Exception as e:  # one failed query shouldn't kill the run
            print(f"  ! SERP failed for {q!r}: {e}")
            continue
        for item in _serp_items(envelope):
            rec = _record(
                supplier_id=supplier.id,
                source_url=item["link"],
                source_type="serp",
                scraper_id=f"brightdata:{client.serp_zone}",
                snippet=item.get("snippet") or item.get("description") or "",
                title=item.get("title"),
                published_at=_parse_dt(item.get("date")),
                raw=item,
            )
            cache.put(rec)
            out.append(rec)
    return out


def _serp_items(envelope: dict) -> Iterable[dict]:
    # BD SERP response shape varies; try the common spots
    if isinstance(envelope, dict):
        for key in ("news", "organic", "items", "results"):
            v = envelope.get(key)
            if isinstance(v, list):
                yield from v
                return
    if isinstance(envelope, list):
        yield from envelope


async def _linkedin(
    supplier: Supplier, cache: EvidenceCache, client: BrightDataClient
) -> list[EvidenceRecord]:
    if not supplier.domain:
        return []
    # naive heuristic — production would resolve via SERP for "site:linkedin.com/company"
    company_url = f"https://www.linkedin.com/company/{supplier.id}"
    try:
        raw = await client.linkedin_company(company_url)
    except Exception as e:
        print(f"  ! LinkedIn fetch failed for {company_url}: {e}")
        return []
    if not raw:
        return []
    snippet = _linkedin_snippet(raw)
    rec = _record(
        supplier_id=supplier.id,
        source_url=company_url,
        source_type="linkedin",
        scraper_id=f"brightdata:{client.linkedin_dataset_id}",
        snippet=snippet,
        title=raw.get("name"),
        raw=raw,
    )
    cache.put(rec)
    return [rec]


def _linkedin_snippet(raw: dict) -> str:
    parts = []
    if hc := raw.get("employee_count") or raw.get("staff_count"):
        parts.append(f"Headcount ~{hc}")
    if hq := raw.get("headquarters"):
        parts.append(f"HQ {hq}")
    if upd := raw.get("recent_updates") or raw.get("posts"):
        parts.append(f"{len(upd)} recent updates")
    return " | ".join(parts) or "LinkedIn page snapshot"


# ─── Sanctions — uses official sources, not BD ────────────────────────

OFAC_SDN_URL = "https://www.treasury.gov/ofac/downloads/sdn.csv"


def _sanctions(supplier: Supplier, cache: EvidenceCache) -> list[EvidenceRecord]:
    """Sanctions is a deterministic string match against the official OFAC list.

    Granite is never allowed to *decide* a sanctions hit — only to describe
    one. That's why this lives in plain Python and doesn't touch BD or LLMs.
    """
    try:
        import httpx
        text = httpx.get(OFAC_SDN_URL, timeout=20.0).text
    except Exception as e:
        print(f"  ! OFAC fetch failed: {e}")
        return []
    needles = [supplier.name.lower(), *(a.lower() for a in supplier.aliases)]
    hits: list[str] = []
    for line in text.splitlines():
        ll = line.lower()
        for needle in needles:
            if needle and needle in ll:
                hits.append(line.strip()[:300])
                break
    if not hits:
        return []
    rec = _record(
        supplier_id=supplier.id,
        source_url=OFAC_SDN_URL,
        source_type="sanctions",
        scraper_id="ofac:sdn-csv",
        snippet=f"{len(hits)} match(es) on OFAC SDN list",
        title="OFAC SDN List match",
        raw={"hits": hits},
    )
    cache.put(rec)
    return [rec]


# ─── Entry point ──────────────────────────────────────────────────────

async def collect_all(
    supplier: Supplier,
    cache: EvidenceCache,
    client: BrightDataClient | None = None,
    *,
    mock: bool = False,
) -> list[EvidenceRecord]:
    if mock or client is None:
        return collect_mock(supplier, cache)
    return await collect_live(supplier, cache, client)
