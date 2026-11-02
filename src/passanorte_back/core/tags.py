"""Central registry of OpenAPI/Swagger tags (feature 006; core/tags.py).

Single source of truth for the API documentation tags: exactly one tag per
canonical domain module (``core/modules.py``, constitution preamble rule 2)
plus one infrastructure tag (``INFRASTRUCTURE_TAG``) for core-owned
non-domain routes (``GET /health``).

``OPENAPI_TAGS_METADATA`` is handed directly to ``FastAPI(openapi_tags=...)``
in ``main.py`` — names, descriptions and display order (domain tags in the
canonical ``DOMAIN_MODULES`` order, ``Health`` last). Domain routers get
their tag at the single router creation point (``core/routers.py``); module
route files never write a tag string.

Descriptions are developer-facing English documentation content (spec 006
FR-009). The registry is a hand-written catalog, not mechanically derived
from ``DOMAIN_MODULES``; ``tests/contract/test_openapi_tags.py`` verifies the
1:1 alignment (spec 006 clarification Q3).
"""

from typing import Final, TypedDict

from passanorte_back.core.modules import DOMAIN_MODULES


class TagMetadata(TypedDict):
    """One OpenAPI tag entry as consumed by ``FastAPI(openapi_tags=...)``."""

    name: str
    description: str


# Infrastructure tag for core-owned, non-domain routes (today: GET /health).
INFRASTRUCTURE_TAG: Final[str] = "Health"

DOMAIN_TAG_NAMES: Final[tuple[str, ...]] = (
    "Auth",
    "Employees",
    "Tourists",
    "Tourist Spots",
    "Events",
    "Gamification",
    "Visitation",
    "Dashboard",
    "Notifications",
    "Chatbot",
)

_TagsByModule: Final[dict[str, str]] = {
    "auth": "Auth",
    "employees": "Employees",
    "tourists": "Tourists",
    "tourist_spots": "Tourist Spots",
    "events": "Events",
    "gamification": "Gamification",
    "visitation": "Visitation",
    "dashboard": "Dashboard",
    "notifications": "Notifications",
    "chatbot": "Chatbot",
}

_DESCRIPTIONS_BY_TAG: Final[dict[str, str]] = {
    "Auth": (
        "Authentication and session management: login, token refresh, "
        "logout and the current user identity (auth module)."
    ),
    "Employees": "Employee management and benefit authorization (employees module).",
    "Tourists": "Tourist registration, login, profile and interests (tourists module).",
    "Tourist Spots": (
        "Registered tourist spots with coordinates, schedules and "
        "multilingual content (tourist_spots module)."
    ),
    "Events": "Cultural events and schedules (events module).",
    "Gamification": "Routes, achievements and reward codes (gamification module).",
    "Visitation": "Check-ins at tourist spots and route progress (visitation module).",
    "Dashboard": "Aggregated metrics and rankings for administrators (dashboard module).",
    "Notifications": "Push notifications and communication (notifications module).",
    "Chatbot": "Generative chatbot over registered content (chatbot module).",
    INFRASTRUCTURE_TAG: "Operational health of the API and its database connectivity.",
}

# Ordered exactly as it must appear in Swagger UI: every DOMAIN_MODULES
# entry in canonical order, then the infrastructure tag last.
OPENAPI_TAGS_METADATA: Final[list[TagMetadata]] = [
    {"name": tag, "description": _DESCRIPTIONS_BY_TAG[tag]} for tag in DOMAIN_TAG_NAMES
] + [
    {
        "name": INFRASTRUCTURE_TAG,
        "description": _DESCRIPTIONS_BY_TAG[INFRASTRUCTURE_TAG],
    }
]


def module_tag(module: str) -> str:
    """Resolve a canonical domain module name to its documentation tag.

    Raises ``ValueError`` for names outside ``DOMAIN_MODULES`` — the
    canonical list and the tag registry must stay in strict 1:1 lockstep
    (spec 006 FR-002; alignment is enforced by test).
    """
    try:
        return _TagsByModule[module]
    except KeyError as error:
        raise ValueError(
            f"Unknown domain module {module!r}: not in DOMAIN_MODULES — "
            "the tag registry must stay aligned with core/modules.py "
            "(feature 006 FR-002)."
        ) from error


def assert_invariants() -> None:
    """Assert registry invariants at import/assert-time for clarity.

    Kept intentionally explicit (and exercised again by the contract sweep):
    exactly one tag per canonical module, bijectively, plus the single
    infrastructure tag — nothing more.
    """
    assert tuple(_TagsByModule[n] for n in DOMAIN_MODULES) == DOMAIN_TAG_NAMES
    assert INFRASTRUCTURE_TAG not in DOMAIN_TAG_NAMES
    assert [entry["name"] for entry in OPENAPI_TAGS_METADATA] == [
        *DOMAIN_TAG_NAMES,
        INFRASTRUCTURE_TAG,
    ]
