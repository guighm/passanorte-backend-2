"""Employee management flows (US4/US5 — RF04/RF05; FR-010/011/012/013).

Admin-only actions (routes enforce RBAC; this layer is the data owner of
``employees``):

- ``create_employee``: the SYSTEM generates the initial password (clar.
  Q3-s4); only the bcrypt hash is persisted; the password is returned for
  the one-time delivery view — never audited/logged.
- ``update_employee``: name/username edits; reactivation of a revoked
  employee (clar. Q3-s3; pre-revocation sessions stay rejected).
- ``revoke_employee``: status → revoked; effective immediately for live
  sessions (next request reloads state — FR-013) and new logins.

Global username uniqueness (admin ∪ employees, case-insensitive — FR-011)
is checked via the public ``auth.services`` function (lazy — analyze F2).
Audit per contract (RNF19/FR-014).
"""

from sqlalchemy.orm import Session

from passanorte_back.core.audit import record_action
from passanorte_back.core.security import generate_initial_password, hash_password
from passanorte_back.modules.employees.repositories.employees import (
    STATUS_ACTIVE,
    STATUS_REVOKED,
    Employee,
    add_employee,
    find_by_username,
    find_other_username_holder,
)
from passanorte_back.modules.employees.services import get_employee


class DuplicateUsernameError(Exception):
    """Username already taken in the global username space (FR-011)."""


class EmployeeMissingError(Exception):
    """Target employee id does not exist (route → 404)."""


class StatusTransitionError(Exception):
    """Not allowed here: revoke goes through the dedicated route (422)."""


def _username_taken_globally(session: Session, username: str) -> bool:
    """Check the admin side (auth) and the employee side (same module)."""
    from passanorte_back.modules.auth.services.bootstrap import is_username_taken  # analyze F2

    return is_username_taken(session, username) or (find_by_username(session, username) is not None)


def create_employee(
    session: Session, *, actor: str, name: str, username: str
) -> tuple[Employee, str]:
    """Create an employee account; returns (employee, initial_password)."""
    if _username_taken_globally(session, username):
        raise DuplicateUsernameError("username already in use")

    initial_password = generate_initial_password()
    employee = add_employee(
        session,
        name=name,
        username=username,
        password_hash=hash_password(initial_password),
    )
    record_action(
        actor=actor,
        action="employee.create",
        target=f"employee:{employee.id}",
        result="success",
        detail={"username": employee.username},
    )
    return employee, initial_password


def update_employee(
    session: Session,
    *,
    actor: str,
    employee_id: int,
    name: str | None = None,
    username: str | None = None,
    status: str | None = None,
) -> Employee:
    """Edit data; ``status="active"`` reactivates a revoked employee
    (clar. Q3-s3; pre-revocation sessions stay rejected — FR-013)."""
    employee = get_employee(session, employee_id)
    if employee is None:
        raise EmployeeMissingError("employee not found")

    reactivated = False
    if status is not None:
        if status == STATUS_REVOKED:
            # Revoke only through the dedicated route (contract clarity).
            raise StatusTransitionError("revoke through POST /employees/{id}/revoke")
        if status != STATUS_ACTIVE:
            raise StatusTransitionError("invalid status value")
        reactivated = not employee.is_active
        employee.status = STATUS_ACTIVE

    if username is not None:
        new_username = username.casefold()
        if new_username != employee.username and (
            _username_taken_globally(session, new_username)
            or find_other_username_holder(session, new_username, employee.id)
        ):
            raise DuplicateUsernameError("username already in use")
        employee.username = new_username

    if name is not None:
        employee.name = name

    field_changed = name is not None or username is not None
    target = f"employee:{employee.id}"
    summary = {
        "name": employee.name,
        "username": employee.username,
        "status": employee.status,
    }
    if reactivated:
        record_action(
            actor=actor,
            action="employee.reactivate",
            target=target,
            result="success",
            detail=summary,
        )
    if field_changed:
        record_action(
            actor=actor,
            action="employee.update",
            target=target,
            result="success",
            detail=summary,
        )
    return employee


def revoke_employee(session: Session, *, actor: str, employee_id: int) -> None:
    """Revoke access (idempotent; effective immediately — FR-013).

    Session state belongs to ``auth``: the live sessions (access + refresh
    credentials) are revoked through the public auth service
    (constitution rule 5 — analyze F2 lazy import).
    """
    from passanorte_back.modules.auth.services.authentication import (
        revoke_sessions_for_account,
    )

    employee = get_employee(session, employee_id)
    if employee is None:
        raise EmployeeMissingError("employee not found")
    employee.status = STATUS_REVOKED
    revoke_sessions_for_account(session, account_type="employee", account_id=employee.id)
    record_action(
        actor=actor,
        action="employee.revoke",
        target=f"employee:{employee.id}",
        result="success",
        detail={"username": employee.username, "sessions_revoked": True},
    )
