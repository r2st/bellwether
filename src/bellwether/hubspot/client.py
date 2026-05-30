"""HubSpot Private App client — supplier list read + Supplier Review ticket write.

Two paths to the CRM exist on Day 4 of the build plan:

1. This API client — deterministic, scriptable, idempotent. Always works.
2. Perplexity Comet driving the browser — the demo's "autonomous action"
   moment. Lives in `bellwether.comet`; calls this client as the fallback
   if Comet is unavailable.

Free-tier preflight (run once on the live tenant before counting on the demo):

  - Private App with scopes `tickets`, `files`, `crm.objects.companies.read`
    can be created and the token mints.
  - `POST /crm/v3/objects/tickets` returns 201.
  - `POST /files/v3/files` returns 201; the file attach association works.
  - Ticket owner assignment via `hubspot_owner_id` works on Free.

If file-attach or owner-assignment is blocked on the Free plan, the
caller can drop them — the ticket body still carries the memo markdown.
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import httpx

from ..models import Memo, Supplier


def _now_ms() -> int:
    """HubSpot's hs_timestamp wants ms since epoch (UTC)."""
    return int(datetime.now(timezone.utc).timestamp() * 1000)

HUBSPOT_BASE = "https://api.hubapi.com"

# HubSpot Files API folder where Bellwether memos live. Created on first upload.
BELLWETHER_FILES_FOLDER = "Bellwether"


class HubSpotError(RuntimeError):
    pass


