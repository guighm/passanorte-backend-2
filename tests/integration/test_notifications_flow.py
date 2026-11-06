"""Integration: notification channel lifecycle (feature 015, RF37).

Acceptance flow (spec criterion): subscribe with 'gastronomia' → receive
notifications for matched items → mark read → unsubscribe stops FUTURE
emissions while keeping the history.
"""

import itertools

from fastapi.testclient import TestClient

from tests.conftest import TEST_ADMIN_PASSWORD

BASE_URL = "/api/v1/notifications"
TOURISTS_URL = "/api/v1/tourists"
TOURIST_LOGIN = "/api/v1/tourists/login"
SPOTS_URL = "/api/v1/tourist-spots"

ADMIN = {"username": "admin.panel", "password": TEST_ADMIN_PASSWORD}
_SEQUENCE = itertools.count(1)


def _tourist(client: TestClient) -> tuple[int, dict[str, str]]:
    sequence = next(_SEQUENCE)
    email = f"flow-notif-{sequence}@example.com"
    payload = {
        "firstName": "Ana",
        "lastName": "Silva",
        "countryOfOrigin": "Brasil",
        "cpf": None,
        "passportNumber": f"AB{sequence:06d}",
        "phone": "+5511999999999",
        "email": email,
        "password": "long-enough-password-1",
    }
    register = client.post(TOURISTS_URL, json=payload)
    assert register.status_code == 201, register.text
    tourist_id = int(register.json()["id"])
    login = client.post(TOURIST_LOGIN, json={"email": email, "password": payload["password"]})
    assert login.status_code == 200, login.text
    return tourist_id, {"Authorization": f"Bearer {login.json()['accessToken']}"}


def _admin_headers(client: TestClient) -> dict[str, str]:
    login = client.post("/api/v1/auth/login", json=ADMIN)
    assert login.status_code == 200, login.text
    return {"Authorization": f"Bearer {login.json()['accessToken']}"}


def test_subscribe_and_cancel(client: TestClient, seeded_admin: int) -> None:
    """US1: subscribe → cancel one → others remain (profile untouched)."""
    tourist_id, tourist = _tourist(client)

    put = client.put(
        f"{BASE_URL}/subscriptions",
        headers=tourist,
        json={"categoryKeys": ["gastronomy", "nature"]},
    )
    assert put.status_code == 200, put.text
    assert put.json() == {"categoryKeys": ["gastronomy", "nature"]}

    delete = client.delete(f"{BASE_URL}/subscriptions/nature", headers=tourist)
    assert delete.status_code == 200
    assert delete.json() == {"categoryKeys": ["gastronomy"]}

    again = client.put(
        f"{BASE_URL}/subscriptions",
        headers=tourist,
        json={"categoryKeys": ["gastronomy"]},
    )
    assert again.json() == {"categoryKeys": ["gastronomy"]}  # idempotent

    # Channel is independent of the profile interests (Q1/FR-007):
    _other, other = _tourist(client)
    assert (
        client.put(
            f"{TOURISTS_URL}/me/interests",
            headers=other,
            json={"interests": ["gastronomy", "nature"]},
        ).status_code
        == 200
    )
    assert client.get(f"{BASE_URL}/subscriptions", headers=other).json() == {"categoryKeys": []}


def test_delivery_and_unsubscribe_stop(
    client: TestClient, seeded_admin: int, seeded_employee: int, sessionfactory_for
) -> None:
    """Full RF37 loop: match emission → read marking → unsubscribe stop."""
    tourist_id, tourist = _tourist(client)
    admin = _admin_headers(client)

    assert (
        client.put(
            f"{BASE_URL}/subscriptions",
            headers=tourist,
            json={"categoryKeys": ["gastronomy"]},
        ).status_code
        == 200
    )

    matched = client.post(
        SPOTS_URL,
        headers=admin,
        json={
            "name": "Restaurante Notifi",
            "description": "Cozinha regional.",
            "latitude": -22.4,
            "longitude": -45.0,
            "categories": ["gastronomy"],
            "schedule": [{"weekday": "monday", "opensAt": "09:00", "closesAt": "17:00"}],
            "status": None,
            "toleranceRadiusM": None,
        },
    )
    assert matched.status_code == 201, matched.text

    listing = client.get(BASE_URL, headers=tourist)
    assert listing.json()["unreadCount"] >= 1
    item = listing.json()["items"][0]
    assert item["itemType"] == "spot"
    assert item["title"] == "Novo ponto turístico: Restaurante Notifi"

    notification_id = item["id"]
    read = client.post(f"{BASE_URL}/{notification_id}/read", headers=tourist)
    assert read.status_code == 200
    read_all = client.post(f"{BASE_URL}/read-all", headers=tourist)
    assert read_all.json() == {"unreadCount": 0}

    # Unsubscribe → FUTURE items do not notify; history remains (SC-004).
    cancel = client.delete(f"{BASE_URL}/subscriptions/gastronomy", headers=tourist)
    assert cancel.status_code == 200
    no_match = client.post(
        SPOTS_URL,
        headers=admin,
        json={
            "name": "Cachoeira Depois",
            "description": "Nova atração.",
            "latitude": -22.6,
            "longitude": -45.2,
            "categories": ["gastronomy"],
            "schedule": [{"weekday": "monday", "opensAt": "09:00", "closesAt": "17:00"}],
            "status": None,
            "toleranceRadiusM": None,
        },
    )
    assert no_match.status_code == 201
    after = client.get(
        BASE_URL, headers=tourist, params={"onlyUnread": "false"}
    )  # history view (read items included)
    titles = [entry["title"] for entry in after.json()["items"]]
    assert "Novo ponto turístico: Restaurante Notifi" in titles  # history kept
    assert "Novo ponto turístico: Cachoeira Depois" not in titles  # future stopped
