"""Contract: per-spot tolerance radius delta (feature 011, contract §4).

The ``toleranceRadiusM`` field rides the existing tourist-spots CRUD
(owner module of the column; analyze C2 companion test for the WGS-84 422
cases lives in ``test_visitation.py``). Semantics: positive float when
present; absent in create/PATCH keeps the global default semantics
(``None`` ⇒ ``settings.gps_tolerance_radius_m`` = 100 m, research R2);
explicit ``toleranceRadiusM: null`` in a PATCH resets the override;
``0`` and negatives are rejected 422.
"""

from fastapi.testclient import TestClient

from tests.conftest import TEST_ADMIN_PASSWORD

SPOTS_URL = "/api/v1/tourist-spots"

VALID_CREATE = {
    "name": "Mirante Pedra do Bauzinho",
    "description": "Mirante com vista para o vale e trilha curta.",
    "latitude": -22.7271,
    "longitude": -45.0366,
    "categories": ["nature"],
    "schedule": [{"weekday": "saturday", "opensAt": "08:30", "closesAt": "17:00"}],
}


def _admin_headers(client: TestClient) -> dict[str, str]:
    login = client.post(
        "/api/v1/auth/login",
        json={"username": "admin.panel", "password": TEST_ADMIN_PASSWORD},
    )
    assert login.status_code == 200, login.text
    return {"Authorization": f"Bearer {login.json()['accessToken']}"}


def test_create_echoes_radius_and_view_keeps_camelcase(
    client: TestClient, seeded_admin: int
) -> None:
    response = client.post(
        SPOTS_URL, json={**VALID_CREATE, "toleranceRadiusM": 25.0}, headers=_admin_headers(client)
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["toleranceRadiusM"] == 25.0
    detail = client.get(f"{SPOTS_URL}/{body['id']}", headers=_admin_headers(client)).json()
    assert detail["toleranceRadiusM"] == 25.0


def test_create_without_radius_stores_null_global_fallback(
    client: TestClient, seeded_admin: int
) -> None:
    body = client.post(SPOTS_URL, json=VALID_CREATE, headers=_admin_headers(client)).json()
    assert body["toleranceRadiusM"] is None  # None ⇒ 100 m global default (R2)


def test_patch_absent_radius_is_unchanged_explicit_null_resets(
    client: TestClient, seeded_admin: int
) -> None:
    headers = _admin_headers(client)
    created = client.post(
        SPOTS_URL, json={**VALID_CREATE, "toleranceRadiusM": 25.0}, headers=headers
    ).json()

    # Absent in patch = untouched (unchanged semantics of FR-017).
    patched = client.patch(
        f"{SPOTS_URL}/{created['id']}", json={"name": "Mirante Renomeado"}, headers=headers
    ).json()
    assert patched["toleranceRadiusM"] == 25.0

    # Explicit null = reset to global default.
    reset = client.patch(
        f"{SPOTS_URL}/{created['id']}", json={"toleranceRadiusM": None}, headers=headers
    ).json()
    assert reset["toleranceRadiusM"] is None


def test_non_positive_radius_rejected_422_unified_error(
    client: TestClient, seeded_admin: int
) -> None:
    headers = _admin_headers(client)
    for bad in (0, -10.0, 0.0):
        response = client.post(
            SPOTS_URL, json={**VALID_CREATE, "toleranceRadiusM": bad}, headers=headers
        )
        assert response.status_code == 422, response.text
        body = response.json()
        assert set(body) == {"errorCode", "message", "details"}  # unified ApiError (spec 005)
