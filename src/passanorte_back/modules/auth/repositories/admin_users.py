"""Admin account persistence (data-model.md §1; module auth).

Exactly one bootstrap-designated admin row exists per environment
(clar. Q4-s5: upsert by bootstrap designation — updated in place, never
duplicated). Other modules never touch this table directly.
"""

from datetime import UTC, datetime

from sqlalchemy import Boolean, String
from sqlalchemy.orm import Mapped, Session, mapped_column

from passanorte_back.core.db import Base

ROLE_ADMIN = "admin"


class AdminUser(Base):
    """Admin account of the panel (bootstrap created — FR-001)."""

    __tablename__ = "admin_users"

    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(100), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(20), default=ROLE_ADMIN)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    is_bootstrap: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(default=lambda: datetime.now(UTC))
    updated_at: Mapped[datetime] = mapped_column(
        default=lambda: datetime.now(UTC), onupdate=lambda: datetime.now(UTC)
    )


def find_by_username(session: Session, username: str) -> AdminUser | None:
    """Case-insensitive lookup by username (data-model.md uniqueness rule)."""
    return session.query(AdminUser).filter(AdminUser.username == username.casefold()).first()


def find_by_id(session: Session, admin_id: int) -> AdminUser | None:
    return session.get(AdminUser, admin_id)


def find_bootstrap_account(session: Session) -> AdminUser | None:
    """The single bootstrap-designated admin row (upsert anchor)."""
    return session.query(AdminUser).filter(AdminUser.is_bootstrap.is_(True)).first()
