"""Unit: RBAC dependencies (get_current_user / require_admin — FR-015).

Contract behavior via a minimal FastAPI app with probe routes:
- missing/invalid/expired token -> 401 (FR-015);
- account revoked at request time -> 401 (FR-013, research R4);
- employee token on admin-only route -> 403; admin token -> allowed (RF03).
"""

from collections.abc import Iterator
from typing import Annotated

import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker

from passanorte_back.core.config import get_settings
from passanorte_back.core.db import get_session, session_scope
from passanorte_back.core.security import create_access_token
from passanorte_back.modules.auth.services.security import (
    AuthenticatedUser,
    get_current_user,
    require_admin,
)

TEST_SECRET = "test-only-synthetic-secret-not-real"


@pytest.fixture
def probed_app(sessionfactory_for: sessionmaker[Session]) -> FastAPI:
    """Minimal app with probe routes wired to the real dependencies."""
    probe = FastAPI()

    def _override() -> Iterator[Session]:
        yield from session_scope(sessionfactory_for)

    probe.dependency_overrides[get_session] = _override

    @probe.get("/probe/me")
    def me(
        user: Annotated[AuthenticatedUser, Depends(get_current_user)],
    ) -> dict[str, object]:
        return {"username": user.username, "role": user.role}

    @probe.get("/probe/admin")
    def admin_area(
        user: Annotated[AuthenticatedUser, Depends(require_admin)],
    ) -> dict[str, object]:
        return {"ok": user.username}

    return probe


@pytest.fixture
def probe_client(probed_app: FastAPI) -> Iterator[TestClient]:
    with TestClient(probed_app) as app_client:
        yield app_client


def _probe_token(sessionfactory_for: sessionmaker, role: str, account_type: str) -> str:
    """Token bound to a real (usable) auth_sessions row — sid matters."""
    from passanorte_back.core.security import (
        generate_refresh_token,
        hash_refresh_token,
    )
    from passanorte_back.modules.auth.repositories.auth_sessions import (
        create_session,
    )

    with sessionfactory_for() as session:
        row = create_session(
            session,
            account_type=account_type,
            account_id=1,
            refresh_token_hash=hash_refresh_token(generate_refresh_token()),
            refresh_ttl=600,
        )
        session.commit()
        return create_access_token(
            account_id=1,
            account_type=account_type,
            role=role,
            session_id=row.id,
            ttl=60,
            secret=get_settings().jwt_secret,
        )


def test_missing_token_is_401(probe_client: TestClient, sessionfactory_for: sessionmaker) -> None:
    assert probe_client.get("/probe/admin").status_code == 401


def test_forged_token_is_401(
    probe_client: TestClient, sessionfactory_for: sessionmaker, seeded_admin: int
) -> None:
    forged = create_access_token(
        account_id=1,
        account_type="admin",
        role="admin",
        session_id=1,  # sid without a session row is ALSO unknown state
        ttl=60,
        secret="forged-with-different-secret-32-bytes-x!!",
    )
    response = probe_client.get("/probe/admin", headers={"Authorization": f"Bearer {forged}"})
    assert response.status_code == 401


def test_expired_token_is_401(
    probe_client: TestClient,
    sessionfactory_for: sessionmaker,
    seeded_admin: int,
) -> None:
    expired = create_access_token(
        account_id=1,
        account_type="admin",
        role="admin",
        session_id=1,
        ttl=-5,
        secret=get_settings().jwt_secret,
    )
    response = probe_client.get("/probe/admin", headers={"Authorization": f"Bearer {expired}"})
    assert response.status_code == 401


def test_revoked_employee_session_is_401_immediately(
    probe_client: TestClient,
    sessionfactory_for: sessionmaker[Session],
    seeded_employee: int,
) -> None:
    """FR-013: revocation kills the in-flight session on the next call."""
    headers = {
        "Authorization": f"Bearer {_probe_token(sessionfactory_for, 'employee', 'employee')}"
    }
    assert probe_client.get("/probe/me", headers=headers).status_code == 200

    with sessionfactory_for() as session:
        employee = session.get(
            __import__(
                "passanorte_back.modules.employees.repositories.employees",
                fromlist=["Employee"],
            ).Employee,
            seeded_employee,
        )
        employee.status = "revoked"
        session.commit()

    assert probe_client.get("/probe/me", headers=headers).status_code == 401
    assert probe_client.get("/probe/admin", headers=headers).status_code == 401


def test_admin_token_on_admin_route_is_allowed(
    probe_client: TestClient,
    sessionfactory_for: sessionmaker,
    seeded_admin: int,
) -> None:
    token = _probe_token(sessionfactory_for, role="admin", account_type="admin")
    response = probe_client.get("/probe/admin", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 200
    assert response.json() == {"ok": "admin.panel"}


def test_employee_token_on_admin_route_is_403(
    probe_client: TestClient,
    sessionfactory_for: sessionmaker,
    seeded_employee: int,
) -> None:
    token = _probe_token(sessionfactory_for, role="employee", account_type="employee")
    response = probe_client.get("/probe/admin", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 403
