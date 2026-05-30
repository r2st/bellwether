from __future__ import annotations

import json
from pathlib import Path

from ..models import Supplier

SUPPLIERS_FILE = Path(__file__).resolve().parent / "suppliers.json"


def load_suppliers() -> list[Supplier]:
    data = json.loads(SUPPLIERS_FILE.read_text())
    return [Supplier(**row) for row in data]


def get_supplier(supplier_id: str) -> Supplier | None:
    for s in load_suppliers():
        if s.id == supplier_id:
            return s
    return None
