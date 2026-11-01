"""Interests flows of the ``tourists`` module (US4 — RF25, RNF06).

- ``list_interest_categories``: exactly ``Settings.resolved_interest_categories()``
  (data from ``config/location.json`` — portability, principle VI).
- ``get_tourist_interests``: selected keys filtered by the CURRENTLY
  configured categories (orphan categories omitted — spec edge case).
- ``update_tourist_interests``: validates every key against the
  configuration (422 naming the invalid one — FR-011), then replaces the
  whole selection delete+insert in ONE transaction (FR-010); duplicates are
  normalized by the schema; audit ``tourist.interests.update``.
"""

from sqlalchemy.orm import Session

from passanorte_back.core.audit import record_action
from passanorte_back.modules.tourists.repositories.tourist_interests import (
    list_for_tourist,
    replace_selection,
)
from passanorte_back.modules.tourists.schemas.tourists import (
    InterestCategory,
    TouristInterestsResponse,
)


class InvalidInterestCategoryError(Exception):
    """Category key outside the configured list (FR-011 → 422)."""


def list_interest_categories() -> list[InterestCategory]:
    """Configured categories, verbatim from the location data (SC-006)."""
    from passanorte_back.core.config import get_settings

    return [
        InterestCategory(key=item["key"], label=item["label"])
        for item in get_settings().resolved_interest_categories()
    ]


def get_tourist_interests(session: Session, tourist_id: int) -> TouristInterestsResponse:
    configured = {category.key for category in list_interest_categories()}
    selected = [key for key in list_for_tourist(session, tourist_id) if key in configured]
    return TouristInterestsResponse(interests=selected)


def update_tourist_interests(
    session: Session, *, tourist_id: int, interests: list[str], actor: str
) -> TouristInterestsResponse:
    """Validate keys against the configuration and replace the selection."""
    configured = {category.key for category in list_interest_categories()}
    for key in interests:
        if key not in configured:
            raise InvalidInterestCategoryError(
                f"invalid interest category: '{key}' is not configured"
            )

    replace_selection(session, tourist_id, interests)
    record_action(
        actor=actor,
        action="tourist.interests.update",
        target=f"tourist:{tourist_id}",
        result="success",
        detail={"count": len(interests)},
    )
    return TouristInterestsResponse(interests=interests)
