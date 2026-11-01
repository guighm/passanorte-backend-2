"""Profile routes of the ``tourists`` module (contracts/tourists.md; US3).

- GET /tourists/me          — tourist-exclusive shortcut (require_tourist).
- GET/PATCH /tourists/{id}  — self-or-admin (403 for the other tourist —
  SC-004; 404 for the admin without target; 401 without token).
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
    TouristProfileResponse,
    TouristUpdateRequest,
)
from passanorte_back.modules.tourists.services.profile import (
    ProfileConflictError,
    ProfileForbiddenError,
    ProfileValidationError,
    get_tourist_profile,
    tourist_or_forbid,
    update_tourist_profile,
)
from passanorte_back.modules.tourists.services.tourists import TouristMissingError

router = MODULE_ROUTERS["tourists"]


def _forbidden() -> HTTPException:
    return HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="insufficient permissions")


def _not_found() -> HTTPException:
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="tourist not found")


@router.get("/me", response_model=TouristProfileResponse)
def get_my_profile(
    session: Annotated[Session, Depends(get_session)],
    user: Annotated[AuthenticatedUser, Depends(require_tourist)],
) -> TouristProfileResponse:
    """Own profile with controlled decryption (FR-006/FR-007)."""
    tourist = tourist_or_forbid(session, requester=user, tourist_id=user.account_id)
    return get_tourist_profile(session, tourist)


@router.get("/{tourist_id}", response_model=TouristProfileResponse)
def get_tourist(
    tourist_id: int,
    session: Annotated[Session, Depends(get_session)],
    user: Annotated[AuthenticatedUser, Depends(get_current_user)],
) -> TouristProfileResponse:
    """Readable by self or admin; another tourist → 403 (SC-004)."""
    try:
        tourist = tourist_or_forbid(session, requester=user, tourist_id=tourist_id)
    except ProfileForbiddenError as error:
        raise _forbidden() from error
    except TouristMissingError as error:
        raise _not_found() from error
    return get_tourist_profile(session, tourist)


@router.patch("/{tourist_id}", status_code=status.HTTP_204_NO_CONTENT)
def patch_tourist(
    tourist_id: int,
    payload: TouristUpdateRequest,
    session: Annotated[Session, Depends(get_session)],
    user: Annotated[AuthenticatedUser, Depends(get_current_user)],
) -> None:
    """Edit self or admin (RF24); 403 denies without leaking (SC-004)."""
    try:
        tourist = tourist_or_forbid(session, requester=user, tourist_id=tourist_id)
    except ProfileForbiddenError as error:
        raise _forbidden() from error
    except TouristMissingError as error:
        raise _not_found() from error
    try:
        update_tourist_profile(session, tourist=tourist, payload=payload, actor=user.username)
    except ProfileConflictError as error:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(error)) from error
    except ProfileValidationError as error:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(error)
        ) from error
