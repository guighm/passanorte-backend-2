"""Contract: POST /api/v1/tourists/login + tourist identity (US2; RF23).

Covers contracts/tourists.md: full pair with ``role: "tourist"``, generic
401 on any failure, POST /auth/refresh renewal via the foundation, and the
RBAC behavior of tourist access tokens (self-only routes vs non-tourist
accounts — FR-015).
"""

import pytest

LOGIN_URL = "/api/v1/tourists/login"
REFRESH_URL = "/api/v1/auth/refresh"
ME_URL = "/api/v1/tourists/me"

CREDENTIALS = {"first_name": "Ana", "last_name": "Silva", "country_of_origin": "Brasil"}


@pytest.fixture
def registered_tourist(client) -> dict:
    """A tourist registered via the public API (fixture for login tests)."""
    response = client.post(
        "/api/v1/tourists",
        json={
            **CREDENTIALS,
            "cpf": "123.456.789-09",
            "passport_number": None,
            "phone": "+5511999999999",
            "email": "ana@example.com",
            "password": "long-enough-password-1",
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def _login(client, email: str, password: str):
    return client.post(LOGIN_URL, json={"email": email, "password": password})


def test_login_correct_credentials_returns_pair_with_tourist_role(
    client, registered_tourist
) -> None:
    response = _login(client, "ana@example.com", "long-enough-password-1")
    assert response.status_code == 200
    body = response.json()
    assert set(body) == {"access_token", "refresh_token", "token_type", "expires_in", "role"}
    assert body["role"] == "tourist"
    assert body["token_type"] == "bearer"
    assert body["access_token"] and body["refresh_token"]
    assert body["expires_in"] > 0


def test_login_wrong_password_is_401_generic(client, registered_tourist) -> None:
    response = _login(client, "ana@example.com", "definitely-wrong-password")
    assert response.status_code == 401
    assert response.json() == {"detail": "invalid credentials"}


def test_login_unknown_email_is_same_generic_401(client, registered_tourist) -> None:
    """FR-014: unknown email is indistinguishable from a wrong password."""
    response = _login(client, "nobody@example.com", "whatever-password-1")
    assert response.status_code == 401
    assert response.json() == {"detail": "invalid credentials"}


def test_login_normalizes_email_trim_and_case(client, registered_tourist) -> None:
    """FR-013: ' ana@example.com ' (spaces/case) logs in the same."""
    response = _login(client, "  Ana@Example.COM ", "long-enough-password-1")
    assert response.status_code == 200


def test_login_body_schema_validation_is_422(client) -> None:
    assert client.post(LOGIN_URL, json={"email": "bad"}).status_code == 422
    assert client.post(LOGIN_URL, json={"email": "ana@example.com"}).status_code == 422


def test_refresh_with_tourist_refresh_token_renews_pair(client, registered_tourist) -> None:
    pair = _login(client, "ana@example.com", "long-enough-password-1").json()
    response = client.post(REFRESH_URL, json={"refresh_token": pair["refresh_token"]})
    assert response.status_code == 200
    body = response.json()
    assert body["role"] == "tourist"
    assert body["refresh_token"] != pair["refresh_token"]


def test_refresh_reuse_of_tourist_token_is_401(client, registered_tourist) -> None:
    pair = _login(client, "ana@example.com", "long-enough-password-1").json()
    assert (
        client.post(REFRESH_URL, json={"refresh_token": pair["refresh_token"]}).status_code == 200
    )
    assert (
        client.post(REFRESH_URL, json={"refresh_token": pair["refresh_token"]}).status_code == 401
    )


def test_get_me_with_tourist_token_is_200(client, registered_tourist) -> None:
    """Real use of the issued token (US2 independent test)."""
    pair = _login(client, "ana@example.com", "long-enough-password-1").json()
    response = client.get(ME_URL, headers={"Authorization": f"Bearer {pair['access_token']}"})
    assert response.status_code == 200


def test_get_me_without_token_is_401(client) -> None:
    assert client.get(ME_URL).status_code == 401


def test_get_me_with_admin_token_is_403(client, seeded_admin: int, registered_tourist) -> None:
    """FR-015: tourist-exclusive routes reject non-tourist accounts."""
    from tests.conftest import TEST_ADMIN_PASSWORD

    pair = client.post(
        "/api/v1/auth/login",
        json={"username": "admin.panel", "password": TEST_ADMIN_PASSWORD},
    ).json()
    response = client.get(ME_URL, headers={"Authorization": f"Bearer {pair['access_token']}"})
    assert response.status_code == 403
