"""FastMCP server exposing Bellwether risk memos.

One tool: `query_supplier_risk(supplier_id)`. Reads the latest memo for
the supplier from `./memos/` (the same directory `bellwether run` writes
to) and returns the score, the 7-day delta, the top signals with their
cited evidence URLs, and the full memo markdown.

Read-only by design. The server does NOT trigger a new pipeline run —
the buyer's morning batch is what populates the memos. This keeps the
auditable contract intact: every score still came from the deterministic
scorer, not from an MCP-time recomputation.

Run standalone:
    python -m bellwether.mcp.server

Or via the installed entry point:
    bellwether-mcp
"""
from __future__ import annotations

from pathlib import Path

from mcp.server.fastmcp import FastMCP

from ..models import Memo

app = FastMCP("bellwether")

MEMO_DIR_ENV = "BELLWETHER_MEMO_DIR"


def _memo_dir() -> Path:
    """Where to look for memos. Defaults to ./memos relative to CWD."""
    import os

    return Path(os.environ.get(MEMO_DIR_ENV, "./memos"))


@app.tool()
def query_supplier_risk(supplier_id: str) -> dict:
    """Return Bellwether's latest cited risk memo for a supplier.

    Args:
        supplier_id: Supplier identifier — e.g. "acme-electronics".

    Returns the latest memo as a dict with the score, 7-day delta, top
    signals (each with description, severity, and source URLs), and the
    rendered memo markdown.
    """
    memo_dir = _memo_dir()
    candidates = sorted(memo_dir.glob(f"{supplier_id}-*.json"), reverse=True)
    if not candidates:
        return {
            "error": f"No memo for {supplier_id}",
            "hint": (
                f"Run `bellwether run --supplier {supplier_id} --mock` first, "
                f"or set {MEMO_DIR_ENV} to point at a populated memo directory."
            ),
        }

    memo = Memo.model_validate_json(candidates[0].read_text())
    evidence_by_id = {e.id: e for e in memo.evidence}

    return {
        "supplier_id": memo.supplier.id,
        "supplier_name": memo.supplier.name,
        "score": memo.score.score,
        "delta_7d": memo.score.score_delta_7d,
        "top_signals": [
            {
                "dimension": s.dimension,
                "severity": s.severity,
                "description": s.description,
                "sources": [
                    {
                        "url": evidence_by_id[eid].source_url,
                        "fetched_at": evidence_by_id[eid].fetched_at.isoformat(),
                    }
                    for eid in s.evidence_ids
                    if eid in evidence_by_id
                ],
            }
            for s in memo.score.top_signals
        ],
        "memo_markdown": memo.body_markdown,
        "generated_at": memo.generated_at.isoformat(),
    }


@app.tool()
def list_suppliers() -> list[dict]:
    """List every supplier with a memo in the local memo directory."""
    memo_dir = _memo_dir()
    seen: dict[str, dict] = {}
    for path in sorted(memo_dir.glob("*-*.json"), reverse=True):
        try:
            memo = Memo.model_validate_json(path.read_text())
        except Exception:
            continue
        sid = memo.supplier.id
        if sid not in seen:
            seen[sid] = {
                "supplier_id": sid,
                "supplier_name": memo.supplier.name,
                "latest_score": memo.score.score,
                "delta_7d": memo.score.score_delta_7d,
                "memo_date": memo.generated_at.date().isoformat(),
            }
    return list(seen.values())


def main() -> None:
    """Entry point for the `bellwether-mcp` script."""
    app.run()


if __name__ == "__main__":
    main()
