"""Integration: admin bootstrap script (US1 — RF01; clar. Q4-s5).

(a) create on empty database; (b) rerun idempotence; (c) rerun with
changed env updates the SAME account in place; (d) missing env fails
without DB change; (e) no plaintext password anywhere (RNF10, FR-002);
(f) audit entry emitted (RNF19).
"""

import pytest
from sqlalchemy import StaticPool, create_engine
from sqlalchemy.orm import sessionmaker

from passanorte_back.core.db import Base
from passanorte_back.modules.auth.repositories.admin_users import AdminUser
from passanorte_back.modules.employees.repositories.employees import Employee

# imports exercised by the tests (fail red while missing — T010/T014)
from passanorte_back.scripts.create_admin import run_bootstrap

SYNTHETIC_ADMIN_PASSWORD_A = "synthetic-bootstrap-password-A1"
SYNTHETIC_ADMIN_PASSWORD_B = "synthetic-bootstrap-password-B2"


@pytest.fixture
def isolated_engine():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    yield engine
    engine.dispose()


@pytest.fixture
def isolated_sessionfactory(isolated_engine) -> sessionmaker:
    from passanorte_back.core.db import get_sessionfactory

    return get_sessionfactory(isolated_engine)


def _admin_rows(sessionfactory: sessionmaker) -> list[AdminUser]:
    with sessionfactory() as session:
        return list(session.query(AdminUser).all())


def test_creates_account_on_empty_database(
    isolated_sessionfactory: sessionmaker,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ADMIN_USERNAME", "primary.admin")
    monkeypatch.setenv("ADMIN_PASSWORD", SYNTHETIC_ADMIN_PASSWORD_A)
    run_bootstrap(isolated_sessionfactory)

    rows = _admin_rows(isolated_sessionfactory)
    assert len(rows) == 1
    admin = rows[0]
    assert admin.username == "primary.admin"
    assert admin.role == "admin"
    assert admin.is_active is True
    assert admin.is_bootstrap is True
    assert SYNTHETIC_ADMIN_PASSWORD_A not in admin.password_hash
    from passanorte_back.core.security import verify_password

    assert verify_password(SYNTHETIC_ADMIN_PASSWORD_A, admin.password_hash)


def test_rerun_is_idempotent(
    isolated_sessionfactory: sessionmaker,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ADMIN_USERNAME", "primary.admin")
    monkeypatch.setenv("ADMIN_PASSWORD", SYNTHETIC_ADMIN_PASSWORD_A)
    run_bootstrap(isolated_sessionfactory)
    run_bootstrap(isolated_sessionfactory)

    rows = _admin_rows(isolated_sessionfactory)
    assert len(rows) == 1
    assert rows[0].username == "primary.admin"


def test_rerun_with_changed_credentials_updates_in_place(
    isolated_sessionfactory: sessionmaker,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Clar. Q4-s5: same bootstrap designation, updated in place."""
    monkeypatch.setenv("ADMIN_USERNAME", "old.admin")
    monkeypatch.setenv("ADMIN_PASSWORD", SYNTHETIC_ADMIN_PASSWORD_A)
    run_bootstrap(isolated_sessionfactory)
    first_id = _admin_rows(isolated_sessionfactory)[0].id

    monkeypatch.setenv("ADMIN_USERNAME", "new.admin")
    monkeypatch.setenv("ADMIN_PASSWORD", SYNTHETIC_ADMIN_PASSWORD_B)
    run_bootstrap(isolated_sessionfactory)

    rows = _admin_rows(isolated_sessionfactory)
    assert len(rows) == 1  # no second account
    admin = rows[0]
    assert admin.id == first_id  # same row updated in place
    assert admin.username == "new.admin"
    from passanorte_back.core.security import verify_password

    assert verify_password(SYNTHETIC_ADMIN_PASSWORD_B, admin.password_hash)
    assert not verify_password(SYNTHETIC_ADMIN_PASSWORD_A, admin.password_hash)
    assert admin.is_active is True


def test_missing_env_fails_without_database_change(
    isolated_sessionfactory: sessionmaker,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("ADMIN_USERNAME", raising=False)
    monkeypatch.delenv("ADMIN_PASSWORD", raising=False)
    with pytest.raises(RuntimeError, match="ADMIN_USERNAME|ADMIN_PASSWORD"):
        run_bootstrap(isolated_sessionfactory)
    assert _admin_rows(isolated_sessionfactory) == []


def test_missing_env_keeps_existing_account(
    isolated_sessionfactory: sessionmaker,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ADMIN_USERNAME", "primary.admin")
    monkeypatch.setenv("ADMIN_PASSWORD", SYNTHETIC_ADMIN_PASSWORD_A)
    run_bootstrap(isolated_sessionfactory)

    monkeypatch.delenv("ADMIN_PASSWORD", raising=False)
    monkeypatch.setenv("ADMIN_USERNAME", "primary.admin")
    with pytest.raises(RuntimeError):
        run_bootstrap(isolated_sessionfactory)
    rows = _admin_rows(isolated_sessionfactory)
    assert len(rows) == 1
    assert rows[0].is_active is True


def test_employees_untouched_by_bootstrap(
    isolated_sessionfactory: sessionmaker,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ADMIN_USERNAME", "primary.admin")
    monkeypatch.setenv("ADMIN_PASSWORD", SYNTHETIC_ADMIN_PASSWORD_A)
    run_bootstrap(isolated_sessionfactory)
    with isolated_sessionfactory() as session:
        assert session.query(Employee).all() == []


def test_bootstrap_writes_audit_entry(
    isolated_sessionfactory: sessionmaker,
    monkeypatch: pytest.MonkeyPatch,
    audit_logs,
) -> None:
    monkeypatch.setenv("ADMIN_USERNAME", "primary.admin")
    monkeypatch.setenv("ADMIN_PASSWORD", SYNTHETIC_ADMIN_PASSWORD_A)
    run_bootstrap(isolated_sessionfactory)

    lines = [record.message for record in audit_logs.records]
    assert any('"action": "bootstrap.upsert"' in line for line in lines), lines
