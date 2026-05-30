"""Per-source evidence collectors.

Each collector takes a Supplier, returns a list of EvidenceRecords, and
writes through the EvidenceCache. Mock mode bypasses Bright Data and
reads from packaged fixtures so the pipeline runs without tokens.
"""
from __future__ import annotations

import csv
import json
from datetime import datetime, timezone
from io import StringIO
from pathlib import Path
from typing import Iterable

import httpx

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
    out.extend(await _sanctions(supplier, cache))
    return out


async def _serp(
    supplier: Supplier, cache: EvidenceCache, client: BrightDataClient
) -> list[EvidenceRecord]:
    # Quote the full supplier name so Google does exact-phrase matching.
    # Unquoted, generic names like "Tranquil" or "Acme" pull in unrelated
    # companies' news (Hair Relaxer Lawsuit, Britannia CEO, etc) which
    # then poison the extracted signals.
    n = _quoted(supplier.name)
    queries = [
        f"{n} layoffs",
        f"{n} lawsuit",
        f"{n} CEO OR CFO departure",
        f"{n} earnings",
    ]
    out: list[EvidenceRecord] = []
    for q in queries:
        try:
            envelope = await client.serp(q)
        except Exception as e:  # one failed query shouldn't kill the run
            print(f"  ! SERP failed for {q!r}: {e}")
            continue
        for item in _serp_items(envelope):
            url = _serp_item_url(item)
            if not url:
                print(f"  ! SERP item has no link/url/source: keys={list(item)[:4]}")
                continue
            title = item.get("title") or ""
            snippet = item.get("snippet") or item.get("description") or ""
            # Belt-and-suspenders: even with quoted queries + nfpr=1 Google
            # occasionally slips in tangentially-related results. Drop any
            # item where the supplier name (or an alias) doesn't appear in
            # the title or snippet. Stops a cross-company false positive
            # from poisoning the extractor.
            if not _mentions_supplier(supplier, title, snippet):
                continue
            rec = _record(
                supplier_id=supplier.id,
                source_url=url,
                source_type="serp",
                scraper_id=f"brightdata:{client.serp_zone}",
                snippet=snippet,
                title=title,
                published_at=_parse_dt(item.get("date")),
                raw=item,
            )
            cache.put(rec)
            out.append(rec)
    return out


def _mentions_supplier(supplier: Supplier, title: str, snippet: str) -> bool:
    """True if the supplier's name (or any alias) appears in title or snippet.

    Match is case-insensitive on the longest available token of the name —
    typically the first two words, e.g. "Acme Electronics" rather than the
    full "Acme Electronics Manufacturing Co.". This catches headlines that
    abbreviate the name while still rejecting unrelated companies.
    """
    haystack = f"{title} {snippet}".lower()
    needles = [supplier.name, *supplier.aliases]
    for raw in needles:
        n = raw.lower().strip()
        if not n:
            continue
        # try the full name first, then the leading two tokens
        if n in haystack:
            return True
        tokens = n.split()
        if len(tokens) >= 2 and " ".join(tokens[:2]) in haystack:
            return True
    return False


def _serp_items(envelope: dict) -> Iterable[dict]:
    """Yield SERP result items from BD's parsed envelope.

    With `brd_json=1` the envelope is a top-level dict with keys like
    `news` / `organic` / `news_results` / `organic_results`. Older shapes
    just yielded a top-level list. We probe both for safety.
    """
    if isinstance(envelope, dict):
        for key in ("news", "news_results", "organic", "organic_results", "items", "results"):
            v = envelope.get(key)
            if isinstance(v, list):
                yield from v
                return
    if isinstance(envelope, list):
        yield from envelope


def _quoted(name: str) -> str:
    """Wrap a supplier name in double quotes for exact-phrase SERP matching.

    Drops embedded quotes (Google treats them as new phrase boundaries) and
    a trailing period (which kills phrase match because Google indexes the
    period as part of the phrase). Common suffixes like ", Inc." are left
    intact — they're often part of the legal name on news indices.
    """
    cleaned = name.replace('"', "").strip().rstrip(".")
    return f'"{cleaned}"'


def _serp_item_url(item: dict) -> str | None:
    """Best-effort URL extraction; BD news shapes use link/url/source.link."""
    for k in ("link", "url", "displayed_link"):
        v = item.get(k)
        if isinstance(v, str) and v.startswith("http"):
            return v
    src = item.get("source")
    if isinstance(src, dict):
        for k in ("link", "url"):
            v = src.get(k)
            if isinstance(v, str) and v.startswith("http"):
                return v
    return None


