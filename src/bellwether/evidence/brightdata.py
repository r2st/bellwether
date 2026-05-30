"""Thin Bright Data API client.

Three surfaces we use:
  - SERP API (POST /request, zone=serp_zone)         → news search
  - Web Unlocker (POST /request, zone=unlocker_zone) → arbitrary URL fetch
  - Datasets (POST /datasets/v3/trigger + poll)      → LinkedIn company pages

The exact request shape is verified at runtime — if Bright Data changes
the payload format, only this file changes.
"""
from __future__ import annotations

import asyncio
from typing import Any

import httpx

BRIGHTDATA_BASE = "https://api.brightdata.com"


class BrightDataError(RuntimeError):
    pass


class BrightDataClient:
    def __init__(
        self,
        api_token: str,
        serp_zone: str,
        unlocker_zone: str,
        linkedin_dataset_id: str,
        timeout: float = 60.0,
    ) -> None:
        self.api_token = api_token
        self.serp_zone = serp_zone
        self.unlocker_zone = unlocker_zone
        self.linkedin_dataset_id = linkedin_dataset_id
        self._client = httpx.AsyncClient(
            timeout=timeout,
            headers={"Authorization": f"Bearer {api_token}"},
        )

    async def aclose(self) -> None:
        await self._client.aclose()

    async def serp(self, query: str, *, country: str = "us", num: int = 10) -> dict[str, Any]:
        """News-flavored SERP. Returns Bright Data's JSON envelope."""
        payload = {
            "zone": self.serp_zone,
            "url": f"https://www.google.com/search?q={httpx.QueryParams({'q': query})['q']}&tbm=nws&num={num}&gl={country}",
            "format": "json",
        }
        r = await self._client.post(f"{BRIGHTDATA_BASE}/request", json=payload)
        if r.status_code >= 400:
            raise BrightDataError(f"SERP {r.status_code}: {r.text[:200]}")
        return r.json()

    async def fetch_url(self, url: str) -> str:
        """Web Unlocker — fetch arbitrary URL HTML."""
        payload = {
            "zone": self.unlocker_zone,
            "url": url,
            "format": "raw",
        }
        r = await self._client.post(f"{BRIGHTDATA_BASE}/request", json=payload)
        if r.status_code >= 400:
            raise BrightDataError(f"Unlocker {r.status_code}: {r.text[:200]}")
        return r.text

    async def linkedin_company(
        self, company_url: str, *, poll_interval: float = 5.0, max_wait: float = 180.0
    ) -> dict[str, Any]:
        """Trigger LinkedIn dataset for one company URL and poll until ready."""
        trigger = await self._client.post(
            f"{BRIGHTDATA_BASE}/datasets/v3/trigger",
            params={"dataset_id": self.linkedin_dataset_id, "include_errors": "true"},
            json=[{"url": company_url}],
        )
        if trigger.status_code >= 400:
            raise BrightDataError(f"LinkedIn trigger {trigger.status_code}: {trigger.text[:200]}")
        snapshot_id = trigger.json().get("snapshot_id")
        if not snapshot_id:
            raise BrightDataError(f"No snapshot_id in trigger response: {trigger.json()}")

        waited = 0.0
        while waited < max_wait:
            await asyncio.sleep(poll_interval)
            waited += poll_interval
            status = await self._client.get(
                f"{BRIGHTDATA_BASE}/datasets/v3/progress/{snapshot_id}"
            )
            if status.json().get("status") == "ready":
                break
        else:
            raise BrightDataError(f"LinkedIn snapshot {snapshot_id} did not become ready in {max_wait}s")

        data = await self._client.get(
            f"{BRIGHTDATA_BASE}/datasets/v3/snapshot/{snapshot_id}",
            params={"format": "json"},
        )
        if data.status_code >= 400:
            raise BrightDataError(f"LinkedIn fetch {data.status_code}: {data.text[:200]}")
        rows = data.json()
        return rows[0] if isinstance(rows, list) and rows else {}
