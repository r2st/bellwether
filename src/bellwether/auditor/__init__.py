"""Auditor view — the single HTML page that lets a judge or auditor
verify that every score traces to a real source."""
from .index import load_latest_memos, render_index_page, write_index_page
from .renderer import render_audit_page, write_audit_page

__all__ = [
    "render_audit_page",
    "write_audit_page",
    "render_index_page",
    "write_index_page",
    "load_latest_memos",
]
