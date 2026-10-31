"""Admin bootstrap service (US1 — RF01; research R7; clar. Q4-s5).

Upsert by bootstrap designation: the environment has exactly ONE
bootstrap-designated admin account (``is_bootstrap``), identified by the
system and not by the username text. Re-executions update it in place
(new username and/or new password hash) and restore ``is_active`` —
no second account is ever created. Segrets arrive from environment
variables only (FR-002); only the bcrypt hash is persisted (RNF10).
"""

from sqlalchemy.orm import sessionmaker

from passanorte_back.core.audit import record_action
from passanorte_back.core.security import hash_password, verify_password
from passanorte_back.modules.auth.repositories.admin_users import (
    AdminUser,
    find_bootstrap_account,
    find_by_username,
)

BOOTSTRAP_ACTOR = "system/bootstrap"


class MissingBootstrapSecretError(RuntimeError):
    """RF-002: required bootstrap secrets absent from the environment."""


def is_username_taken(session, username: str) -> bool:
    """Global username uniqueness — admin side (FR-011).

    Employees check against admin accounts via this public function
    (research R5: no shared tables, service-only).
    """
    return find_by_username(session, username) is not None


def upsert_bootstrap_admin(
    session,
    *,
    admin_username: str,
    admin_password: str,
) -> tuple[AdminUser, bool]:
    """Create or update the bootstrap admin in place (FR-001/FR-003)."""
    bootstrap = find_bootstrap_account(session)
    created = bootstrap is None
    if bootstrap is None:
        bootstrap = AdminUser(
            username=admin_username.casefold(),
            password_hash=hash_password(admin_password),
            role="admin",
            is_active=True,
            is_bootstrap=True,
        )
        session.add(bootstrap)
    else:
        bootstrap.username = admin_username.casefold()
        password_changed = not verify_password(admin_password, bootstrap.password_hash)
        if password_changed:
            bootstrap.password_hash = hash_password(admin_password)
        bootstrap.is_active = True
    session.flush()
    record_action(
        actor=BOOTSTRAP_ACTOR,
        action="bootstrap.upsert",
        target=f"admin:{bootstrap.id}",
        result="success",
        detail={"created": created, "username": bootstrap.username},
    )
    return bootstrap, created


def run_bootstrap(
    sessionfactory: sessionmaker, *, admin_username: str, admin_password: str
) -> tuple[AdminUser, bool]:
    """Transactionally run one bootstrap upsert (script entry — T014)."""
    with sessionfactory() as session:  # close-only context; commit below
        result = upsert_bootstrap_admin(
            session, admin_username=admin_username, admin_password=admin_password
        )
        session.commit()
        return result
