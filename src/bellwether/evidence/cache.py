"""Provenance-preserving disk cache for evidence.

Bright Data calls are billable AND rate-limited. Cache every raw response
so that re-runs (and demos) don't repeat the work. The cache key is the
exact source URL — never the prompt, never the supplier — so the same
URL fetched for two suppliers is cached once.
"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from ..models import EvidenceRecord


class EvidenceCache:
    def __init__(self, root: Path) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, record_id: str) -> Path:
        # 2-level prefix dir keeps any single dir from getting fat
        return self.root / record_id[:2] / f"{record_id}.json"

    def has(self, record_id: str) -> bool:
        return self._path(record_id).exists()

    def get(self, record_id: str) -> EvidenceRecord | None:
        path = self._path(record_id)
        if not path.exists():
            return None
        return EvidenceRecord.model_validate_json(path.read_text())

    def put(self, record: EvidenceRecord) -> EvidenceRecord:
        path = self._path(record.id)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(record.model_dump_json(indent=2))
        return record

    def list_for_supplier(self, supplier_id: str) -> list[EvidenceRecord]:
        out: list[EvidenceRecord] = []
        for path in self.root.rglob("*.json"):
            try:
                rec = EvidenceRecord.model_validate_json(path.read_text())
            except Exception:
                continue
            if rec.supplier_id == supplier_id:
                out.append(rec)
        out.sort(key=lambda r: r.fetched_at, reverse=True)
        return out
