"""Interests routes of the ``tourists`` module (contracts/tourists.md; US4).

- GET /tourists/interest-categories — configured categories, readable by
  ANY authenticated account (configuration data, not personal — FR-012).
- GET/PUT /tourists/me/interests — tourist-exclusive (require_tourist —
  FR-015); PUT replaces the selection wholesale (422 naming an invalid
  category).
"""

from typing import Annotated

from fastapi import Depends, HTTPException, status
from sqlalchemy.orm import Session

from passanorte_back.core.db import get_session
from passanorte_back.core.routers import MODULE_ROUTERS
from passanorte_back.modules.auth.services.security import (
    AuthenticatedUser,
    get_current_user,
    require_tourist,
)
from passanorte_back.modules.tourists.schemas import (
    InterestCategoriesResponse,
    TouristInterestsResponse,
    TouristInterestsUpdateRequest,
)
from passanorte_back.modules.tourists.services.interests import (
    InvalidInterestCategoryError,
    get_tourist_interests,
    list_interest_categories,
    update_tourist_interests,
)

router = MODULE_ROUTERS["tourists"]


@router.get("/interest-categories", response_model=InterestCategoriesResponse)
def get_interest_categories(
    user: Annotated[AuthenticatedUser, Depends(get_current_user)],
) -> InterestCategoriesResponse:
    """Exactly the configured categories (RNF06/SC-006 — data, not code)."""
    return InterestCategoriesResponse(categories=list_interest_categories())


@router.get("/me/interests", response_model=TouristInterestsResponse)
def get_my_interests(
    session: Annotated[Session, Depends(get_session)],
    user: Annotated[AuthenticatedUser, Depends(require_tourist)],
) -> TouristInterestsResponse:
    """Own selection; configured-only; empty before the first PUT."""
    return get_tourist_interests(session, user.account_id)


@router.put("/me/interests", response_model=TouristInterestsResponse)
def put_my_interests(
    payload: TouristInterestsUpdateRequest,
    session: Annotated[Session, Depends(get_session)],
    user: Annotated[AuthenticatedUser, Depends(require_tourist)],
) -> TouristInterestsResponse:
    """Replace the whole selection (FR-010; invalid key → 422 — FR-011)."""
    try:
        return update_tourist_interests(
            session,
            tourist_id=user.account_id,
            interests=payload.interests,
            actor=user.username,
        )
    except InvalidInterestCategoryError as error:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(error)
        ) from error
