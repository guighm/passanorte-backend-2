"""HTTP routes of the ``auth`` module (contracts/auth.md; US2/US3).

Endpoints mounted on the canonical module router (core/routers.py,
prefix /api/v1/auth): POST /login, POST /refresh, POST /logout, GET /me.
Login/refresh are unauthenticated by definition; everything else requires
the bearer access token (401 — FR-015).
"""

from typing import Annotated

from fastapi import Depends, HTTPException, status
from sqlalchemy.orm import Session

from passanorte_back.core.db import get_session
from passanorte_back.core.routers import MODULE_ROUTERS
from passanorte_back.modules.auth.schemas import (
    CurrentUserResponse,
    LoginRequest,
    RefreshRequest,
    SessionResponse,
)
from passanorte_back.modules.auth.services.authentication import (
    GENERIC_FAILURE,
    InvalidCredentialsError,
    InvalidRefreshTokenError,
    SessionTokens,
    login,
    logout,
    refresh,
)
from passanorte_back.modules.auth.services.security import (
    AuthenticatedUser,
    get_current_user,
)

router = MODULE_ROUTERS["auth"]


def _unauthorized() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=GENERIC_FAILURE,
        headers={"WWW-Authenticate": "Bearer"},
    )


@router.post("/login", response_model=SessionResponse)
def post_login(
    payload: LoginRequest, session: Annotated[Session, Depends(get_session)]
) -> SessionResponse:
    """Authenticate admin or employee and issue the credential pair."""
    try:
        tokens: SessionTokens = login(session, username=payload.username, password=payload.password)
    except InvalidCredentialsError as error:
        raise _unauthorized() from error
    return SessionResponse(
        access_token=tokens.access_token,
        refresh_token=tokens.refresh_token,
        token_type="bearer",
        expires_in=tokens.expires_in,
        role=tokens.role,
    )


@router.post("/refresh", response_model=SessionResponse)
def post_refresh(
    payload: RefreshRequest, session: Annotated[Session, Depends(get_session)]
) -> SessionResponse:
    """Exchange a valid refresh credential for a new pair (single-use)."""
    try:
        tokens: SessionTokens = refresh(session, refresh_token=payload.refresh_token)
    except InvalidRefreshTokenError as error:
        raise _unauthorized() from error
    return SessionResponse(
        access_token=tokens.access_token,
        refresh_token=tokens.refresh_token,
        token_type="bearer",
        expires_in=tokens.expires_in,
        role=tokens.role,
    )


@router.get("/me", response_model=CurrentUserResponse)
def get_me(
    user: Annotated[AuthenticatedUser, Depends(get_current_user)],
) -> CurrentUserResponse:
    """Authenticated identity of the current session (US3, /me probe of
    the RBAC contract — any authenticated role; FR-015)."""
    return CurrentUserResponse(username=user.username, role=user.role)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def post_logout(
    session: Annotated[Session, Depends(get_session)],
    user: Annotated[AuthenticatedUser, Depends(get_current_user)],
) -> None:
    """Revoke the current session (refresh credential unusable — FR-016)."""
    logout(session, session_id=user.session_id, actor=user.username)
