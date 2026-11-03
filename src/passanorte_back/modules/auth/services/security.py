"""Authentication dependencies and RBAC gate (research R4/R6; FR-013/FR-015).

Public import surface of the ``auth`` module for request authentication:

- ``get_current_user``: verifies the bearer access token (signature,
  expiry) AND reloads the account state per request — so an account
  revoked/deactivated between requests loses access immediately (FR-013).
- ``require_admin``: the RBAC gate for admin-only panel routes (403 for a
  correctly authenticated non-admin account — RF03, FR-008).

Imported lazily from ``employees.services`` (cross-module public interface;
analyze F2 — avoids import cycles at module load).
"""

from typing import Annotated, NamedTuple

import jwt as pyjwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from passanorte_back.core.config import get_settings
from passanorte_back.core.db import get_session
from passanorte_back.core.security import decode_access_token
from passanorte_back.modules.auth.repositories.admin_users import (
    ROLE_ADMIN,
)
from passanorte_back.modules.auth.repositories.admin_users import (
    find_by_id as find_admin_by_id,
)

ROLE_ADMIN: str = ROLE_ADMIN
ROLE_EMPLOYEE: str = "employee"

_bearer_scheme = HTTPBearer(auto_error=False)

_UNAUTHORIZED_CREDENTIALS = "invalid or expired credentials"
_FORBIDDEN_PERMISSION = "insufficient permissions"


class AuthenticatedUser(NamedTuple):
    """Identity of the account behind a valid request session."""

    account_id: int
    username: str
    role: str
    account_type: str
    session_id: int


def _http_401() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=_UNAUTHORIZED_CREDENTIALS,
        headers={"WWW-Authenticate": "Bearer"},
    )


def _find_session_session(
    session: Session, credentials: HTTPAuthorizationCredentials | None
) -> AuthenticatedUser:
    """Resolve the authenticated identity from the bearer token.

    Signature/expiry come from the access token; account state is always
    reloaded (revocation is effective for live sessions — FR-013).
    """

    if credentials is None:
        raise _http_401()
    try:
        claims = decode_access_token(credentials.credentials, secret=get_settings().jwt_secret)
    except pyjwt.InvalidTokenError as error:
        raise _http_401() from error

    account_type: str = str(claims["account_type"])
    account_id = int(str(claims["sub"]))
    session_id = int(str(claims["sid"]))
    username: str
    role: str

    from passanorte_back.modules.auth.repositories.auth_sessions import find_by_id

    session_row = find_by_id(session, session_id)
    if session_row is None or session_row.revoked_at is not None:
        # Live sessions die with their state row (logout/revocation — FR-013/FR-016).
        raise _http_401()

    if account_type == "admin":
        admin = find_admin_by_id(session, account_id)
        if admin is None or not admin.is_active:
            raise _http_401()
        username, role = admin.username, admin.role
    elif account_type == "employee":
        credential = _lookup_employee_by_id(session, account_id)
        if credential is None or not credential.active:
            raise _http_401()
        username, role = credential.username, credential.role
    elif account_type == "tourist":
        tourist = _lookup_tourist_by_id(session, account_id)
        if tourist is None or not tourist.active:
            raise _http_401()
        username, role = tourist.email, tourist.role
    else:
        raise _http_401()

    return AuthenticatedUser(
        account_id=account_id,
        username=username,
        role=role,
        account_type=account_type,
        session_id=session_id,
    )


def _lookup_employee_by_id(session: Session, account_id: int):
    """Employee state reload via the public employees interface."""
    from passanorte_back.modules.employees.services import EmployeeCredential, get_employee

    employee = get_employee(session, account_id)
    if employee is None:
        return None

    return EmployeeCredential(
        account_id=employee.id,
        username=employee.username,
        password_hash=employee.password_hash,
        active=employee.is_active,
        role=employee.role,
    )


def _lookup_tourist_by_id(session: Session, account_id: int):
    """Tourist state reload via the public tourists interface (T017)."""
    from passanorte_back.modules.tourists.services.tourists import get_tourist_account

    return get_tourist_account(session, account_id)


def get_current_user(
    session: Annotated[Session, Depends(get_session)],
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer_scheme)],
) -> AuthenticatedUser:
    """FastAPI dependency: the authenticated identity or HTTP 401."""
    return _find_session_session(session, credentials)


def require_admin(
    user: Annotated[AuthenticatedUser, Depends(get_current_user)],
) -> AuthenticatedUser:
    """FastAPI dependency: admin-only routes (403 otherwise — FR-008)."""
    if user.account_type != "admin" or user.role != ROLE_ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=_FORBIDDEN_PERMISSION,
        )
    return user


def require_tourist(
    user: Annotated[AuthenticatedUser, Depends(get_current_user)],
) -> AuthenticatedUser:
    """FastAPI dependency: tourist-exclusive routes (app Passaporte) —
    403 for admin/employee (FR-015/s16)."""
    if user.account_type != "tourist":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=_FORBIDDEN_PERMISSION,
        )
    return user


def require_staff(
    user: Annotated[AuthenticatedUser, Depends(get_current_user)],
) -> AuthenticatedUser:
    """FastAPI dependency: staff routes (admin OR employee) — the prize
    concession gate (feature 009 research R6; Q3). Tourist sessions and
    anonymous requests get 403 (anonymous never reaches here — bearer
    required by ``get_current_user``)."""
    if user.account_type not in ("admin", "employee"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=_FORBIDDEN_PERMISSION,
        )
    return user


__all__ = [
    "AuthenticatedUser",
    "get_current_user",
    "require_admin",
    "require_staff",
    "require_tourist",
]
