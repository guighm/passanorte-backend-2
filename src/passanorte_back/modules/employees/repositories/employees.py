"""Employee account persistence (data-model.md §2; module employees).

The table and its data access belong exclusively to the ``employees``
domain: nobody outside reads or writes these rows directly. Other modules
consume the public service interface in ``employees.services`` (research
R5).
"""

from datetime import UTC, datetime
from typing import Final

from sqlalchemy import String
from sqlalchemy.orm import Mapped, Session, mapped_column

from passanorte_back.core.db import Base

USERNAME_LENGTH: Final[int] = 100
NAME_LENGTH: Final[int] = 200

ROLE_EMPLOYEE: Final[str] = "employee"
STATUS_ACTIVE: Final[str] = "active"
STATUS_REVOKED: Final[str] = "revoked"


class Employee(Base):
    """Employee account (created by an admin; status active/revoked)."""

    __tablename__ = "employees"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(NAME_LENGTH))
    username: Mapped[str] = mapped_column(String(USERNAME_LENGTH), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(20), default=ROLE_EMPLOYEE)
    status: Mapped[str] = mapped_column(String(20), default=STATUS_ACTIVE)
    created_at: Mapped[datetime] = mapped_column(index=False, default=lambda: datetime.now(UTC))
    updated_at: Mapped[datetime] = mapped_column(
        default=lambda: datetime.now(UTC), onupdate=lambda: datetime.now(UTC)
    )

    @property
    def is_active(self) -> bool:
        return self.status == STATUS_ACTIVE


def find_by_username(session: Session, username: str) -> Employee | None:
    """Case-insensitive lookup by username (data-model.md uniqueness rule)."""
    return session.query(Employee).filter(Employee.username == username.casefold()).first()


def find_by_id(session: Session, employee_id: int) -> Employee | None:
    return session.get(Employee, employee_id)


def list_all(session: Session) -> list[Employee]:
    return list(session.query(Employee).order_by(Employee.id))


def add_employee(
    session: Session,
    *,
    name: str,
    username: str,
    password_hash: str,
) -> Employee:
    employee = Employee(
        name=name,
        username=username.casefold(),
        password_hash=password_hash,
        role=ROLE_EMPLOYEE,
        status=STATUS_ACTIVE,
    )
    session.add(employee)
    session.flush()
    return employee


def find_other_username_holder(
    session: Session, username: str, except_id: int | None
) -> Employee | None:
    """Another employee already holding this username (case-insensitive)."""
    query = session.query(Employee).filter(Employee.username == username.casefold())
    if except_id is not None:
        query = query.filter(Employee.id != except_id)
    return query.first()