class HubSpotClient:
    def __init__(self, private_app_token: str, *, timeout: float = 30.0) -> None:
        self.token = private_app_token
        self._client = httpx.Client(
            base_url=HUBSPOT_BASE,
            timeout=timeout,
            headers={
                "Authorization": f"Bearer {private_app_token}",
                "Content-Type": "application/json",
            },
        )

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> "HubSpotClient":
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    # ─── Read ─────────────────────────────────────────────────────────

    def list_suppliers(self, *, limit: int = 100) -> list[Supplier]:
        """List companies marked as suppliers in HubSpot.

        Convention: a company is a supplier if its `industry` or a custom
        property `is_supplier` is set. We default to "all companies" so
        the demo tenant doesn't need extra wiring — tighten this once you
        have a real supplier filter.
        """
        out: list[Supplier] = []
        after: str | None = None
        while True:
            params = {
                "limit": str(min(limit, 100)),
                "properties": "name,domain,hubspot_owner_id,linkedin_company_page",
            }
            if after:
                params["after"] = after
            r = self._client.get("/crm/v3/objects/companies", params=params)
            if r.status_code >= 400:
                raise HubSpotError(f"list_suppliers {r.status_code}: {r.text[:200]}")
            data = r.json()
            for row in data.get("results", []):
                props = row.get("properties", {})
                name = props.get("name") or "Unnamed company"
                out.append(Supplier(
                    id=_slug(name),
                    name=name,
                    domain=props.get("domain"),
                    hubspot_id=row.get("id"),
                    linkedin_url=props.get("linkedin_company_page"),
                ))
                if len(out) >= limit:
                    return out
            paging = data.get("paging", {}).get("next", {})
            after = paging.get("after")
            if not after:
                break
        return out

    def _company_owner(self, hubspot_id: str) -> str | None:
        """Return the company's hubspot_owner_id, if set."""
        r = self._client.get(
            f"/crm/v3/objects/companies/{hubspot_id}",
            params={"properties": "hubspot_owner_id"},
        )
        if r.status_code >= 400:
            return None
        return (r.json().get("properties") or {}).get("hubspot_owner_id")

    # ─── Write ────────────────────────────────────────────────────────

    def file_supplier_review_ticket(
        self,
        supplier: Supplier,
        memo: Memo,
        *,
        memo_dir: Path | None = None,
    ) -> str:
        """Create a Supplier Review ticket, attach the memo .md, assign the owner.

        Returns the ticket id. Idempotency: a deterministic subject line
        plus a pre-create search for an existing open ticket with the same
        subject avoid duplicates inside one morning's run.
        """
        if not supplier.hubspot_id:
            raise HubSpotError(
                f"Supplier {supplier.id} has no hubspot_id; cannot associate ticket"
            )

        subject = self._subject(supplier, memo)
        existing = self._find_open_ticket(subject)
        if existing:
            # Best-effort: still try to attach the file/owner to the existing one
            self._post_create(existing, supplier, memo, memo_dir)
            return existing

        priority = _priority_for(memo.score.score)
        owner_id = self._company_owner(supplier.hubspot_id)
        props: dict[str, str] = {
            "subject": subject,
            "content": memo.body_markdown,
            "hs_pipeline": "0",            # default support pipeline
            "hs_pipeline_stage": "1",      # "New"
            "hs_ticket_priority": priority,
        }
        if owner_id:
            props["hubspot_owner_id"] = owner_id

        payload = {
            "properties": props,
            "associations": [
                {
                    "to": {"id": supplier.hubspot_id},
                    "types": [
                        {"associationCategory": "HUBSPOT_DEFINED", "associationTypeId": 26}
                    ],
                }
            ],
        }
        r = self._client.post("/crm/v3/objects/tickets", json=payload)
        if r.status_code >= 400:
            raise HubSpotError(f"create_ticket {r.status_code}: {r.text[:200]}")
        ticket_id = r.json().get("id", "")
        self._post_create(ticket_id, supplier, memo, memo_dir)
        return ticket_id

    def _post_create(
        self,
        ticket_id: str,
        supplier: Supplier,
        memo: Memo,
        memo_dir: Path | None,
    ) -> None:
        """Best-effort memo attach. Logs (doesn't swallow) on failure."""
        if not ticket_id:
            return
        path = self._resolve_memo_path(supplier, memo, memo_dir)
        if not path or not path.exists():
            return
        try:
            file_id = self._upload_file(path)
            if file_id:
                self._attach_via_note(file_id, ticket_id, path.name)
        except HubSpotError as e:
            # Non-fatal: the memo body is already in the ticket `content`. But
            # don't disappear the error — h18 lost a demo beat to that.
            print(f"  ! Memo file attach failed (ticket {ticket_id}): {e}")

    @staticmethod
    def _resolve_memo_path(
        supplier: Supplier, memo: Memo, memo_dir: Path | None
    ) -> Path | None:
        if memo_dir is None:
            return None
        date = memo.generated_at.strftime("%Y-%m-%d")
        candidate = Path(memo_dir) / f"{supplier.id}-{date}.md"
        return candidate if candidate.exists() else None

    def _upload_file(self, path: Path) -> str | None:
        """Upload a file via the Files v3 API and return the file id.

        Uses a one-off httpx.Client so the multipart boundary header isn't
        clobbered by the long-lived client's `Content-Type: application/json`
        default (HubSpot returns 415 if the JSON content-type leaks through).
        """
        opts = (
            '{"access":"PRIVATE","overwrite":false,"folderPath":"'
            + BELLWETHER_FILES_FOLDER + '"}'
        )
        files = {
            "file": (path.name, path.read_bytes(), "text/markdown"),
            "options": (None, opts, "application/json"),
            "folderPath": (None, BELLWETHER_FILES_FOLDER),
        }
        with httpx.Client(
            base_url=HUBSPOT_BASE,
            timeout=30.0,
            headers={"Authorization": f"Bearer {self.token}"},
        ) as multipart:
            r = multipart.post("/files/v3/files", files=files)
        if r.status_code >= 400:
            raise HubSpotError(f"file_upload {r.status_code}: {r.text[:200]}")
        return r.json().get("id")

    def _attach_via_note(self, file_id: str, ticket_id: str, file_name: str) -> None:
        """Files attach to tickets via a Note engagement, not directly.

        HubSpot's CRM associations model has no Ticket↔File type — the
        Attachments rail on a ticket is rendered from files carried by
        associated engagement objects (Notes / Emails / Tasks / Meetings).
        We create a Note with `hs_attachment_ids = file_id`, then associate
        the note to the ticket via the v4 default Note↔Ticket type.
        """
        note_payload = {
            "properties": {
                "hs_timestamp": _now_ms(),
                "hs_note_body": f"Bellwether memo attached: {file_name}",
                "hs_attachment_ids": file_id,
            },
        }
        r = self._client.post("/crm/v3/objects/notes", json=note_payload)
        if r.status_code >= 400:
            raise HubSpotError(f"create_note {r.status_code}: {r.text[:200]}")
        note_id = r.json().get("id", "")
        if not note_id:
            raise HubSpotError(f"create_note returned no id: {r.text[:200]}")

        r = self._client.put(
            f"/crm/v4/objects/notes/{note_id}/associations/default/tickets/{ticket_id}"
        )
        if r.status_code >= 400:
            raise HubSpotError(
                f"associate_note_to_ticket {r.status_code}: {r.text[:200]}"
            )

    # ─── Internals ────────────────────────────────────────────────────

    def _subject(self, supplier: Supplier, memo: Memo) -> str:
        date = memo.generated_at.strftime("%Y-%m-%d")
        return f"[Bellwether] {supplier.name} — risk {memo.score.score:.1f}/10 — {date}"

    def _find_open_ticket(self, subject: str) -> str | None:
        payload = {
            "filterGroups": [{
                "filters": [
                    {"propertyName": "subject", "operator": "EQ", "value": subject},
                    {"propertyName": "hs_pipeline_stage", "operator": "NEQ", "value": "4"},
                ]
            }],
            "properties": ["subject"],
            "limit": 1,
        }
        r = self._client.post("/crm/v3/objects/tickets/search", json=payload)
        if r.status_code >= 400:
            # search is best-effort for idempotency; don't kill the write path
            return None
        results = r.json().get("results", [])
        return results[0].get("id") if results else None


def _slug(name: str) -> str:
    out = []
    for ch in name.lower():
        if ch.isalnum():
            out.append(ch)
        elif out and out[-1] != "-":
            out.append("-")
    return "".join(out).strip("-")[:64] or "supplier"


def _priority_for(score: float) -> str:
    # HubSpot priorities: LOW, MEDIUM, HIGH
    if score >= 7.0:
        return "HIGH"
    if score >= 4.0:
        return "MEDIUM"
    return "LOW"
