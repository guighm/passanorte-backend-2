"""Authentication flows of the panel (US2 — RF02, RNF09; research R3/R4).

- ``login``: single flow for both profiles (clar. Q2) — resolves the admin
  account from this module's repository and the employee account via the
  public ``employees.services`` interface; issues the credential PAIR
  (short-lived access JWT + opaque refresh persisted hashed, single-use).
- ``refresh``: exchanges a valid refresh credential for a new pair
  (single-use — reused/rotated/revoked/expired are refused).
- ``logout``: revokes the session (invalidates the refresh credential).

Account state (active/revoked) is always revalidated (FR-013, research R4).
Audit: login.success, login.failure, session.refresh, logout (FR-014).
"""

from typing import NamedTuple

from sqlalchemy.orm import Session

from passanorte_back.core.audit import record_action
from passanorte_back.core.config import get_settings
from passanorte_back.core.security import (
    create_access_token,
    generate_refresh_token,
    hash_refresh_token,
    verify_password,
)
from passanorte_back.modules.auth.repositories.admin_users import (
    find_by_id as find_admin_by_id,
)
from passanorte_back.modules.auth.repositories.admin_users import (
    find_by_username as find_admin_by_username,
)
from passanorte_back.modules.auth.repositories.auth_sessions import (
    AccountType,
    find_active_by_refresh_hash,
    revoke_session,
)
from passanorte_back.modules.auth.repositories.auth_sessions import (
    create_session as create_auth_session,
)

GENERIC_FAILURE = "invalid credentials"


class InvalidCredentialsError(Exception):
    """Login rejected: wrong password, unknown user or inactive account."""


class InvalidRefreshTokenError(Exception):
    """Refresh rejected: unknown/rotated/revoked/expired or inactive account."""


class SessionTokens(NamedTuple):
    """The credential pair + identity returned by login/refresh."""

    access_token: str
    refresh_token: str
    expires_in: int
    role: str
    session_id: int


class _ResolvedAccount(NamedTuple):
    """Account state the flows need (password hash only in the login path)."""

    account_type: AccountType
    account_id: int
    role: str
    active: bool
    username: str
    password_hash: str | None = None


def _resolve_admin_by_username(session: Session, username: str) -> _ResolvedAccount | None:
    admin = find_admin_by_username(session, username)
    if admin is None:
        return None
    return _ResolvedAccount(
        account_type="admin",
        account_id=admin.id,
        role=admin.role,
        active=admin.is_active,
        username=admin.username,
        password_hash=admin.password_hash,
    )


def _resolve_employee_by_username(session: Session, username: str) -> _ResolvedAccount | None:
    from passanorte_back.modules.employees.services import lookup_credentials

    credential = lookup_credentials(session, username)
    if credential is None:
        return None
    return _ResolvedAccount(
        account_type="employee",
        account_id=credential.account_id,
        role=credential.role,
        active=credential.active,
        username=credential.username,
        password_hash=credential.password_hash,
    )


def _resolve_admin_by_id(session: Session, account_id: int) -> _ResolvedAccount | None:
    admin = find_admin_by_id(session, account_id)
    if admin is None:
        return None
    return _ResolvedAccount(
        account_type="admin",
        account_id=admin.id,
        role=admin.role,
        active=admin.is_active,
        username=admin.username,
    )


def _resolve_employee_by_id(session: Session, account_id: int) -> _ResolvedAccount | None:
    from passanorte_back.modules.employees.services import get_employee

    employee = get_employee(session, account_id)
    if employee is None:
        return None
    return _ResolvedAccount(
        account_type="employee",
        account_id=employee.id,
        role=employee.role,
        active=employee.is_active,
        username=employee.username,
    )


def _issue_pair(
    session: Session,
    *,
    account_type: AccountType,
    account_id: int,
    role: str,
) -> SessionTokens:
    """Persist the session row and issue the credential pair (clar. Q1)."""
    settings = get_settings()
    refresh_token = generate_refresh_token()
    auth_session = create_auth_session(
        session,
        account_type=account_type,
        account_id=account_id,
        refresh_token_hash=hash_refresh_token(refresh_token),
        refresh_ttl=settings.jwt_refresh_ttl,
    )
    access_token = create_access_token(
        account_id=account_id,
        account_type=account_type,
        role=role,
        session_id=auth_session.id,
        ttl=settings.jwt_ttl,
        secret=settings.jwt_secret,
    )
    return SessionTokens(
        access_token=access_token,
        refresh_token=refresh_token,
        expires_in=settings.jwt_ttl,
        role=role,
        session_id=auth_session.id,
    )


def login(session: Session, *, username: str, password: str) -> SessionTokens:
    """Authenticate (admin or employee) and issue the credential pair."""
    # Admin first (module-local); employee via the public lazy import (F2).
    resolved = _resolve_admin_by_username(session, username) or (
        _resolve_employee_by_username(session, username)
    )
    if (
        resolved is None
        or resolved.password_hash is None
        or not verify_password(password, resolved.password_hash)
        or not resolved.active
    ):
        record_action(
            actor=username or "unknown",
            action="login.failure",
            target="account",
            result="failure",
        )
        raise InvalidCredentialsError(GENERIC_FAILURE)

    tokens = _issue_pair(
        session,
        account_type=resolved.account_type,
        account_id=resolved.account_id,
        role=resolved.role,
    )
    record_action(
        actor=resolved.username,
        action="login.success",
        target=f"account:{resolved.account_id}",
        result="success",
        detail={"role": resolved.role, "account_type": resolved.account_type},
    )
    return tokens


def refresh(session: Session, *, refresh_token: str) -> SessionTokens:
    """Exchange a valid refresh credential for a NEW pair (single-use)."""
    row = find_active_by_refresh_hash(session, hash_refresh_token(refresh_token))
    if row is None:
        record_action(
            actor="unknown",
            action="session.refresh.failure",
            target="auth_session",
            result="failure",
        )
        raise InvalidRefreshTokenError(GENERIC_FAILURE)

    if row.account_type == "admin":
        resolved = _resolve_admin_by_id(session, row.account_id)
    else:
        resolved = _resolve_employee_by_id(session, row.account_id)
    if resolved is None or not resolved.active:
        record_action(
            actor="unknown",
            action="session.refresh.failure",
            target=f"auth_session:{row.id}",
            result="failure",
        )
        raise InvalidRefreshTokenError(GENERIC_FAILURE)

    # Single-use: the old session dies exactly when the new pair is issued.
    revoke_session(session, row.id)

    tokens = _issue_pair(
        session,
        account_type=resolved.account_type,
        account_id=resolved.account_id,
        role=resolved.role,
    )
    record_action(
        actor=resolved.username,
        action="session.refresh",
        target=f"account:{resolved.account_id}",
        result="success",
    )
    return tokens


def logout(session: Session, *, session_id: int, actor: str) -> None:
    """Revoke the current session (FR-016; audit FR-014)."""
    revoke_session(session, session_id)
    record_action(
        actor=actor,
        action="logout",
        target=f"auth_session:{session_id}",
        result="success",
    )


def revoke_sessions_for_account(session: Session, *, account_type: str, account_id: int) -> int:
    """Public write interface (constitution rule 5): revoke all usable
    sessions of an account, killing live access + refresh credentials
    immediately (FR-013; used by ``employees.services`` on revocation)."""
    from passanorte_back.modules.auth.repositories.auth_sessions import (
        revoke_all_for_account,
    )

    return revoke_all_for_account(session, account_type, account_id)
