"""Granite extractor — turns EvidenceRecords into RiskSignals.

Granite runs on AMD MI300X behind a vLLM endpoint speaking the OpenAI-
compatible chat API. MockExtractor is a keyword-rule fallback so the
pipeline runs without the GPU during development and demos.
"""
from __future__ import annotations

import json
import re
from typing import Protocol

from openai import OpenAI

from ..models import EvidenceRecord, RiskSignal
from .prompts import SYSTEM_PROMPT, user_prompt


class Extractor(Protocol):
    def extract(self, supplier_name: str, evidence: list[EvidenceRecord]) -> list[RiskSignal]: ...


def _evidence_block(evidence: list[EvidenceRecord]) -> str:
    lines = []
    for r in evidence:
        title = (r.title or "").replace("\n", " ")[:120]
        snip = (r.snippet or "").replace("\n", " ")[:300]
        lines.append(f"{r.id} | {r.source_type} | {title} | {snip}")
    return "\n".join(lines)


class GraniteExtractor:
    def __init__(self, base_url: str, model: str, api_key: str = "dummy") -> None:
        self.client = OpenAI(base_url=base_url, api_key=api_key)
        self.model = model

    def extract(self, supplier_name: str, evidence: list[EvidenceRecord]) -> list[RiskSignal]:
        if not evidence:
            return []
        resp = self.client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt(supplier_name, _evidence_block(evidence))},
            ],
            temperature=0.0,
            response_format={"type": "json_object"},
        )
        raw = resp.choices[0].message.content or "{}"
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            return []
        out: list[RiskSignal] = []
        for item in data.get("signals", []):
            try:
                out.append(RiskSignal(**item))
            except Exception:
                continue
        return out


# ─── Mock extractor ───────────────────────────────────────────────────

_PATTERNS: list[tuple[str, str, int]] = [
    # (regex, dimension, severity)
    (r"\b(layoff|layoffs|reduction in force|RIF)\b", "financial_distress", 6),
    (r"\b(bankruptcy|chapter 11|insolvent)\b", "financial_distress", 9),
    (r"\b(missed earnings|guidance cut|profit warning)\b", "financial_distress", 5),
    (r"\b(CEO|CFO|COO|CTO).{0,40}\b(depart|stepped down|resigned|fired)\b", "leadership_churn", 7),
    (r"\b(lawsuit|sued|litigation|class action)\b", "legal_exposure", 6),
    (r"\b(SEC investigation|DOJ probe|indictment)\b", "legal_exposure", 8),
    (r"\b(OFAC|SDN|sanctioned|sanctions list)\b", "sanctions", 10),
    (r"\b(recall|defect|safety issue|complaint)\b", "operational_chatter", 4),
]


class MockExtractor:
    """Regex-rule extractor. Not real extraction — runs the pipeline offline.

    The hackathon demo runs against the real GraniteExtractor; this lets the
    developer iterate on the rest of the system without the AMD endpoint up.
    """

    def extract(self, supplier_name: str, evidence: list[EvidenceRecord]) -> list[RiskSignal]:
        signals: list[RiskSignal] = []
        for rec in evidence:
            text = f"{rec.title or ''} {rec.snippet}"
            for pattern, dimension, severity in _PATTERNS:
                if re.search(pattern, text, flags=re.IGNORECASE):
                    signals.append(
                        RiskSignal(
                            dimension=dimension,  # type: ignore[arg-type]
                            severity=severity,
                            description=_describe(rec, dimension),
                            evidence_ids=[rec.id],
                            confidence=0.6,
                        )
                    )
                    break  # one signal per record in mock mode
            else:
                if rec.source_type == "sanctions":
                    # the fixture/live sanctions hit speaks for itself
                    signals.append(
                        RiskSignal(
                            dimension="sanctions",
                            severity=10,
                            description=f"OFAC SDN list match for {supplier_name}.",
                            evidence_ids=[rec.id],
                            confidence=1.0,
                        )
                    )
        return _dedupe(signals)


def _describe(rec: EvidenceRecord, dimension: str) -> str:
    head = (rec.title or rec.snippet or "")[:140].strip().rstrip(".")
    if not head:
        head = "Evidence observed"
    return f"{head}."


def _dedupe(signals: list[RiskSignal]) -> list[RiskSignal]:
    # collapse identical (dimension, description) pairs, union their evidence_ids
    by_key: dict[tuple[str, str], RiskSignal] = {}
    for s in signals:
        key = (s.dimension, s.description)
        if key in by_key:
            existing = by_key[key]
            merged_ids = list(dict.fromkeys([*existing.evidence_ids, *s.evidence_ids]))
            by_key[key] = existing.model_copy(update={"evidence_ids": merged_ids})
        else:
            by_key[key] = s
    return list(by_key.values())
