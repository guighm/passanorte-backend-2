"""Admin bootstrap script (RF01; clar. Q4-s5) — entry ``create-admin``.

Secrets come exclusively from environment variables (FR-002):
``ADMIN_USERNAME`` and ``ADMIN_PASSWORD`` (both required, no defaults).
The account is created or updated IN PLACE (upsert by bootstrap
designation — exactly one ``is_bootstrap`` admin exists). Only the bcrypt
hash is persisted; the plaintext password is never echoed.

Requires the migrations to be applied (``uv run alembic upgrade head``);
the database URL comes from ``DATABASE_URL`` (same as the app).

Usage: ``uv run create-admin`` (or ``ADMIN_USERNAME=... ADMIN_PASSWORD=... uv run create-admin``).
"""

import os
import sys

from sqlalchemy.orm import sessionmaker

from passanorte_back.core.config import get_settings
from passanorte_back.core.db import create_engine_from_settings, get_sessionfactory
from passanorte_back.modules.auth.repositories.admin_users import AdminUser

REQUIRED_SECRETS: tuple[str, ...] = ("ADMIN_USERNAME", "ADMIN_PASSWORD")


def _read_required_secrets() -> tuple[str, str]:
    """Env-only secrets (FR-002): fail fast with a clear message."""
    values = [os.environ.get(name, "").strip() for name in REQUIRED_SECRETS]
    missing = [name for name, value in zip(REQUIRED_SECRETS, values, strict=True) if not value]
    if missing:
        message = "required bootstrap secrets missing or empty in environment: " + ", ".join(
            missing
        )
        raise MissingBootstrapSecretError(message)
    username, password = values
    return username, password


class MissingBootstrapSecretError(RuntimeError):
    """RF-002: required bootstrap secrets absent from the environment."""


def run_bootstrap(sessionfactory: sessionmaker) -> tuple[AdminUser, bool]:
    """Run one bootstrap upsert for the current environment (testable)."""
    from passanorte_back.modules.auth.services.bootstrap import upsert_bootstrap_admin

    username, password = _read_required_secrets()
    with sessionfactory() as session:
        account, created = upsert_bootstrap_admin(
            session, admin_username=username, admin_password=password
        )
        session.commit()
        return account, created


def main() -> None:
    """Script entry: upsert the bootstrap admin and report its status."""
    get_settings()  # fail fast on missing DATABASE_URL/JWT_SECRET (app config)
    engine = create_engine_from_settings(get_settings())
    sessionfactory = get_sessionfactory(engine)
    try:
        account, created = run_bootstrap(sessionfactory)
    except MissingBootstrapSecretError as error:
        print(f"error: {error}", file=sys.stderr)
        sys.exit(1)
    finally:
        engine.dispose()

    verb = "created" if created else "updated"
    print(f"bootstrap admin {verb}: username='{account.username}' (is_active={account.is_active})")
    print("the password is NOT echoed (RNF10) — deliver it through your secret store")


if __name__ == "__main__":  # pragma: no cover
    main()
