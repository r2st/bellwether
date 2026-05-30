# Bellwether MCP server

Read-only MCP server exposing Bellwether risk memos to any MCP-speaking
agent — Claude Desktop, Cursor, custom clients.

## What it exposes

Two tools, both read-only:

- `query_supplier_risk(supplier_id)` — latest cited memo for one supplier
- `list_suppliers()` — index of suppliers with memos in the local store

The server reads from `./memos/` (or `$BELLWETHER_MEMO_DIR` if set). It
does **not** trigger a pipeline run — the buyer's morning batch is what
populates the memos. That keeps the auditable contract intact: every
score still came from the deterministic scorer, not from MCP-time
recomputation.

## Run standalone

```bash
# from Bellwether/, with .venv activated
python -m bellwether.mcp.server
# or, via the installed entry point:
bellwether-mcp
```

## Wire into Claude Desktop

Add to `~/Library/Application Support/Claude/claude_desktop_config.json`
(macOS) or the equivalent on your OS:

```json
{
  "mcpServers": {
    "bellwether": {
      "command": "/absolute/path/to/Bellwether/.venv/bin/bellwether-mcp",
      "env": {
        "BELLWETHER_MEMO_DIR": "/absolute/path/to/Bellwether/memos"
      }
    }
  }
}
```

Restart Claude Desktop. The two tools appear in the tools panel; try:

> What's the current supplier risk on acme-electronics?

Claude will call `query_supplier_risk("acme-electronics")` and return
the score, the top three cited signals, and the rendered memo.

## Why read-only

Bellwether's pitch is *auditable* scoring — deterministic Python over
LLM-extracted signals. If the MCP server could re-score on demand, the
"every score is auditable" claim would dilute. Read-only keeps the
morning batch as the single source of truth.

If you need a fresh score from MCP, the right pattern is to call the
existing CLI as a subprocess and *then* call `query_supplier_risk` —
the server doesn't blur that boundary.