async def _resolve_linkedin_url(
    supplier: Supplier, client: BrightDataClient
) -> str | None:
    """Use supplier.linkedin_url if pinned; else SERP-resolve."""
    if supplier.linkedin_url:
        return supplier.linkedin_url
    query = f'site:linkedin.com/company "{supplier.name}"'
    try:
        envelope = await client.serp(query, num=3)
    except Exception as e:
        print(f"  ! LinkedIn URL resolution failed for {supplier.name!r}: {e}")
        return None
    for item in _serp_items(envelope):
        url = _serp_item_url(item)
        if url and url.startswith("https://www.linkedin.com/company/"):
            return url.split("?", 1)[0].rstrip("/")
    return None


async def _linkedin(
    supplier: Supplier, cache: EvidenceCache, client: BrightDataClient
) -> list[EvidenceRecord]:
    company_url = await _resolve_linkedin_url(supplier, client)
    if not company_url:
        print(f"  ! No LinkedIn URL for {supplier.id}; skipping LinkedIn collector")
        return []
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

# The current canonical OFAC SDN publication endpoint. The old
# treasury.gov/ofac/downloads/sdn.csv host is end-of-life and has had
# intermittent 5xx/404 episodes; we use the Sanctions List Service.
OFAC_SDN_URL = "https://sanctionslistservice.ofac.treas.gov/api/PublicationPreview/exports/SDN.CSV"


def _ofac_csv_path(cache_dir: Path) -> Path:
    today = datetime.now(timezone.utc).date().isoformat()
    return Path(cache_dir) / f"_ofac_sdn-{today}.csv"


async def _fetch_ofac_csv(cache_root: Path) -> str | None:
    """Fetch SDN.CSV once per UTC day; reuse across suppliers."""
    cache_path = _ofac_csv_path(cache_root)
    if cache_path.exists():
        return cache_path.read_text()
    try:
        async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as http:
            r = await http.get(OFAC_SDN_URL)
            r.raise_for_status()
            text = r.text
    except httpx.HTTPError as e:
        print(f"  ! OFAC fetch failed: {e}")
        return None
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache_path.write_text(text)
    return text


def _normalize(s: str) -> str:
    """Lower-case, strip punctuation, collapse whitespace."""
    out = []
    for ch in s.lower():
        if ch.isalnum() or ch == " ":
            out.append(ch)
        else:
            out.append(" ")
    return " ".join("".join(out).split())


def _name_match(sdn_name: str, needle: str) -> bool:
    """Whole-word match; short needles require exact equality to avoid noise."""
    if not needle:
        return False
    if len(needle) < 4:
        return sdn_name == needle
    if sdn_name == needle:
        return True
    return f" {needle} " in f" {sdn_name} "


def find_ofac_hits(csv_text: str, needles: Iterable[str]) -> list[dict]:
    """Parse the SDN CSV and return hits on the SDN_Name column only.

    Public so the unit tests can exercise it without httpx.
    """
    normalized = {_normalize(n) for n in needles if n and n.strip()}
    if not normalized:
        return []
    out: list[dict] = []
    reader = csv.reader(StringIO(csv_text))
    for row in reader:
        if len(row) < 4:
            continue
        sdn_name = _normalize(row[1])
        for needle in normalized:
            if _name_match(sdn_name, needle):
                out.append({
                    "ent_num": row[0],
                    "sdn_name": row[1],
                    "sdn_type": row[2] if len(row) > 2 else "",
                    "program": row[3] if len(row) > 3 else "",
                    "matched_on": needle,
                })
                break
    return out


async def _sanctions(supplier: Supplier, cache: EvidenceCache) -> list[EvidenceRecord]:
    """Sanctions is a deterministic, CSV-parsed match against the SDN list.

    Granite is never allowed to *decide* a sanctions hit — only to describe
    one. That's why this lives in plain Python and doesn't touch BD or LLMs.
    """
    text = await _fetch_ofac_csv(cache.root)
    if text is None:
        return []
    needles = [supplier.name, *supplier.aliases]
    hits = find_ofac_hits(text, needles)
    if not hits:
        return []
    sample = ", ".join(h["sdn_name"] for h in hits[:3])
    rec = _record(
        supplier_id=supplier.id,
        source_url=OFAC_SDN_URL,
        source_type="sanctions",
        scraper_id="ofac:sdn-csv",
        snippet=f"{len(hits)} SDN match(es): {sample}",
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
