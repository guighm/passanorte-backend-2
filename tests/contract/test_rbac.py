"""Contract: RBAC on the panel endpoints (US3 — FR-008/009/015).

GET /api/v1/auth/me (any authenticated role) and the admin-only
/employees endpoints (employee token -> 403; admin token -> allowed;
no token -> 401). Dashboard/tourist-spots blocking (FR-009) is validated
at the dependency level in tests/unit/test_rbac_dependencies.py + via the
require_admin reutilized by future features (analyze F1 deferral note in
tasks.md Phase 5).
"""

from fastapi.testclient import TestClient

from tests.conftest import TEST_ADMIN_PASSWORD

ME_URL = "/api/v1/auth/me"
EMPLOYEES_URL = "/api/v1/employees"


def _login_as_admin(client: TestClient) -> dict[str, str]:
    response = client.post(
        "/api/v1/auth/login",
        json={"username": "admin.panel", "password": TEST_ADMIN_PASSWORD},
    )
    assert response.status_code == 200
    return response.json()


def _login_as_employee(client: TestClient) -> dict[str, str]:
    response = client.post(
        "/api/v1/auth/login",
        json={"username": "maria.panel", "password": "synthetic-employee-password-1"},
    )
    assert response.status_code == 200
    return response.json()


def test_me_without_token_is_401(client: TestClient) -> None:
    assert client.get(ME_URL).status_code == 401


def test_me_with_admin_token_returns_admin_identity(client: TestClient, seeded_admin: int) -> None:
    tokens = _login_as_admin(client)
    response = client.get(ME_URL, headers={"Authorization": f"Bearer {tokens['access_token']}"})
    assert response.status_code == 200
    body = response.json()
    assert body == {"username": "admin.panel", "role": "admin"}


def test_me_with_employee_token_returns_employee_identity(
    client: TestClient, seeded_admin: int, seeded_employee: int
) -> None:
    tokens = _login_as_employee(client)
    response = client.get(ME_URL, headers={"Authorization": f"Bearer {tokens['access_token']}"})
    assert response.status_code == 200
    assert response.json() == {"username": "maria.panel", "role": "employee"}


def test_employee_token_is_403_on_admin_endpoints(
    client: TestClient, seeded_admin: int, seeded_employee: int
) -> None:
    """RBAC: employees cannot manage employees/panel resources (FR-008,
    FR-009 dependency-level coverage; contracts/employees.md)."""
    employee_headers = {"Authorization": f"Bearer {_login_as_employee(client)['access_token']}"}

    assert (
        client.post(
            EMPLOYEES_URL,
            json={"name": "Novo", "username": "novo.f"},
            headers=employee_headers,
        ).status_code
        == 403
    )
    assert client.get(EMPLOYEES_URL, headers=employee_headers).status_code == 403
    assert client.get(f"{EMPLOYEES_URL}/1", headers=employee_headers).status_code == 403
    assert (
        client.patch(f"{EMPLOYEES_URL}/1", json={"name": "X"}, headers=employee_headers).status_code
        == 403
    )
    assert client.post(f"{EMPLOYEES_URL}/1/revoke", headers=employee_headers).status_code == 403


def test_admin_token_is_allowed_on_admin_endpoints(client: TestClient, seeded_admin: int) -> None:
    admin_headers = {"Authorization": f"Bearer {_login_as_admin(client)['access_token']}"}

    created = client.post(
        EMPLOYEES_URL,
        json={"name": "Novo", "username": "novo.f"},
        headers=admin_headers,
    )
    assert created.status_code == 201  # FR-008: admin has total access
    assert client.get(EMPLOYEES_URL, headers=admin_headers).status_code == 200
