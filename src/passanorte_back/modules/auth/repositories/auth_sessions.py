"""Session (refresh credential) persistence — data-model.md §3; module auth.

One row per issued credential pair: the refresh token is stored only as a
SHA-256 hash (research R3). Rows end their life as ``rotated`` (single-use
refresh), ``revoked`` (logout / account revocation) or expired
(``expires_at`` in the past).
"""

from datetime import UTC, datetime, timedelta
from typing import Literal

from sqlalchemy import DateTime, String
from sqlalchemy.orm import Mapped, Session, mapped_column

from passanorte_back.core.db import Base

ACCOUNT_TYPES: tuple[str, str, str] = ("admin", "employee", "tourist")
AccountType = Literal["admin", "employee", "tourist"]

REFRESH_HASH_LENGTH = 64


def _as_naive_utc(value: datetime) -> datetime:
    """Normalize datetimes for comparison (SQLite returns naive datetimes
    even for timezone-aware columns — uniform UTC-naive comparisons)."""
    return value.replace(tzinfo=None) if value.tzinfo is not None else value


class AuthSession(Base):
    """Server-side state of one issued credential pair (Q1 clar.)."""

    __tablename__ = "auth_sessions"

    id: Mapped[int] = mapped_column(primary_key=True)
    account_type: Mapped[str] = mapped_column(String(10))
    account_id: Mapped[int] = mapped_column(index=True)
    refresh_token_hash: Mapped[str] = mapped_column(
        String(REFRESH_HASH_LENGTH), unique=True, index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    def is_usable(self, now: datetime) -> bool:
        """Not revoked and not yet expired (refresh eligibility)."""
        return self.revoked_at is None and _as_naive_utc(self.expires_at) > _as_naive_utc(now)


def create_session(
    session: Session,
    *,
    account_type: AccountType,
    account_id: int,
    refresh_token_hash: str,
    refresh_ttl: int,
) -> AuthSession:
    """Persist a new session row (state of the issued pair)."""
    auth_session = AuthSession(
        account_type=account_type,
        account_id=account_id,
        refresh_token_hash=refresh_token_hash,
        expires_at=datetime.now(UTC) + timedelta(seconds=refresh_ttl),
    )
    session.add(auth_session)
    session.flush()
    return auth_session


def find_by_id(session: Session, session_id: int) -> AuthSession | None:
    return session.get(AuthSession, session_id)


def revoke_all_for_account(session: Session, account_type: str, account_id: int) -> int:
    """Revoke every usable session of an account (account revocation —
    FR-013). Returns the number of rows revoked."""
    moment = datetime.now(UTC)
    rows = (
        session.query(AuthSession)
        .filter(
            AuthSession.account_type == account_type,
            AuthSession.account_id == account_id,
            AuthSession.revoked_at.is_(None),
        )
        .all()
    )
    for row in rows:
        row.revoked_at = moment
    return len(rows)


def find_active_by_refresh_hash(
    session: Session, refresh_token_hash: str, *, now: datetime | None = None
) -> AuthSession | None:
    """Usable session for a refresh hash (rotated/revoked/expired → None)."""
    moment = now or datetime.now(UTC)
    auth_session = (
        session.query(AuthSession)
        .filter(AuthSession.refresh_token_hash == refresh_token_hash)
        .first()
    )
    if auth_session is None or not auth_session.is_usable(moment):
        return None
    return auth_session


def revoke_session(session: Session, session_id: int) -> bool:
    """Mark the session revoked immediately (logout / revocation — FR-013).

    Returns whether a usable row was found and revoked.
    """
    auth_session = session.get(AuthSession, session_id)
    if auth_session is None or auth_session.revoked_at is not None:
        return False
    auth_session.revoked_at = datetime.now(UTC)
    return True
