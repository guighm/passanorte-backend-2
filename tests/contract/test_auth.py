"""Contract: /api/v1/auth — login, refresh, logout, 401-without-token (US2).

Covers the acceptance contract (contracts/auth.md — clar. Q1/Q2/Q3-s1):
login valid/invalid (401, generic message), renewal pair single-use,
logout revoking the refresh credential, 401 without a bearer token.
"""

import datetime as dt

LOGIN_URL = "/api/v1/auth/login"
REFRESH_URL = "/api/v1/auth/refresh"
LOGOUT_URL = "/api/v1/auth/logout"


def _login(client, username: str, password: str):
    return client.post(LOGIN_URL, json={"username": username, "password": password})


def test_login_admin_returns_pair_and_role(client, seeded_admin: int, audit_logs) -> None:
    from tests.conftest import TEST_ADMIN_PASSWORD

    response = _login(client, "admin.panel", TEST_ADMIN_PASSWORD)
    assert response.status_code == 200
    body = response.json()
    assert set(body) == {"access_token", "refresh_token", "token_type", "expires_in", "role"}
    assert body["token_type"] == "bearer"
    assert body["role"] == "admin"
    assert body["access_token"] and body["refresh_token"]
    assert body["expires_in"] > 0


def test_login_employee_returns_pair_and_restricted_role(
    client, seeded_admin: int, seeded_employee: int
) -> None:
    password = "synthetic-employee-password-1"
    response = _login(client, "maria.panel", password)
    assert response.status_code == 200
    body = response.json()
    assert body["role"] == "employee"


def test_login_wrong_password_is_401_generic(client, seeded_admin: int, audit_logs) -> None:
    response = _login(client, "admin.panel", "definitely-wrong-password")
    assert response.status_code == 401
    assert response.json() == {"detail": "invalid credentials"}


def test_login_unknown_user_is_401_generic(client, seeded_admin: int, audit_logs) -> None:
    response = _login(client, "nobody.here", "whatever-password-1")
    assert response.status_code == 401


def test_login_revoked_employee_is_401(
    client, seeded_admin: int, seeded_employee: int, sessionfactory_for
) -> None:
    from passanorte_back.modules.employees.repositories.employees import Employee

    with sessionfactory_for() as session:
        session.get(Employee, seeded_employee).status = "revoked"
        session.commit()
    response = _login(client, "maria.panel", "synthetic-employee-password-1")
    assert response.status_code == 401


def test_login_body_schema_validation_is_422(client) -> None:
    assert client.post(LOGIN_URL, json={"username": "x"}).status_code == 422
    assert client.post(LOGIN_URL, json={"username": "", "password": "y"}).status_code == 422


def test_refresh_issues_new_pair_single_use(client, seeded_admin: int) -> None:
    from tests.conftest import TEST_ADMIN_PASSWORD

    pair = _login(client, "admin.panel", TEST_ADMIN_PASSWORD).json()
    refresh_token = pair["refresh_token"]

    response = client.post(REFRESH_URL, json={"refresh_token": refresh_token})
    assert response.status_code == 200
    new_pair = response.json()
    assert new_pair["role"] == "admin"
    assert new_pair["refresh_token"] != refresh_token

    reused = client.post(REFRESH_URL, json={"refresh_token": refresh_token})
    assert reused.status_code == 401  # single-use (clar. Q1)

    again = client.post(REFRESH_URL, json={"refresh_token": new_pair["refresh_token"]})
    assert again.status_code == 200  # the new credential is still valid


def test_refresh_invalid_or_unknown_is_401(client, seeded_admin: int) -> None:
    assert client.post(REFRESH_URL, json={"refresh_token": "no-such-credential"}).status_code == 401
    assert client.post(REFRESH_URL, json={}).status_code == 422


def test_refresh_expired_session_is_401(client, seeded_admin: int, sessionfactory_for) -> None:
    from passanorte_back.core.security import hash_refresh_token
    from tests.conftest import TEST_ADMIN_PASSWORD

    pair = _login(client, "admin.panel", TEST_ADMIN_PASSWORD).json()
    # Expire the underlying session row directly (time-based eligibility).
    with sessionfactory_for() as session:
        from passanorte_back.modules.auth.repositories.auth_sessions import AuthSession

        row = (
            session.query(AuthSession)
            .filter_by(refresh_token_hash=hash_refresh_token(pair["refresh_token"]))
            .one()
        )
        row.expires_at = dt.datetime.now(dt.UTC) - dt.timedelta(seconds=1)
        session.commit()
    response = client.post(REFRESH_URL, json={"refresh_token": pair["refresh_token"]})
    assert response.status_code == 401


def test_logout_invalidates_refresh_credential(client, seeded_admin: int) -> None:
    from tests.conftest import TEST_ADMIN_PASSWORD

    pair = _login(client, "admin.panel", TEST_ADMIN_PASSWORD).json()
    headers = {"Authorization": f"Bearer {pair['access_token']}"}

    response = client.post(LOGOUT_URL, headers=headers)
    assert response.status_code == 204

    assert (
        client.post(REFRESH_URL, json={"refresh_token": pair["refresh_token"]}).status_code == 401
    )
    # Stricter-than-contract behavior (T031): the WHOLE session dies at
    # logout — the access credential is also rejected immediately via the
    # per-request session-state revalidation (FR-016 + FR-013 machinery).
    assert client.post(LOGOUT_URL, headers=headers).status_code == 401
    me = client.get("/api/v1/auth/me", headers=headers)
    assert me.status_code == 401


def test_logout_without_token_is_401(client) -> None:
    assert client.post(LOGOUT_URL).status_code == 401


def test_login_and_logout_are_audited(client, seeded_admin: int, audit_logs) -> None:
    from tests.conftest import TEST_ADMIN_PASSWORD

    pair = _login(client, "admin.panel", TEST_ADMIN_PASSWORD).json()
    client.post(LOGOUT_URL, headers={"Authorization": f"Bearer {pair['access_token']}"})
    _login(client, "admin.panel", "wrong-password-forever")

    lines = [record.message for record in audit_logs.records]
    assert any('"action": "login.success"' in line for line in lines)
    assert any('"action": "logout"' in line for line in lines)
    assert any('"action": "login.failure"' in line for line in lines)
