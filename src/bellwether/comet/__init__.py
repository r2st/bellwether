"""Perplexity Comet driver — the "agent files the ticket in-browser" beat.

Public surface:

    from bellwether.comet import file_ticket_via_comet, CometUnavailable, CometError

    try:
        screenshot = file_ticket_via_comet(memo, supplier, portal_id=...)
    except CometUnavailable:
        # token not set / Comet not invokable — caller falls back to HubSpot REST
        ...
    except CometError as e:
        # token was set but the browser flow failed mid-run — caller falls back too
        ...

Two distinct errors so the caller can distinguish "Comet not configured"
(silent fallback expected) from "Comet was attempted and failed" (worth a
log line at WARN level).
"""
from .driver import CometError, CometUnavailable, file_ticket_via_comet

__all__ = ["file_ticket_via_comet", "CometError", "CometUnavailable"]
