"""Public service interface of the ``employees`` module (research R5).

This is the ONLY import surface other modules may use (constitution rule 3;
boundary checker allows only cross-module imports from ``services``):

- ``lookup_credentials`` — credential lookup consumed by the ``auth`` login
  flow (auth imports it lazily inside functions to avoid import cycles —
  analyze F2).
- ``is_username_taken`` comes from the ``auth`` module (global username
  uniqueness across admin users and employees — FR-011).

The management flows (create/update/revoke) live in ``management.py`` and
are re-exported here.
"""

from typing import NamedTuple

from sqlalchemy.orm import Session

from passanorte_back.modules.employees.repositories.employees import (
    Employee,
    find_by_id,
    find_by_username,
    list_all,
)


class EmployeeCredential(NamedTuple):
    """Credential view another module may act upon (no plaintext ever)."""

    account_id: int
    username: str
    password_hash: str
    active: bool
    role: str


def lookup_credentials(session: Session, username: str) -> EmployeeCredential | None:
    """Find an (active or revoked) employee credential by username."""
    employee = find_by_username(session, username)
    if employee is None:
        return None
    return EmployeeCredential(
        account_id=employee.id,
        username=employee.username,
        password_hash=employee.password_hash,
        active=employee.is_active,
        role=employee.role,
    )


def get_employee(session: Session, employee_id: int) -> Employee | None:
    return find_by_id(session, employee_id)


def list_employees(session: Session) -> list[Employee]:
    """All employees ordered by id (admin panel listing)."""
    return list(list_all(session))
