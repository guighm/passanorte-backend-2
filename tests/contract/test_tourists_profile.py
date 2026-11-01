"""Contract: tourist profile — GET/PATCH /tourists/{id} and /me (US3; RF24).

Covers contracts/tourists.md: controlled decryption for self (FR-006/007),
403 for the other tourist (SC-004 — nothing changes), partial PATCH with
document XOR, 409 on uniqueness collisions, admin access to any tourist and
404 for missing targets, 401 without token.
"""

import pytest

REGISTER_URL = "/api/v1/tourists"
ME_URL = "/api/v1/tourists/me"


def _register(
    client, *, email: str, cpf: str | None = "123.456.789-09", passport_number: str | None = None
) -> dict:
    """Register a tourist (cpf digits are synthetic VALID examples only)."""
    response = client.post(
        REGISTER_URL,
        json={
            "first_name": "Ana",
            "last_name": "Silva",
            "country_of_origin": "Brasil",
            "cpf": cpf,
            "passport_number": passport_number,
            "phone": "+5511999999999",
            "email": email,
            "password": "long-enough-password-1",
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def _login(client, email: str, password: str = "long-enough-password-1"):
    return client.post("/api/v1/tourists/login", json={"email": email, "password": password}).json()


@pytest.fixture
def tourist_a(client) -> dict:
    return _register(client, email="ana@example.com")


@pytest.fixture
def tourist_b(client) -> dict:
    return _register(client, email="bruna@example.com", cpf="111.444.777-35")


def _auth_bearer(access_token: str) -> dict:
    return {"Authorization": f"Bearer {access_token}"}


def test_get_me_returns_decrypted_self_profile(client, tourist_a: dict) -> None:
    """FR-006/FR-007: own values legible; no interests saved yet."""
    pair = _login(client, "ana@example.com")
    response = client.get(ME_URL, headers=_auth_bearer(pair["access_token"]))
    assert response.status_code == 200
    body = response.json()
    assert body["email"] == "ana@example.com"
    assert body["phone"] == "+5511999999999"
    assert body["cpf"] == "12345678909"
    assert body["passport_number"] is None
    assert body["interests"] == []
    assert body["id"] == tourist_a["id"]
    assert not any(key.endswith(("_encrypted", "_lookup", "password_hash")) for key in body)


def test_get_other_tourist_profile_is_403_and_leaks_nothing(
    client, tourist_a: dict, tourist_b: dict, sessionfactory_for
) -> None:
    """SC-004: another tourist → 403, no existence leak."""
    pair = _login(client, "bruna@example.com")
    response = client.get(
        f"/api/v1/tourists/{tourist_a['id']}", headers=_auth_bearer(pair["access_token"])
    )
    assert response.status_code == 403
    assert response.json() == {"detail": "insufficient permissions"}


def test_patch_other_tourist_profile_is_403_and_target_unchanged(
    client, tourist_a: dict, tourist_b: dict, sessionfactory_for
) -> None:
    """SC-004: denial does not change the target (FR-009)."""
    pair = _login(client, "bruna@example.com")
    response = client.patch(
        f"/api/v1/tourists/{tourist_a['id']}",
        headers=_auth_bearer(pair["access_token"]),
        json={"country_of_origin": "Invadido"},
    )
    assert response.status_code == 403

    from passanorte_back.modules.tourists.repositories.tourists import Tourist

    with sessionfactory_for() as session:
        target = session.get(Tourist, tourist_a["id"])
        assert target.country_of_origin == "Brasil"


def test_patch_me_updates_country_and_phone(client, tourist_a: dict) -> None:
    pair = _login(client, "ana@example.com")
    response = client.patch(
        ME_URL.replace("/me", f"/{tourist_a['id']}"),
        headers=_auth_bearer(pair["access_token"]),
        json={"country_of_origin": "Argentina", "phone": "+541155500000"},
    )
    assert response.status_code == 204, response.text

    profile = client.get(ME_URL, headers=_auth_bearer(pair["access_token"])).json()
    assert profile["country_of_origin"] == "Argentina"
    assert profile["phone"] == "+541155500000"


def test_patch_document_swap_is_accepted(client, tourist_a: dict) -> None:
    pair = _login(client, "ana@example.com")
    response = client.patch(
        f"/api/v1/tourists/{tourist_a['id']}",
        headers=_auth_bearer(pair["access_token"]),
        json={"cpf": None, "passport_number": "AB123456"},
    )
    assert response.status_code == 204, response.text
    profile = client.get(ME_URL, headers=_auth_bearer(pair["access_token"])).json()
    assert profile["cpf"] is None
    assert profile["passport_number"] == "AB123456"


def test_patch_removing_the_document_is_422(client) -> None:
    """Contract: final result with NO document → 422 (a tourist that only
    holds a passport, removing it)."""
    registered = _register(client, email="erin@example.com", cpf=None, passport_number="AB123456")
    pair = _login(client, "erin@example.com")
    response = client.patch(
        f"/api/v1/tourists/{registered['id']}",
        headers=_auth_bearer(pair["access_token"]),
        json={"passport_number": None},
    )
    assert response.status_code == 422
    # A no-op removal against a tourist holding the OTHER document is fine.
    response = client.patch(
        f"/api/v1/tourists/{registered['id']}",
        headers=_auth_bearer(pair["access_token"]),
        json={"cpf": "111.444.777-35"},
    )
    assert response.status_code == 204


def test_patch_email_to_taken_is_409(client, tourist_a: dict, tourist_b: dict) -> None:
    pair = _login(client, "ana@example.com")
    response = client.patch(
        f"/api/v1/tourists/{tourist_a['id']}",
        headers=_auth_bearer(pair["access_token"]),
        json={"email": "bruna@example.com"},
    )
    assert response.status_code == 409


def test_patch_invalid_fields_are_422(client, tourist_a: dict) -> None:
    pair = _login(client, "ana@example.com")
    response = client.patch(
        f"/api/v1/tourists/{tourist_a['id']}",
        headers=_auth_bearer(pair["access_token"]),
        json={"phone": "5511999999999"},
    )
    assert response.status_code == 422
    response = client.patch(
        f"/api/v1/tourists/{tourist_a['id']}",
        headers=_auth_bearer(pair["access_token"]),
        json={"email": "not-an-email"},
    )
    assert response.status_code == 422


def test_patch_password_field_is_ignored_or_rejected(client, tourist_a: dict) -> None:
    """Password changing is out of scope (contract — schema forbids it)."""
    pair = _login(client, "ana@example.com")
    response = client.patch(
        f"/api/v1/tourists/{tourist_a['id']}",
        headers=_auth_bearer(pair["access_token"]),
        json={"password": "another-password-1"},
    )
    assert response.status_code == 422  # extra="forbid"


def test_admin_gets_and_patches_any_tourist(client, tourist_a: dict, seeded_admin: int) -> None:
    from tests.conftest import TEST_ADMIN_PASSWORD

    pair = client.post(
        "/api/v1/auth/login",
        json={"username": "admin.panel", "password": TEST_ADMIN_PASSWORD},
    ).json()
    headers = _auth_bearer(pair["access_token"])

    response = client.get(f"/api/v1/tourists/{tourist_a['id']}", headers=headers)
    assert response.status_code == 200  # admin access (principle I)
    assert response.json()["email"] == "ana@example.com"

    response = client.patch(
        f"/api/v1/tourists/{tourist_a['id']}", headers=headers, json={"last_name": "Editada"}
    )
    assert response.status_code == 204

    response = client.get("/api/v1/tourists/999", headers=headers)
    assert response.status_code == 404


def test_get_me_without_token_is_401(client, tourist_a: dict) -> None:
    assert client.get(ME_URL).status_code == 401
    assert client.get("/api/v1/tourists/999").status_code == 401
