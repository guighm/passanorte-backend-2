"""Integration: tourist spot full lifecycle (feature 007 US1 — SC-001).

Create → read state via the edit response → edit (name + status) →
remove → spot invisible for follow-up edit/remove (404). One admin
session, one flow — the "2 minutes end-to-end" completion criterion.
"""

from fastapi.testclient import TestClient

from tests.conftest import TEST_ADMIN_PASSWORD

SPOTS_URL = "/api/v1/tourist-spots"

CREATE = {
    "name": "Cachoeira do Vale",
    "description": "Cachoeira com piscina natural e área de piquenique.",
    "latitude": -22.7051,
    "longitude": -45.0703,
    "categories": ["nature", "leisure"],
    "schedule": [
        {"weekday": "monday", "opensAt": "09:00", "closesAt": "12:00"},
        {"weekday": "monday", "opensAt": "13:00", "closesAt": "17:00"},
        {"weekday": "wednesday", "opensAt": "09:00", "closesAt": "17:00"},
    ],
}


def _admin_headers(client: TestClient) -> dict[str, str]:
    login = client.post(
        "/api/v1/auth/login",
        json={"username": "admin.panel", "password": TEST_ADMIN_PASSWORD},
    )
    return {"Authorization": f"Bearer {login.json()['accessToken']}"}


def test_full_lifecycle_create_edit_remove(client: TestClient, seeded_admin: int) -> None:
    headers = _admin_headers(client)

    created = client.post(SPOTS_URL, json=CREATE, headers=headers)
    assert created.status_code == 201, created.text
    spot = created.json()
    assert spot["status"] == "open"  # default (FR-008)
    assert spot["categories"] == CREATE["categories"]
    assert len(spot["schedule"]) == 3

    # Partial edit: name + status change; the rest persists.
    edited = client.patch(
        f"{SPOTS_URL}/{spot['id']}",
        json={"name": "Cachoeira do Vale (temporariamente fechada)", "status": "temporarilyClosed"},
        headers=headers,
    )
    assert edited.status_code == 200
    body = edited.json()
    assert body["name"] == "Cachoeira do Vale (temporariamente fechada)"
    assert body["status"] == "temporarilyClosed"
    assert body["latitude"] == spot["latitude"]
    assert body["categories"] == spot["categories"]
    assert body["schedule"] == spot["schedule"]

    # Removal: 204 and the spot leaves every target operation (404 after).
    removed = client.delete(f"{SPOTS_URL}/{spot['id']}", headers=headers)
    assert removed.status_code == 204
    assert (
        client.patch(f"{SPOTS_URL}/{spot['id']}", json={"name": "X"}, headers=headers).status_code
        == 404
    )
    assert client.delete(f"{SPOTS_URL}/{spot['id']}", headers=headers).status_code == 404
