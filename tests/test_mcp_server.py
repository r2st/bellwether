"""Pin the MCP server contract: tool names + Acme memo shape.

The deck's closing slide promises 'MCP-native · query from Claude Desktop.'
This test guards that promise — a future refactor that breaks the tool
shape or the supplier lookup will fail here, not at the finale.
"""
from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path

import pytest

from bellwether.mcp.server import app

MEMO_DIR = Path(__file__).parent.parent / "memos"


@pytest.fixture(autouse=True)
def _point_at_repo_memos(monkeypatch):
    """Force the server to read from the repo's memos/ regardless of CWD."""
    monkeypatch.setenv("BELLWETHER_MEMO_DIR", str(MEMO_DIR))


def _call(name: str, args: dict):
    return asyncio.run(app.call_tool(name, args))


def _payload(result):
    """Unwrap a FastMCP call_tool return into native Python.

    FastMCP returns either:
      - list[TextContent] for dict-returning tools, or
      - (list[TextContent], {"result": [...]}) for list-returning tools.
    Prefer the structured payload when present; otherwise parse the text.
    """
    if isinstance(result, tuple):
        _, structured = result
        return structured["result"] if "result" in structured else structured
    text = result[0].text if isinstance(result, list) else result
    return json.loads(text)


def test_tools_registered():
    tools = asyncio.run(app.list_tools())
    names = {t.name for t in tools}
    assert "query_supplier_risk" in names
    assert "list_suppliers" in names


def test_acme_memo_has_signals_and_sources():
    payload = _payload(_call("query_supplier_risk", {"supplier_id": "acme-electronics"}))
    assert payload["supplier_id"] == "acme-electronics"
    assert payload["score"] > 0
    assert payload["top_signals"], "Acme demo memo must have signals"
    # Every signal must carry at least one cited source (the auditable claim)
    for signal in payload["top_signals"]:
        assert signal["sources"], f"signal {signal['dimension']} has no sources"
        for src in signal["sources"]:
            assert src["url"].startswith("http"), "source URLs must be real-looking"


def test_unknown_supplier_returns_error_not_exception():
    payload = _payload(_call("query_supplier_risk", {"supplier_id": "nonexistent-co"}))
    assert "error" in payload
    assert "nonexistent-co" in payload["error"]


def test_list_suppliers_includes_demo_trio():
    payload = _payload(_call("list_suppliers", {}))
    ids = {row["supplier_id"] for row in payload}
    assert {"acme-electronics", "bluewave-cm", "tranquil-corp"} <= ids
