"""Evidence layer — live web collection with provenance."""
from .cache import EvidenceCache
from .collectors import collect_all

__all__ = ["EvidenceCache", "collect_all"]
