"""Canonical list of the 10 domain modules (constitution, foundational decision).

Single source of truth for router registration and boundary verification.
"""

from typing import Final

DOMAIN_MODULES: Final[tuple[str, ...]] = (
    "auth",
    "employees",
    "tourists",
    "tourist_spots",
    "events",
    "gamification",
    "visitation",
    "dashboard",
    "notifications",
    "chatbot",
)
