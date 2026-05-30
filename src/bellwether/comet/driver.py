"""Comet driver — gated stub with clear error contract.

We don't bake in the Perplexity Comet SDK call shape here because Comet's
public SDK was still in flux as of the hackathon window. The contract is:

  - If `PERPLEXITY_COMET_SESSION_TOKEN` is unset → raise CometUnavailable.
    The caller silently falls back to the HubSpot REST path.
  - If the token is set but anything in the browser flow fails → raise
    CometError with the upstream message. The caller logs and falls back.
  - On success → return the path to a screenshot of the filed ticket.

When the actual SDK is ready, replace the body of `_drive_comet` with the
real calls. Nothing else in this module needs to change.
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from .. import config as cfg
from ..models import Memo, Supplier


class CometUnavailable(RuntimeError):
    """Comet is not configured. Caller should fall back silently."""


class CometError(RuntimeError):
    """Comet was attempted but the browser flow failed. Caller should log + fall back."""


def file_ticket_via_comet(
    memo: Memo,
    supplier: Supplier,
    *,
    portal_id: str | None = None,
    out_dir: Path | None = None,
) -> Path:
    """Drive Perplexity Comet to file the Supplier Review ticket in HubSpot.

    Returns the path to the screenshot recorded mid-flow (used in the demo
    as visual proof the agent took the action). On failure raises CometError
    or CometUnavailable per the module contract.
    """
    token = cfg.PERPLEXITY_COMET_SESSION_TOKEN
    if not token:
        raise CometUnavailable("PERPLEXITY_COMET_SESSION_TOKEN is not set")

    portal_id = portal_id or cfg.HUBSPOT_PORTAL_ID
    if not portal_id:
        raise CometError("Comet needs HUBSPOT_PORTAL_ID to navigate to the right tenant")
    if not supplier.hubspot_id:
        raise CometError(f"Supplier {supplier.id} has no hubspot_id; Comet has nothing to open")

    out_dir = Path(out_dir or "./memos")
    out_dir.mkdir(parents=True, exist_ok=True)
    date = memo.generated_at.strftime("%Y-%m-%d")
    screenshot_path = out_dir / f"{supplier.id}-{date}.comet.png"

    try:
        _drive_comet(
            token=token,
            portal_id=portal_id,
            hubspot_company_id=supplier.hubspot_id,
            subject=_subject(supplier, memo),
            body=memo.body_markdown,
            screenshot_path=screenshot_path,
        )
    except CometUnavailable:
        raise
    except CometError:
        raise
    except Exception as e:  # surface anything upstream as CometError so caller falls back
        raise CometError(f"Comet flow failed: {type(e).__name__}: {e}") from e

    return screenshot_path


def _subject(supplier: Supplier, memo: Memo) -> str:
    date = memo.generated_at.strftime("%Y-%m-%d")
    return f"[Bellwether] {supplier.name} — risk {memo.score.score:.1f}/10 — {date}"


def _drive_comet(
    *,
    token: str,
    portal_id: str,
    hubspot_company_id: str,
    subject: str,
    body: str,
    screenshot_path: Path,
) -> None:
    """The actual Comet calls. STUB until the Perplexity SDK shape lands.

    Wire-up checklist when the SDK is available:
      1. Create a Comet session with `token`.
      2. Open `https://app.hubspot.com/contacts/{portal_id}/company/{hubspot_company_id}`.
      3. Wait for the right panel; click "Create" → "Ticket".
      4. Fill subject, paste body, set priority based on score band.
      5. Save; screenshot the resulting ticket view to `screenshot_path`.
      6. Close the Comet session.
    """
    raise CometError(
        "Comet SDK call not wired yet — set PERPLEXITY_COMET_SESSION_TOKEN to empty "
        "to use the HubSpot REST fallback, or implement _drive_comet against the "
        "current Perplexity Comet SDK."
    )
