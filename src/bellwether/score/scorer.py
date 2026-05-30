"""Deterministic risk scorer — pure Python, no LLM.

The scorer is intentionally simple so the math is auditable. Granite
extracts; this scores. Judges (and auditors) can read 40 lines of code
and convince themselves how the number was reached.
"""
from __future__ import annotations

from ..models import Dimension, RiskScore, RiskSignal

# Tunable. Sanctions outweighs everything because a hit terminates the
# relationship. Operational chatter is noisy and weighted down.
DIMENSION_WEIGHTS: dict[Dimension, float] = {
    "sanctions": 1.0,
    "legal_exposure": 0.8,
    "financial_distress": 0.7,
    "leadership_churn": 0.5,
    "operational_chatter": 0.4,
}

# A single sanctions hit at severity 10 should pin the score at the cap.
_SANCTIONS_PIN = 10.0


def score_supplier(
    supplier_id: str,
    signals: list[RiskSignal],
    *,
    prior_score: float | None = None,
    top_n: int = 3,
) -> RiskScore:
    if any(s.dimension == "sanctions" and s.severity >= 8 for s in signals):
        raw = _SANCTIONS_PIN
    else:
        # weighted sum, confidence-discounted, then normalized to 0–10
        total = 0.0
        for s in signals:
            w = DIMENSION_WEIGHTS.get(s.dimension, 0.5)
            total += s.severity * w * s.confidence
        # 4 dimensions * sev 7 * weight 0.7 * conf 0.7 ≈ 13.7 → cap at 10
        raw = min(total, 10.0)

    top_signals = sorted(
        signals,
        key=lambda s: (s.severity * DIMENSION_WEIGHTS.get(s.dimension, 0.5)),
        reverse=True,
    )[:top_n]

    delta = None if prior_score is None else round(raw - prior_score, 2)

    return RiskScore(
        supplier_id=supplier_id,
        score=round(raw, 2),
        score_delta_7d=delta,
        top_signals=top_signals,
    )
