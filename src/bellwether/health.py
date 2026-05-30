"""Provider health check — `bellwether ping`.

Hits each configured provider with the smallest possible call and reports
green/red. Removes 90% of demo-day failure mystery: if ping is green, the
demo will work; if ping is red, fix that first.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

import httpx

from . import config as cfg


@dataclass
class HealthCheck:
    name: str
    ok: bool
    detail: str


def check_brightdata() -> HealthCheck:
    if not cfg.BRIGHTDATA_API_TOKEN:
        return HealthCheck("Bright Data", False, "no token set in keys/.env")
    try:
        r = httpx.get(
            "https://api.brightdata.com/status",
            headers={"Authorization": f"Bearer {cfg.BRIGHTDATA_API_TOKEN}"},
            timeout=10.0,
        )
        if r.status_code != 200:
            return HealthCheck("Bright Data", False, f"auth status {r.status_code}")

        # Auth works — also confirm the zones the collectors need are present.
        zr = httpx.get(
            "https://api.brightdata.com/zone/get_active_zones",
            headers={"Authorization": f"Bearer {cfg.BRIGHTDATA_API_TOKEN}"},
            timeout=10.0,
        )
        if zr.status_code != 200:
            return HealthCheck("Bright Data", True, f"auth OK; zones probe {zr.status_code} (token may lack zone read)")
        active = {z.get("name") for z in zr.json() if isinstance(z, dict)}
        if not active:
            return HealthCheck(
                "Bright Data",
                False,
                "auth OK but no zones exist — create a SERP and Web Unlocker zone in the BD dashboard "
                "(https://brightdata.com/cp/zones) and paste names into BRIGHTDATA_SERP_ZONE / _WEB_UNLOCKER_ZONE",
            )
        # SERP is required by the live pipeline; Web Unlocker is reserved for
        # future collectors and only warned about.
        def _bad(val: str) -> bool:
            return (not val) or val == "REPLACE_ME" or val not in active

        if _bad(cfg.BRIGHTDATA_SERP_ZONE):
            return HealthCheck(
                "Bright Data",
                False,
                f"BRIGHTDATA_SERP_ZONE unset or not in account zones {sorted(active)}",
            )
        detail = f"auth + SERP zone OK ({sorted(active)})"
        if _bad(cfg.BRIGHTDATA_WEB_UNLOCKER_ZONE):
            detail += " — Web Unlocker zone unset (optional; not on active pipeline)"
        return HealthCheck("Bright Data", True, detail)
    except httpx.HTTPError as e:
        return HealthCheck("Bright Data", False, f"{type(e).__name__}: {e}")


def check_granite() -> HealthCheck:
    if not cfg.AMD_INFERENCE_URL:
        return HealthCheck("AMD / Granite", False, "no AMD_INFERENCE_URL set")
    try:
        # vLLM exposes /v1/models — list call confirms server is alive
        r = httpx.get(f"{cfg.AMD_INFERENCE_URL.rstrip('/')}/models", timeout=10.0)
        if r.status_code == 200:
            models = [m.get("id") for m in r.json().get("data", [])]
            present = cfg.AMD_INFERENCE_MODEL in models
            return HealthCheck(
                "AMD / Granite",
                present,
                f"models: {models}" if present else f"{cfg.AMD_INFERENCE_MODEL} not served (got {models})",
            )
        return HealthCheck("AMD / Granite", False, f"status {r.status_code}")
    except httpx.HTTPError as e:
        return HealthCheck("AMD / Granite", False, f"{type(e).__name__}: {e}")


def check_hubspot() -> HealthCheck:
    if not cfg.HUBSPOT_PRIVATE_APP_TOKEN:
        return HealthCheck("HubSpot", False, "no token set in keys/.env")
    try:
        r = httpx.get(
            "https://api.hubapi.com/crm/v3/objects/companies",
            headers={"Authorization": f"Bearer {cfg.HUBSPOT_PRIVATE_APP_TOKEN}"},
            params={"limit": "1"},
            timeout=10.0,
        )
        if r.status_code == 200:
            return HealthCheck("HubSpot", True, "auth OK")
        return HealthCheck("HubSpot", False, f"status {r.status_code}: {r.text[:120]}")
    except httpx.HTTPError as e:
        return HealthCheck("HubSpot", False, f"{type(e).__name__}: {e}")


def check_ofac() -> HealthCheck:
    # OFAC is public; we just confirm the URL is reachable
    from .evidence.collectors import OFAC_SDN_URL
    try:
        r = httpx.head(OFAC_SDN_URL, timeout=15.0, follow_redirects=True)
        if r.status_code < 400:
            return HealthCheck("OFAC SDN list", True, "reachable")
        return HealthCheck("OFAC SDN list", False, f"status {r.status_code}")
    except httpx.HTTPError as e:
        return HealthCheck("OFAC SDN list", False, f"{type(e).__name__}: {e}")


def check_hf() -> HealthCheck:
    if not cfg.HF_TOKEN:
        return HealthCheck("Hugging Face", False, "no token set")
    try:
        r = httpx.get(
            "https://huggingface.co/api/whoami-v2",
            headers={"Authorization": f"Bearer {cfg.HF_TOKEN}"},
            timeout=10.0,
        )
        if r.status_code == 200:
            user = r.json().get("name", "anon")
            return HealthCheck("Hugging Face", True, f"as {user}")
        return HealthCheck("Hugging Face", False, f"status {r.status_code}")
    except httpx.HTTPError as e:
        return HealthCheck("Hugging Face", False, f"{type(e).__name__}: {e}")


CHECKS: list[Callable[[], HealthCheck]] = [
    check_brightdata,
    check_granite,
    check_hubspot,
    check_ofac,
    check_hf,
]


def run_all() -> list[HealthCheck]:
    return [c() for c in CHECKS]
