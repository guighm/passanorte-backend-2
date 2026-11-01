"""Contract: interest categories and tourist interests (US4; RF25).

Covers contracts/tourists.md: categories == exactly the location.json
config (RNF06/SC-006), integral replacement (FR-010), invalid category →
422 naming it (FR-011), no quantity cap (s3-Q1), input duplicates normalized,
empty selection, 403 for non-tourists (FR-015), 401 without token.
"""

import json
import pathlib

import pytest
from fastapi.testclient import TestClient

CATEGORIES_URL = "/api/v1/tourists/interest-categories"
MY_INTERESTS_URL = "/api/v1/tourists/me/interests"

REGISTER_URL = "/api/v1/tourists"
LOGIN_URL = "/api/v1/tourists/login"


def _register_and_login(client: TestClient, email: str = "ana@example.com") -> str:
    """Register + login; returns the bearer-ready access token."""
    response = client.post(
        REGISTER_URL,
        json={
            "first_name": "Ana",
            "last_name": "Silva",
            "country_of_origin": "Brasil",
            "cpf": "123.456.789-09",
            "passport_number": None,
            "phone": "+5511999999999",
            "email": email,
            "password": "long-enough-password-1",
        },
    )
    assert response.status_code == 201, response.text
    pair = client.post(
        LOGIN_URL, json={"email": email, "password": "long-enough-password-1"}
    ).json()
    return pair["access_token"]


@pytest.fixture
def tourist_token(client) -> str:
    return _register_and_login(client)


def test_list_categories_matches_location_config(client, seeded_admin: int) -> None:
    """SC-006/FR-012: exactly the location.json categories, any auth account."""
    from tests.conftest import TEST_ADMIN_PASSWORD

    pair = client.post(
        "/api/v1/auth/login",
        json={"username": "admin.panel", "password": TEST_ADMIN_PASSWORD},
    ).json()
    response = client.get(
        CATEGORIES_URL, headers={"Authorization": f"Bearer {pair['access_token']}"}
    )
    assert response.status_code == 200

    config = json.loads((pathlib.Path("config/location.json")).read_text(encoding="utf-8"))
    expected = [
        {"key": item["key"], "label": item["label"]} for item in config["interest_categories"]
    ]
    assert response.json() == {"categories": expected}


def test_list_categories_without_token_is_401(client) -> None:
    assert client.get(CATEGORIES_URL).status_code == 401


def test_get_interests_without_selection_is_empty_list(client, tourist_token: str) -> None:
    """Edge case: no selection → [] without error."""
    response = client.get(MY_INTERESTS_URL, headers={"Authorization": f"Bearer {tourist_token}"})
    assert response.status_code == 200
    assert response.json() == {"interests": []}


def test_put_interests_replaces_selection(client, tourist_token: str) -> None:
    headers = {"Authorization": f"Bearer {tourist_token}"}
    response = client.put(
        MY_INTERESTS_URL, headers=headers, json={"interests": ["gastronomy", "nature"]}
    )
    assert response.status_code == 200
    assert response.json() == {"interests": ["gastronomy", "nature"]}

    # Integral update: swap one, add another — no residue (FR-010).
    response = client.put(MY_INTERESTS_URL, headers=headers, json={"interests": ["culture"]})
    assert response.json() == {"interests": ["culture"]}

    # GET /me reflects the profile too.
    profile = client.get("/api/v1/tourists/me", headers=headers).json()
    assert profile["interests"] == ["culture"]


def test_put_invalid_category_is_422_naming_it(client, tourist_token: str) -> None:
    response = client.put(
        MY_INTERESTS_URL,
        headers={"Authorization": f"Bearer {tourist_token}"},
        json={"interests": ["xpto"]},
    )
    assert response.status_code == 422
    assert "xpto" in response.text


def test_put_all_configured_categories_is_valid(client, tourist_token: str) -> None:
    """s3-Q1: no artificial cap — selecting every configured category."""
    config = json.loads(pathlib.Path("config/location.json").read_text(encoding="utf-8"))
    every = [item["key"] for item in config["interest_categories"]]
    response = client.put(
        MY_INTERESTS_URL,
        headers={"Authorization": f"Bearer {tourist_token}"},
        json={"interests": every},
    )
    assert response.status_code == 200
    assert sorted(response.json()["interests"]) == sorted(every)


def test_put_duplicate_keys_are_normalized(client, tourist_token: str) -> None:
    response = client.put(
        MY_INTERESTS_URL,
        headers={"Authorization": f"Bearer {tourist_token}"},
        json={"interests": ["gastronomy", "gastronomy", "nature"]},
    )
    assert response.status_code == 200

    stored = client.get(
        MY_INTERESTS_URL, headers={"Authorization": f"Bearer {tourist_token}"}
    ).json()
    assert stored["interests"] == ["gastronomy", "nature"]


def test_put_empty_list_clears_selection(client, tourist_token: str) -> None:
    headers = {"Authorization": f"Bearer {tourist_token}"}
    assert (
        client.put(MY_INTERESTS_URL, headers=headers, json={"interests": ["nature"]}).status_code
        == 200
    )
    response = client.put(MY_INTERESTS_URL, headers=headers, json={"interests": []})
    assert response.status_code == 200
    assert response.json() == {"interests": []}


def test_put_interests_without_token_is_401(client) -> None:
    assert client.put(MY_INTERESTS_URL, json={"interests": []}).status_code == 401
    assert client.get(MY_INTERESTS_URL).status_code == 401


def test_put_interests_by_admin_or_employee_is_403(
    client, seeded_admin: int, seeded_employee: int
) -> None:
    """FR-015: tourist-exclusive routes reject the panel accounts."""
    from tests.conftest import TEST_ADMIN_PASSWORD

    admin_pair = client.post(
        "/api/v1/auth/login",
        json={"username": "admin.panel", "password": TEST_ADMIN_PASSWORD},
    ).json()
    response = client.put(
        MY_INTERESTS_URL,
        headers={"Authorization": f"Bearer {admin_pair['access_token']}"},
        json={"interests": ["nature"]},
    )
    assert response.status_code == 403

    pair = client.post(
        "/api/v1/auth/login",
        json={"username": "maria.panel", "password": "synthetic-employee-password-1"},
    ).json()
    response = client.get(
        MY_INTERESTS_URL, headers={"Authorization": f"Bearer {pair['access_token']}"}
    )
    assert response.status_code == 403
