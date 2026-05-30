"""CrewAI orchestration — one crew of four agents per supplier.

The crew wraps Bellwether's existing pipeline pieces as CrewAI Tools so the
agent flow is visually legible to demo judges. Real LLM-backed execution
needs `cfg.AMD_INFERENCE_URL` set (the Granite vLLM endpoint); if no LLM is
configured the runner falls back to a sequential tool invocation that still
exercises every Tool and produces an identical Memo.

The four agents and their exclusive contracts:

    Researcher    →  Bright Data SERP + LinkedIn evidence
    Compliance    →  OFAC SDN deterministic match (never via LLM)
    Analyst       →  Granite extraction over the gathered evidence
    Writer        →  deterministic scorer + cited Markdown memo

This resolves the role-overlap risk flagged in the research notes
(researcher vs watchman) by collapsing watchman into Researcher and giving
Compliance the exclusive sanctions path.
"""
from .crew import build_crew, run_crew_for_supplier

__all__ = ["build_crew", "run_crew_for_supplier"]
