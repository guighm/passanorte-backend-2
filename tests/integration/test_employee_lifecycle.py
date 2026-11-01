"""Integration: employee lifecycle (US5 — SC-003; FR-012/FR-013).

create → edit → revoke → login blocked, then reactivation (clar. Q3-s3):
new login works, pre-revocation sessions stay rejected. Also: 404 for
unknown ids, 422 for status=revoked via PATCH, audit trail (FR-014).
"""

import pytest
from fastapi.testclient import TestClient

from tests.conftest import TEST_ADMIN_PASSWORD

EMPLOYEES_URL = "/api/v1/employees"
LOGIN_URL = "/api/v1/auth/login"


@pytest.fixture
def admin_headers(client: TestClient) -> dict[str, str]:
    login = client.post(
        LOGIN_URL, json={"username": "admin.panel", "password": TEST_ADMIN_PASSWORD}
    )
    return {"Authorization": f"Bearer {login.json()['accessToken']}"}


def _new_employee(client: TestClient, headers: dict[str, str]) -> dict:
    response = client.post(
        EMPLOYEES_URL,
        json={"name": "Maria Souza", "username": "maria.souza"},
        headers=headers,
    )
    assert response.status_code == 201
    return response.json()


def _login(client: TestClient, username: str, password: str):
    return client.post(LOGIN_URL, json={"username": username, "password": password})


def test_lifecycle_create_edit_revoke_login_blocked(
    client: TestClient, seeded_admin: int, admin_headers: dict[str, str], audit_logs
) -> None:
    created = _new_employee(client, admin_headers)
    initial_password = created["initialPassword"]

    # The employee logs in right after creation (role restricted).
    employee_login = _login(client, "maria.souza", initial_password)
    assert employee_login.status_code == 200
    assert employee_login.json()["role"] == "employee"

    # EDIT: name change is persisted and returned (FR-012).
    edited = client.patch(
        f"{EMPLOYEES_URL}/{created['id']}",
        json={"name": "Maria Souza e Silva"},
        headers=admin_headers,
    )
    assert edited.status_code == 200
    assert edited.json()["name"] == "Maria Souza e Silva"
    assert (
        client.get(f"{EMPLOYEES_URL}/{created['id']}", headers=admin_headers).json()["name"]
        == "Maria Souza e Silva"
    )

    # REVOKE: immediate effect on live session and new logins (FR-013).
    revoked = client.post(f"{EMPLOYEES_URL}/{created['id']}/revoke", headers=admin_headers)
    assert revoked.status_code == 204

    live = client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {employee_login.json()['accessToken']}"},
    )
    assert live.status_code == 401
    assert _login(client, "maria.souza", initial_password).status_code == 401

    # REACTIVATE via edit (clar. Q3-s3): new login OK, old session stays dead.
    reactivated = client.patch(
        f"{EMPLOYEES_URL}/{created['id']}",
        json={"status": "active"},
        headers=admin_headers,
    )
    assert reactivated.status_code == 200
    assert reactivated.json()["status"] == "active"

    new_login = _login(client, "maria.souza", initial_password)
    assert new_login.status_code == 200
    reopened = client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {employee_login.json()['accessToken']}"},
    )
    assert reopened.status_code == 401  # pre-revocation session remains rejected

    # Audit trail of the whole lifecycle (FR-014).
    messages = [record.message for record in audit_logs.records]
    actions = set()
    for line in messages:
        marker = '"action": "'
        if marker in line:
            actions.add(line.split(marker)[1].split('"')[0])
    assert "employee.create" in actions
    assert "employee.update" in actions
    assert "employee.revoke" in actions
    assert "employee.reactivate" in actions


def test_lifecycle_username_update_flow(
    client: TestClient, seeded_admin: int, admin_headers: dict[str, str]
) -> None:
    created = _new_employee(client, admin_headers)
    edited = client.patch(
        f"{EMPLOYEES_URL}/{created['id']}",
        json={"username": "maria.silva"},
        headers=admin_headers,
    )
    assert edited.status_code == 200
    assert edited.json()["username"] == "maria.silva"
    # The initial password still works for the renamed account.
    assert _login(client, "maria.silva", created["initialPassword"]).status_code == 200


def test_lifecycle_patch_status_revoked_is_422(
    client: TestClient, seeded_admin: int, admin_headers: dict[str, str]
) -> None:
    created = _new_employee(client, admin_headers)
    response = client.patch(
        f"{EMPLOYEES_URL}/{created['id']}",
        json={"status": "revoked"},
        headers=admin_headers,
    )
    assert response.status_code == 422
    assert (
        client.get(f"{EMPLOYEES_URL}/{created['id']}", headers=admin_headers).json()["status"]
        == "active"
    )


def test_lifecycle_unknown_id_is_404_without_side_effects(
    client: TestClient, seeded_admin: int, admin_headers: dict[str, str]
) -> None:
    assert client.get(f"{EMPLOYEES_URL}/999", headers=admin_headers).status_code == 404
    assert (
        client.patch(f"{EMPLOYEES_URL}/999", json={"name": "X"}, headers=admin_headers).status_code
        == 404
    )
    assert client.post(f"{EMPLOYEES_URL}/999/revoke", headers=admin_headers).status_code == 404


def test_lifecycle_revoke_is_idempotent(
    client: TestClient, seeded_admin: int, admin_headers: dict[str, str]
) -> None:
    created = _new_employee(client, admin_headers)
    assert (
        client.post(f"{EMPLOYEES_URL}/{created['id']}/revoke", headers=admin_headers).status_code
        == 204
    )
    assert (
        client.post(f"{EMPLOYEES_URL}/{created['id']}/revoke", headers=admin_headers).status_code
        == 204
    )
