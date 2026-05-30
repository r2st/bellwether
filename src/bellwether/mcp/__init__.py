"""MCP server — exposes Bellwether's risk memos to any MCP-speaking agent.

The closing slide of the deck promises "MCP-native · query from Claude
Desktop." This module is the backing implementation: a read-only tool
that returns the latest cited memo for a supplier.

See `server.py` for the FastMCP app definition and `README.md` in this
folder for the Claude Desktop config snippet.
"""
from .server import app, list_suppliers, main, query_supplier_risk

__all__ = ["app", "list_suppliers", "main", "query_supplier_risk"]
