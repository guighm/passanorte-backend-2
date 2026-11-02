"""Integration: events full lifecycle (feature 008 US1+US2 — SC-001/SC-003).

One admin session, one flow: login → create spot → create event → list by
spot → list by date range (incl. combined filter) → edit (spot change +
fields) → public detail embedding → delete event. A second block proves
the cascade (spot removal wipes its events) and the audit trail (exactly
one record per administrative write — RNF19).
"""

from fastapi.testclient import TestClient

from tests.conftest import TEST_ADMIN_PASSWORD

EVENTS_URL = "/api/v1/events"
SPOTS_URL = "/api/v1/tourist-spots"

SPOT_CREATE = {
    "name": "Mirante Pedra do Bauzinho",
    "description": "Mirante com vista para o vale e trilha curta.",
    "latitude": -22.7271,
    "longitude": -45.0366,
    "categories": ["nature"],
    "schedule": [{"weekday": "saturday", "opensAt": "08:30", "closesAt": "17:00"}],
}

EVENT_CREATE = {
    "occurrenceDate": "2026-12-08",
    "description": "Festival de luzes no mirante com apresentação local.",
    "ticketPrice": 15.50,
}


def _admin_headers(client: TestClient) -> dict[str, str]:
    login = client.post(
        "/api/v1/auth/login",
        json={"username": "admin.panel", "password": TEST_ADMIN_PASSWORD},
    )
    return {"Authorization": f"Bearer {login.json()['accessToken']}"}


def _create_spot(client: TestClient, headers: dict[str, str], **overrides) -> dict:  # noqa: ANN003
    response = client.post(SPOTS_URL, json={**SPOT_CREATE, **overrides}, headers=headers)
    assert response.status_code == 201, response.text
    return response.json()


def _create_event(
    client: TestClient,
    headers: dict[str, str],
    spot_id: int,
    **overrides,  # noqa: ANN003
) -> dict:
    response = client.post(
        EVENTS_URL,
        json={"spotId": spot_id, **EVENT_CREATE, **overrides},
        headers=headers,
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_event_full_lifecycle_and_public_embedding(
    client: TestClient, seeded_admin: int, audit_logs
) -> None:
    headers = _admin_headers(client)

    spot = _create_spot(client, headers)
    event = _create_event(client, headers, spot["id"])
    assert event["ticketPrice"] == 15.50

    # List by spot (FR-007).
    by_spot = client.get(EVENTS_URL, params={"spotId": spot["id"]}, headers=headers)
    assert by_spot.status_code == 200
    assert [item["id"] for item in by_spot.json()["items"]] == [event["id"]]

    # List by date range, inclusive bounds + combined filter (FR-008).
    by_range = client.get(
        EVENTS_URL,
        params={"startDate": "2026-12-01", "endDate": "2026-12-31"},
        headers=headers,
    )
    assert [item["id"] for item in by_range.json()["items"]] == [event["id"]]
    combined = client.get(
        EVENTS_URL,
        params={"spotId": spot["id"], "startDate": "2026-12-01", "endDate": "2026-12-08"},
        headers=headers,
    )
    assert [item["id"] for item in combined.json()["items"]] == [event["id"]]

    # Edit: date + price change, then a spot change (re-validated target).
    edited = client.patch(
        f"{EVENTS_URL}/{event['id']}",
        json={"occurrenceDate": "2026-12-15", "ticketPrice": 0},
        headers=headers,
    )
    assert edited.status_code == 200
    assert edited.json()["occurrenceDate"] == "2026-12-15"
    assert edited.json()["ticketPrice"] == 0  # zero = free stays
    other = _create_spot(client, headers, name="Casa de Cultura")
    moved = client.patch(
        f"{EVENTS_URL}/{event['id']}", json={"spotId": other["id"]}, headers=headers
    )
    assert moved.status_code == 200
    assert moved.json()["spotId"] == other["id"]

    # The Public detail embeds the event without a second request (RF27).
    public_detail = client.get(f"{SPOTS_URL}/{other['id']}")
    assert public_detail.status_code == 200
    embedded = public_detail.json()["events"]
    assert [item["id"] for item in embedded] == [event["id"]]
    assert embedded[0]["ticketPrice"] == 0
    assert embedded[0]["occurrenceDate"] == "2026-12-15"

    # Delete the event; every read path empties out.
    assert client.delete(f"{EVENTS_URL}/{event['id']}", headers=headers).status_code == 204
    assert client.get(EVENTS_URL, headers=headers).json()["items"] == []
    assert client.get(f"{SPOTS_URL}/{other['id']}").json()["events"] == []

    # Exactly one audit record per administrative write (SC-004).
    event_actions = [
        record.getMessage()
        for record in audit_logs.records
        if '"action": "event.' in record.getMessage()
    ]
    assert len(event_actions) == 4  # create, update, update(move), delete
    actions = [record.split('"action": "')[1].split('"')[0] for record in event_actions]
    assert actions.count("event.create") == 1
    assert actions.count("event.update") == 2
    assert actions.count("event.delete") == 1


def test_spot_removal_cascades_its_events(client: TestClient, seeded_admin: int) -> None:
    headers = _admin_headers(client)

    spot = _create_spot(client, headers, name="Parque Cerrado")
    event = _create_event(client, headers, spot["id"], ticketPrice=25.00)

    # Before removal: the event exists in the spot's listing and publicly.
    before = client.get(EVENTS_URL, params={"spotId": spot["id"]}, headers=headers)
    assert [item["id"] for item in before.json()["items"]] == [event["id"]]

    # Remove the SPOT (soft delete) — its events cease to exist (cascade).
    assert client.delete(f"{SPOTS_URL}/{spot['id']}", headers=headers).status_code == 204

    after = client.get(EVENTS_URL, params={"spotId": spot["id"]}, headers=headers)
    assert after.status_code == 404  # the spot filter target no longer exists
    everything = client.get(EVENTS_URL, headers=headers)
    assert all(item["id"] != event["id"] for item in everything.json()["items"])

    # The removed spot itself is publicly gone (007 soft-delete semantics).
    assert client.get(f"{SPOTS_URL}/{spot['id']}").status_code == 404
