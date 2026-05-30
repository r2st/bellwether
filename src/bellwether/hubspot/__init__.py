"""HubSpot adapter — read the supplier list, file Supplier Review tickets."""
from .client import HubSpotClient, HubSpotError

__all__ = ["HubSpotClient", "HubSpotError"]
