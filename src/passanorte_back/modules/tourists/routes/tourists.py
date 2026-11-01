"""HTTP routes of the ``tourists`` module (contracts/tourists.md; US1/US2).

Public endpoints (POST /tourists, POST /tourists/login) plus profile routes
mounted on the canonical router (core/routers.py, prefix /api/v1/tourists).
Uniqueness failures → 409 without leaking existing-account data (SC-002).
"""

from typing import Annotated

from fastapi import Depends, HTTPException, status
from sqlalchemy.orm import Session

from passanorte_back.core.db import get_session
from passanorte_back.core.routers import MODULE_ROUTERS
from passanorte_back.modules.auth.services.authentication import GENERIC_FAILURE
from passanorte_back.modules.tourists.schemas import (
    TouristCreateRequest,
    TouristLoginRequest,
    TouristRegistered,
    TouristSessionResponse,
)
from passanorte_back.modules.tourists.services.tourists import (
    InvalidCredentialsError,
    TouristAlreadyRegisteredError,
    register_tourist,
    tourist_login,
)

router = MODULE_ROUTERS["tourists"]


def _unauthorized() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=GENERIC_FAILURE,
        headers={"WWW-Authenticate": "Bearer"},
    )


@router.post("/login", response_model=TouristSessionResponse)
def post_tourist_login(
    payload: TouristLoginRequest, session: Annotated[Session, Depends(get_session)]
) -> TouristSessionResponse:
    """Authenticate the tourist (RF23): 200 with the foundation's pair or
    401 with the GENERIC message (FR-014)."""
    try:
        tokens = tourist_login(session, email=payload.email, password=payload.password)
    except InvalidCredentialsError as error:
        raise _unauthorized() from error
    return TouristSessionResponse(
        access_token=tokens.access_token,
        refresh_token=tokens.refresh_token,
        token_type="bearer",
        expires_in=tokens.expires_in,
        role=tokens.role,
    )


@router.post("", response_model=TouristRegistered, status_code=status.HTTP_201_CREATED)
def post_tourist(
    payload: TouristCreateRequest,
    session: Annotated[Session, Depends(get_session)],
) -> TouristRegistered:
    """Register a tourist (RF22; one document enforced by the schema —
    409 on duplicate email/cpf/passport among tourists)."""
    try:
        tourist = register_tourist(
            session,
            first_name=payload.first_name.strip(),
            last_name=payload.last_name.strip(),
            country_of_origin=payload.country_of_origin.strip(),
            normalized_email=payload.email,
            phone=payload.phone,
            password=payload.password,
            cpf=payload.cpf,
            passport_number=payload.passport_number,
        )
    except TouristAlreadyRegisteredError as error:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(error)) from error
    return TouristRegistered(
        id=tourist.id,
        first_name=tourist.first_name,
        last_name=tourist.last_name,
        country_of_origin=tourist.country_of_origin,
    )
