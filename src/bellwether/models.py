"""Pydantic schemas — the contract every module reads and writes."""
from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, Field

Dimension = Literal[
    "financial_distress",
    "leadership_churn",
    "legal_exposure",
    "sanctions",
    "operational_chatter",
]

SourceType = Literal["serp", "linkedin", "sanctions", "court", "filing", "fixture"]


def _now() -> datetime:
    return datetime.now(timezone.utc)


class Supplier(BaseModel):
    id: str
    name: str
    domain: str | None = None
    aliases: list[str] = Field(default_factory=list)
    hubspot_id: str | None = None
    linkedin_url: str | None = None


class EvidenceRecord(BaseModel):
    """One piece of live-web evidence, with provenance.

    Every field downstream of this — every signal, every memo line —
    must trace back to an EvidenceRecord by id.
    """

    id: str
    supplier_id: str
    source_url: str
    source_type: SourceType
    scraper_id: str
    fetched_at: datetime
    title: str | None = None
    snippet: str
    published_at: datetime | None = None
    raw: dict = Field(default_factory=dict)

    @classmethod
    def make_id(cls, source_url: str, fetched_at: datetime) -> str:
        h = hashlib.sha256(f"{source_url}|{fetched_at.isoformat()}".encode()).hexdigest()
        return h[:16]


class RiskSignal(BaseModel):
    """A structured judgment extracted from one or more EvidenceRecords."""

    dimension: Dimension
    severity: int = Field(ge=0, le=10)
    description: str
    evidence_ids: list[str]
    confidence: float = Field(ge=0.0, le=1.0, default=0.7)
    observed_at: datetime = Field(default_factory=_now)


class RiskScore(BaseModel):
    supplier_id: str
    score: float = Field(ge=0.0, le=10.0)
    score_delta_7d: float | None = None
    top_signals: list[RiskSignal]
    computed_at: datetime = Field(default_factory=_now)


class Memo(BaseModel):
    supplier: Supplier
    score: RiskScore
    body_markdown: str
    evidence: list[EvidenceRecord]
    generated_at: datetime = Field(default_factory=_now)
    # Optional metadata surfaced in the audit HTML so judges/auditors can see
    # how the number was produced. Older memo JSON files load fine via defaults.
    extraction_model: str | None = None
    extraction_provider: str | None = None
    hubspot_ticket_id: str | None = None
    hubspot_portal_id: str | None = None
