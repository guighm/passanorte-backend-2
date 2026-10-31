"""Contract: employee management endpoints (US4 — contracts/employees.md).

Admin-only: POST creates with a SYSTEM-GENERATED initial password shown
exactly once; list/detail return EmployeeView without credentials;
duplicates -> 409; 401/403 per RBAC.
"""

from fastapi.testclient import TestClient

from tests.conftest import TEST_ADMIN_PASSWORD

EMPLOYEES_URL = "/api/v1/employees"


def _admin_headers(client: TestClient) -> dict[str, str]:
    login = client.post(
        "/api/v1/auth/login",
        json={"username": "admin.panel", "password": TEST_ADMIN_PASSWORD},
    )
    token = login.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def test_create_employee_201_with_one_time_password(
    client: TestClient, seeded_admin: int, audit_logs
) -> None:
    response = client.post(
        EMPLOYEES_URL,
        json={"name": "Maria Souza", "username": "Maria.Souza"},
        headers=_admin_headers(client),
    )
    assert response.status_code == 201
    body = response.json()
    assert body["name"] == "Maria Souza"
    assert body["username"] == "maria.souza"  # case-insensitive canonical storage
    assert body["status"] == "active"
    assert len(body["initial_password"]) >= 12
    # The initial password is not retrievable afterwards (one-time view).
    detail = client.get(f"{EMPLOYEES_URL}/{body['id']}", headers=_admin_headers(client))
    assert detail.status_code == 200
    assert "initial_password" not in detail.json()


def test_create_employee_no_plaintext_password_in_storage(
    client: TestClient, seeded_admin: int, sessionfactory_for, audit_logs
) -> None:
    created = client.post(
        EMPLOYEES_URL,
        json={"name": "Maria Souza", "username": "maria.hash"},
        headers=_admin_headers(client),
    ).json()
    from passanorte_back.modules.employees.repositories.employees import Employee

    with sessionfactory_for() as session:
        employee = session.get(Employee, created["id"])
        assert created["initial_password"] not in employee.password_hash
        assert employee.password_hash.startswith("$2b$")
    # The password is never echoed in the audit trail either.
    for record in audit_logs.records:
        assert created["initial_password"] not in record.getMessage()


def test_create_employee_duplicate_username_is_409(
    client: TestClient, seeded_admin: int, seeded_employee: int
) -> None:
    response = client.post(
        EMPLOYEES_URL,
        json={"name": "Duplicada", "username": "maria.panel"},
        headers=_admin_headers(client),
    )
    assert response.status_code == 409
    # Also conflicting against the ADMIN side of the same username space.
    response = client.post(
        EMPLOYEES_URL,
        json={"name": "Duplicada", "username": "Admin.Panel"},
        headers=_admin_headers(client),
    )
    assert response.status_code == 409


def test_create_employee_username_conflict_is_case_insensitive_for_employees(
    client: TestClient, seeded_admin: int, seeded_employee: int
) -> None:
    response = client.post(
        EMPLOYEES_URL,
        json={"name": "Duplicada", "username": "MARIA.PANEL"},
        headers=_admin_headers(client),
    )
    assert response.status_code == 409


def test_create_employee_request_validation_422(client: TestClient, seeded_admin: int) -> None:
    headers = _admin_headers(client)
    assert client.post(EMPLOYEES_URL, json={"name": "Maria"}, headers=headers).status_code == 422
    assert (
        client.post(
            EMPLOYEES_URL,
            json={"name": "Maria", "username": "", "initial_password": "hacked"},
            headers=headers,
        ).status_code
        == 422
    )  # initial_password is never an accepted request field


def test_employee_list_and_detail_view_without_credentials(
    client: TestClient, seeded_admin: int, seeded_employee: int
) -> None:
    headers = _admin_headers(client)
    listing = client.get(EMPLOYEES_URL, headers=headers)
    assert listing.status_code == 200
    body = listing.json()
    assert body["total"] >= 1
    first = body["items"][0]
    assert set(first) == {"id", "name", "username", "status", "created_at", "updated_at"}

    detail = client.get(f"{EMPLOYEES_URL}/{first['id']}", headers=headers)
    assert detail.status_code == 200
    assert set(detail.json()) == {"id", "name", "username", "status", "created_at", "updated_at"}


def test_employees_endpoints_without_token_are_401(client: TestClient) -> None:
    assert client.get(EMPLOYEES_URL).status_code == 401
    assert client.post(EMPLOYEES_URL, json={"name": "X", "username": "y.z"}).status_code == 401
