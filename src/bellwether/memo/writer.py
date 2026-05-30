"""Memo writer — Markdown with every score hyperlinked to its source."""
from __future__ import annotations

from datetime import datetime
from pathlib import Path

from ..models import EvidenceRecord, Memo, RiskScore, Supplier


def _evidence_index(evidence: list[EvidenceRecord]) -> dict[str, EvidenceRecord]:
    return {r.id: r for r in evidence}


def write_memo(
    supplier: Supplier,
    score: RiskScore,
    evidence: list[EvidenceRecord],
    out_dir: Path | None = None,
) -> Memo:
    idx = _evidence_index(evidence)
    body = _render(supplier, score, idx)
    memo = Memo(supplier=supplier, score=score, body_markdown=body, evidence=evidence)
    if out_dir is not None:
        out_dir = Path(out_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        date = datetime.utcnow().strftime("%Y-%m-%d")
        (out_dir / f"{supplier.id}-{date}.md").write_text(body)
        (out_dir / f"{supplier.id}-{date}.json").write_text(memo.model_dump_json(indent=2))
    return memo


def _render(supplier: Supplier, score: RiskScore, idx: dict[str, EvidenceRecord]) -> str:
    headline = _headline(score)
    delta = ""
    if score.score_delta_7d is not None:
        sign = "+" if score.score_delta_7d >= 0 else ""
        delta = f" ({sign}{score.score_delta_7d} vs last week)"

    lines = [
        f"# {supplier.name} — Supplier Risk Memo",
        "",
        f"**Score:** {score.score:.1f} / 10{delta}  ",
        f"**Status:** {headline}  ",
        f"**Computed:** {score.computed_at.isoformat(timespec='minutes')}",
        "",
        "## Top signals",
        "",
    ]
    if not score.top_signals:
        lines.append("_No material signals this week — no action required._")
    else:
        for i, sig in enumerate(score.top_signals, 1):
            cites = ", ".join(f"[{eid}]" for eid in sig.evidence_ids)
            lines.append(
                f"{i}. **{sig.dimension.replace('_', ' ').title()}** "
                f"(severity {sig.severity}/10, conf {sig.confidence:.0%}) — "
                f"{sig.description} {cites}"
            )
    lines += ["", "## Cited evidence", ""]
    cited_ids: list[str] = []
    for sig in score.top_signals:
        for eid in sig.evidence_ids:
            if eid not in cited_ids:
                cited_ids.append(eid)
    if not cited_ids:
        lines.append("_None._")
    else:
        for eid in cited_ids:
            rec = idx.get(eid)
            if not rec:
                continue
            title = rec.title or rec.source_url
            lines.append(f"- `[{eid}]` [{title}]({rec.source_url}) — {rec.source_type}, "
                         f"fetched {rec.fetched_at.isoformat(timespec='minutes')}")
    return "\n".join(lines) + "\n"


def _headline(score: RiskScore) -> str:
    if score.score >= 9.0:
        return "STOP — sanctions or bankruptcy signal"
    if score.score >= 7.0:
        return "Review required — multiple high-severity signals"
    if score.score >= 4.0:
        return "Watch — material signals present"
    if score.score >= 1.0:
        return "Stable — minor signals"
    return "Quiet — no change"
