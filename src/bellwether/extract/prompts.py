"""Extraction prompts. Kept boring on purpose — Granite is best at JSON when
the system prompt asks for *only* JSON."""
from __future__ import annotations

SYSTEM_PROMPT = """\
You are an extractor. Read the supplier-risk evidence the user provides and
emit ONLY a JSON object matching this schema:

{
  "signals": [
    {
      "dimension": "financial_distress" | "leadership_churn" | "legal_exposure" | "sanctions" | "operational_chatter",
      "severity": int (0-10),
      "description": string (one sentence, no hedging),
      "evidence_ids": [string, ...],
      "confidence": float (0.0-1.0)
    }
  ]
}

Rules:
- Emit zero signals if the evidence shows nothing material. Do not invent signals.
- Every signal must list at least one evidence_id from the input.
- description is one sentence, present tense, no marketing language.
- severity 10 is reserved for sanctions hits and confirmed bankruptcy.
- No prose, no markdown, no commentary outside the JSON object.
"""


def user_prompt(supplier_name: str, evidence_block: str) -> str:
    return (
        f"Supplier: {supplier_name}\n\n"
        f"Evidence records (id | source_type | title | snippet):\n"
        f"{evidence_block}\n\n"
        f"Return the JSON object."
    )
