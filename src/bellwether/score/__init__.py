"""Risk scoring — deterministic weighted sum over RiskSignals."""
from .scorer import score_supplier, DIMENSION_WEIGHTS

__all__ = ["score_supplier", "DIMENSION_WEIGHTS"]
