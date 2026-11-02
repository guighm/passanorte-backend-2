"""Module public service interface (the only cross-module importable surface)."""

from passanorte_back.modules.events.services.events import list_public_spot_events

__all__ = ["list_public_spot_events"]
