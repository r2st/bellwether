"""Central config — loads ../../../keys/.env and exposes typed constants.

Secrets live OUTSIDE the Bellwether project tree (in the sibling `keys/`
folder) so the submission deliverable can be zipped or pushed without
dragging tokens along. Import this module anywhere in the package
instead of touching os.environ directly:

    from bellwether import config
    headers = {"Authorization": f"Bearer {config.BRIGHTDATA_API_TOKEN}"}

Run `bellwether verify` (or `python -m bellwether.config`) to check which
tokens are still missing.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

try:
    from dotenv import load_dotenv
except ImportError:
    print("dotenv not installed — run: pip install python-dotenv", file=sys.stderr)
    raise

# this file: Hackathons/Bellwether/src/bellwether/config.py
# secrets:   Hackathons/keys/.env
ENV_FILE = Path(__file__).resolve().parents[3] / "keys" / ".env"
load_dotenv(ENV_FILE)


_MISSING: list[str] = []


def _req(name: str) -> str:
    val = os.environ.get(name, "").strip()
    if not val or val == "REPLACE_ME":
        _MISSING.append(name)
    return val


def _opt(name: str, default: str = "") -> str:
    return os.environ.get(name, default).strip()


# Bright Data
BRIGHTDATA_API_TOKEN = _req("BRIGHTDATA_API_TOKEN")
BRIGHTDATA_SERP_ZONE = _req("BRIGHTDATA_SERP_ZONE")
BRIGHTDATA_LINKEDIN_DATASET_ID = _req("BRIGHTDATA_LINKEDIN_DATASET_ID")
BRIGHTDATA_WEB_UNLOCKER_ZONE = _opt("BRIGHTDATA_WEB_UNLOCKER_ZONE")

# AMD / model host
AMD_DEVCLOUD_API_KEY = _req("AMD_DEVCLOUD_API_KEY")
AMD_INFERENCE_URL = _req("AMD_INFERENCE_URL")
AMD_INFERENCE_MODEL = _opt("AMD_INFERENCE_MODEL", "ibm-granite/granite-3.1-8b-instruct")

# Perplexity Comet
PERPLEXITY_API_KEY = _req("PERPLEXITY_API_KEY")
PERPLEXITY_COMET_SESSION_TOKEN = _opt("PERPLEXITY_COMET_SESSION_TOKEN") or _opt(
    "PERPLEXITY_COMPUTER_SESSION_TOKEN"
)

# HubSpot (demo CRM)
HUBSPOT_PRIVATE_APP_TOKEN = _req("HUBSPOT_PRIVATE_APP_TOKEN")
HUBSPOT_PORTAL_ID = _req("HUBSPOT_PORTAL_ID")

# Hugging Face
HF_TOKEN = _req("HF_TOKEN")

# Optional
LANGSMITH_API_KEY = _opt("LANGSMITH_API_KEY")
LANGSMITH_PROJECT = _opt("LANGSMITH_PROJECT", "bellwether")

# Runtime
APP_ENV = _opt("APP_ENV", "dev")
LOG_LEVEL = _opt("LOG_LEVEL", "INFO")
EVIDENCE_CACHE_DIR = Path(_opt("EVIDENCE_CACHE_DIR", "./.cache/evidence"))
MEMO_OUTPUT_DIR = Path(_opt("MEMO_OUTPUT_DIR", "./memos"))


def verify() -> bool:
    if not ENV_FILE.exists():
        print(f"No .env at {ENV_FILE}. Copy keys/.env.example to keys/.env and fill it in.")
        return False
    if _MISSING:
        print(f"Missing or unset secrets in {ENV_FILE}:")
        for name in _MISSING:
            print(f"  - {name}")
        return False
    print(f"OK — all required tokens set ({ENV_FILE}).")
    return True


if __name__ == "__main__":
    sys.exit(0 if verify() else 1)
