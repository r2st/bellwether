"""Scorer is the only deterministic auditable piece — pin its behavior."""
from __future__ import annotations

from bellwether.models import RiskSignal
from bellwether.score.scorer import score_supplier


def _sig(dim, sev, conf=1.0, eid="ev1"):
    return RiskSignal(
        dimension=dim, severity=sev, confidence=conf,
        description="x", evidence_ids=[eid],
    )


def test_no_signals_zero_score():
    score = score_supplier("acme", [])
    assert score.score == 0.0
    assert score.top_signals == []


def test_sanctions_pins_score_at_ten():
    signals = [
        _sig("sanctions", 10),
        _sig("operational_chatter", 2),
    ]
    score = score_supplier("acme", signals)
    assert score.score == 10.0
    # sanctions is the top signal
    assert score.top_signals[0].dimension == "sanctions"


def test_weighted_sum_clamps_at_ten():
    # 5 mid-severity signals across dimensions would naively exceed 10
    signals = [
        _sig("legal_exposure", 7),
        _sig("financial_distress", 7),
        _sig("leadership_churn", 7),
        _sig("operational_chatter", 7),
    ]
    score = score_supplier("acme", signals)
    assert 0.0 <= score.score <= 10.0


def test_confidence_discounts_score():
    high = score_supplier("acme", [_sig("financial_distress", 8, conf=1.0)])
    low = score_supplier("acme", [_sig("financial_distress", 8, conf=0.5)])
    assert high.score > low.score


def test_top_signals_truncates_to_n():
    signals = [_sig("financial_distress", i) for i in range(8, 0, -1)]
    score = score_supplier("acme", signals, top_n=3)
    assert len(score.top_signals) == 3
    # ordered by severity desc
    assert score.top_signals[0].severity >= score.top_signals[1].severity
