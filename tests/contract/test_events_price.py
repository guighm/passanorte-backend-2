"""Contract: exact-money guarantee of the events module (feature 008 US3 — SC-005).

One submitted amount round-trips identically through EVERY read path —
create response, edit response, both listing shapes and the public
tourist-spot detail embedding (RF39 dependency). ``0`` stays a free event
everywhere. Storage never touches a float (integer cents — research R1).
"""

from decimal import Decimal

from fastapi.testclient import TestClient

from tests.contract.test_events import (
    EVENTS_URL,
    SPOTS_URL,
    _admin_headers,
    _create_spot,
)

ROUND_TRIP_PRICE = 15.50
EDGE_PRICES = (0, 0.01, 123456.78)


def _create_event_at_spot(client: TestClient, spot_id: int, price: float) -> dict:  # noqa: ANN201
    response = client.post(
        EVENTS_URL,
        json={
            "spotId": spot_id,
            "occurrenceDate": "2026-12-08",
            "description": "Festival de luzes no mirante.",
            "ticketPrice": price,
        },
        headers=_admin_headers(client),
    )
    assert response.status_code == 201, response.text
    return response.json()


def _listing_bodies(client: TestClient, spot_id: int) -> list[dict]:  # noqa: ANN201
    headers = _admin_headers(client)
    by_spot = client.get(EVENTS_URL, params={"spotId": spot_id}, headers=headers).json()["items"]
    by_range = client.get(
        EVENTS_URL,
        params={"startDate": "2026-12-01", "endDate": "2026-12-31", "spotId": spot_id},
        headers=headers,
    ).json()["items"]
    return [by_spot[0], by_range[0]]


def test_price_round_trips_identically_through_every_read_path(
    client: TestClient, seeded_admin: int
) -> None:
    spot = _create_spot(client)
    created = _create_event_at_spot(client, spot["id"], ROUND_TRIP_PRICE)
    headers = _admin_headers(client)

    # Edit response.
    edited = client.patch(
        f"{EVENTS_URL}/{created['id']}",
        json={"ticketPrice": ROUND_TRIP_PRICE},
        headers=headers,
    )
    assert edited.status_code == 200
    assert edited.json()["ticketPrice"] == ROUND_TRIP_PRICE

    # Both listing shapes.
    for item in _listing_bodies(client, spot["id"]):
        assert item["ticketPrice"] == ROUND_TRIP_PRICE

    # Public tourist-spot detail embedding (anonymous, RF27).
    embedded = client.get(f"{SPOTS_URL}/{spot['id']}").json()["events"]
    assert embedded[0]["ticketPrice"] == ROUND_TRIP_PRICE

    # Decimal-precision sanity: the wire value is a two-decimal float.
    assert Decimal(str(created["ticketPrice"])) == Decimal("15.50")


def test_zero_price_stays_free_everywhere(client: TestClient, seeded_admin: int) -> None:
    spot = _create_spot(client)
    created = _create_event_at_spot(client, spot["id"], 0)
    headers = _admin_headers(client)
    listing_item = client.get(EVENTS_URL, params={"spotId": spot["id"]}, headers=headers).json()[
        "items"
    ][0]
    embedded = client.get(f"{SPOTS_URL}/{spot['id']}").json()["events"][0]
    for body in (created, listing_item, embedded):
        assert body["ticketPrice"] == 0


def test_edge_monetary_values_round_trip(client: TestClient, seeded_admin: int) -> None:
    for price in EDGE_PRICES:
        spot = _create_spot(client, name=f"Ponto {price}")
        event = _create_event_at_spot(client, spot["id"], price)
        assert event["ticketPrice"] == price
        assert Decimal(str(event["ticketPrice"])) == Decimal(str(price))


def test_magnitude_cap_and_sub_cents_refused_at_border(
    client: TestClient, seeded_admin: int
) -> None:
    """The 12-digit contract cap (≤ 9999999999.99 / 999999999999 cents) and
    third-decimal inputs are rejected before anything persists."""
    spot = _create_spot(client)
    headers = _admin_headers(client)
    for invalid_price in (10000000000.00, 15.505, "0.001"):
        response = client.post(
            EVENTS_URL,
            json={
                "spotId": spot["id"],
                "occurrenceDate": "2026-12-08",
                "description": "x",
                "ticketPrice": invalid_price,
            },
            headers=headers,
        )
        assert response.status_code == 422, (invalid_price, response.text)
        assert response.json()["errorCode"] == "validation_error"
    assert client.get(EVENTS_URL, headers=headers).json()["items"] == []


def test_negative_price_never_persists(client: TestClient, seeded_admin: int) -> None:
    spot = _create_spot(client)
    headers = _admin_headers(client)
    response = client.post(
        EVENTS_URL,
        json={
            "spotId": spot["id"],
            "occurrenceDate": "2026-12-08",
            "description": "x",
            "ticketPrice": -5,
        },
        headers=headers,
    )
    assert response.status_code == 422
    assert client.get(EVENTS_URL, headers=headers).json()["items"] == []
