"""Global test configuration: fixed, synthetic environment.

Fixes DATABASE_URL (in-memory SQLite) and a synthetic JWT_SECRET — never a
real secret (Quality Gate: no sensitive data in tests, FR-011). Tests that
need another profile override via monkeypatch.

Feature fixtures (research R9): per-test isolated engine (SQLite in-memory,
``StaticPool``), schema created from the shared ``Base`` metadata (the
Alembic upgrade path itself is validated by ``tests/test_migrations.py``),
app-level ``get_session`` override and audit capture.
"""

import os
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import StaticPool, create_engine
from sqlalchemy.orm import Session, sessionmaker

TEST_DATABASE_URL = "sqlite:///:memory:"
TEST_JWT_SECRET = "test-only-synthetic-secret-not-real"
TEST_SENSITIVE_DATA_KEY = "PNCzqoMAz1KHMnG9dMYiwXyv8L53y8MA4msQ0fPSDhw="
TEST_ADMIN_PASSWORD = "synthetic-admin-password-1"

# Essentials also at module level (collection time): test modules importing
# ``passanorte_back.main`` (and, indirectly, ``core.db``, which builds
# Settings) run before any fixture.
os.environ.setdefault("DATABASE_URL", TEST_DATABASE_URL)
os.environ.setdefault("JWT_SECRET", TEST_JWT_SECRET)
os.environ.setdefault("SENSITIVE_DATA_KEY", TEST_SENSITIVE_DATA_KEY)


@pytest.fixture(autouse=True)
def _test_settings_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Synthetic essential environment for every test (autouse)."""
    monkeypatch.setenv("DATABASE_URL", TEST_DATABASE_URL)
    monkeypatch.setenv("JWT_SECRET", TEST_JWT_SECRET)
    # Isolate the tests from any .env present in the checkout.
    monkeypatch.delenv("JWT_TTL", raising=False)
    monkeypatch.delenv("JWT_REFRESH_TTL", raising=False)
    monkeypatch.delenv("ADMIN_USERNAME", raising=False)
    monkeypatch.delenv("ADMIN_PASSWORD", raising=False)
    monkeypatch.delenv("GPS_TOLERANCE_RADIUS_M", raising=False)
    monkeypatch.delenv("CITY_NAME", raising=False)
    monkeypatch.delenv("ENABLED_LANGUAGES", raising=False)
    monkeypatch.delenv("LOCATION_DATA_PATH", raising=False)
    assert os.environ["DATABASE_URL"] == TEST_DATABASE_URL


@pytest.fixture
def db_engine():
    """Isolated engine per test with the feature tables (StaticPool)."""
    # Imports here so collect of unrelated suites does not require the models.
    from passanorte_back.core.db import Base
    from passanorte_back.modules.auth.repositories.admin_users import AdminUser  # noqa: F401
    from passanorte_back.modules.auth.repositories.auth_sessions import AuthSession  # noqa: F401
    from passanorte_back.modules.employees.repositories.employees import Employee  # noqa: F401
    from passanorte_back.modules.tourists.repositories.tourist_interests import (  # noqa: F401
        TouristInterest,
    )
    from passanorte_back.modules.tourists.repositories.tourists import Tourist  # noqa: F401

    engine = create_engine(
        TEST_DATABASE_URL,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    yield engine
    engine.dispose()


@pytest.fixture
def sessionfactory_for(db_engine) -> sessionmaker[Session]:
    from passanorte_back.core.db import get_sessionfactory

    return get_sessionfactory(db_engine)


@pytest.fixture
def client(db_engine, sessionfactory_for: sessionmaker[Session]) -> Iterator[TestClient]:
    """Test app with ``get_session`` overridden to the isolated database."""
    from fastapi.testclient import TestClient as _Client

    from passanorte_back.core.db import get_session, session_scope
    from passanorte_back.main import app

    def _override() -> Iterator[Session]:
        yield from session_scope(sessionfactory_for)

    app.dependency_overrides[get_session] = _override
    yield _Client(app, raise_server_exceptions=False)
    app.dependency_overrides.clear()


@pytest.fixture
def seeded_admin(sessionfactory_for: sessionmaker[Session]) -> int:
    """Active bootstrap-flagged admin (id returned) with a synthetic password."""
    from passanorte_back.core.security import hash_password
    from passanorte_back.modules.auth.repositories.admin_users import AdminUser

    with sessionfactory_for() as session:
        admin = AdminUser(
            username="admin.panel",
            password_hash=hash_password(TEST_ADMIN_PASSWORD),
            role="admin",
            is_active=True,
            is_bootstrap=True,
        )
        session.add(admin)
        session.commit()
        return admin.id


@pytest.fixture
def seeded_employee(sessionfactory_for: sessionmaker[Session]) -> int:
    """Active employee (id returned) with a synthetic password."""
    from passanorte_back.core.security import hash_password
    from passanorte_back.modules.employees.repositories.employees import Employee

    with sessionfactory_for() as session:
        employee = Employee(
            name="Maria Souza",
            username="maria.panel",
            password_hash=hash_password("synthetic-employee-password-1"),
            role="employee",
            status="active",
        )
        session.add(employee)
        session.commit()
        return employee.id


@pytest.fixture
def audit_logs(caplog):
    """Capture structured audit lines (logger propagates to root)."""
    import logging

    caplog.set_level(logging.INFO, logger="passanorte.audit")
    return caplog
