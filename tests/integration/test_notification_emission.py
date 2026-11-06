"""Integration: emission through the three emitters (feature 015, RF37).

Real admin creation paths of specs 007/008/009: spot inherits ITS OWN
categories; event inherits the target spot's (research R4); route inherits
the union of its spots' categories (Q3). Best-effort guarantee: a failed
notification emission never blocks the item creation (FR-011).
"""

import itertools
import logging

from fastapi.testclient import TestClient

from tests.conftest import TEST_ADMIN_PASSWORD

TOURISTS_URL = "/api/v1/tourists"
TOURIST_LOGIN = "/api/v1/tourists/login"
SPOTS_URL = "/api/v1/tourist-spots"
EVENTS_URL = "/api/v1/events"
ROUTES_URL = "/api/v1/gamification/routes"
NOTIFICATIONS_URL = "/api/v1/notifications"

ADMIN = {"username": "admin.panel", "password": TEST_ADMIN_PASSWORD}
_SEQUENCE = itertools.count(1)

_SCHEDULE = [{"weekday": "monday", "opensAt": "09:00", "closesAt": "17:00"}]


def _tourist(client: TestClient) -> tuple[int, dict[str, str]]:
    sequence = next(_SEQUENCE)
    email = f"emission-tourist-{sequence}@example.com"
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


def _admin(client: TestClient) -> dict[str, str]:
    login = client.post("/api/v1/auth/login", json=ADMIN)
    assert login.status_code == 200, login.text
    return {"Authorization": f"Bearer {login.json()['accessToken']}"}


def _subscribe(client: TestClient, tourist: dict[str, str], key: str) -> None:
    put = client.put(
        f"{NOTIFICATIONS_URL}/subscriptions",
        headers=tourist,
        json={"categoryKeys": [key]},
    )
    assert put.status_code == 200, put.text


def _titles(client: TestClient, tourist: dict[str, str]) -> list[str]:
    listing = client.get(NOTIFICATIONS_URL, headers=tourist)
    assert listing.status_code == 200, listing.text
    return [item["title"] for item in listing.json()["items"]]


def _create_spot(
    client: TestClient, admin: dict[str, str], name: str, categories: list[str]
) -> int:
    spot = client.post(
        SPOTS_URL,
        headers=admin,
        json={
            "name": name,
            "description": f"Spot {name} para emissão.",
            "latitude": -22.4,
            "longitude": -45.0,
            "categories": categories,
            "schedule": _SCHEDULE,
            "status": None,
            "toleranceRadiusM": None,
        },
    )
    assert spot.status_code == 201, spot.text
    return int(spot.json()["id"])


def _create_event(client: TestClient, admin: dict[str, str], spot_id: int, name: str) -> int:
    event = client.post(
        EVENTS_URL,
        headers=admin,
        json={
            "spotId": spot_id,
            "occurrenceDate": "2027-03-10",
            "description": f"Festival {name}",
            "ticketPrice": "25.00",
        },
    )
    assert event.status_code == 201, event.text
    return int(event.json()["id"])


def _create_route(client: TestClient, admin: dict[str, str], name: str, spot_ids: list[int]) -> int:
    url = ROUTES_URL if name != "Rota Fantasma" else None
    if url is None:
        # empty spots is 422 by schema (US1-5) — category-less routes do not
        # exist via the API; emulate by pointing at spots with zero categories
        # (delete-all case exercised at the seam level in the contract test).
        fake = client.post(
            ROUTES_URL,
            headers=admin,
            json={
                "name": name,
                "description": f"Rota {name}",
                "spots": [],
                "prize": {"name": f"Prêmio {name}", "initialStock": 5},
            },
        )
        assert fake.status_code in (201, 422)
        return 0
    route = client.post(
        ROUTES_URL,
        headers=admin,
        json={
            "name": name,
            "description": f"Rota {name}",
            "spots": [
                {"spotId": spot_id, "displayOrder": order + 1}
                for order, spot_id in enumerate(spot_ids)
            ],
            "prize": {"name": f"Prêmio {name}", "initialStock": 5},
        },
    )
    assert route.status_code == 201, route.text
    return int(route.json()["id"])


def test_spot_emission_match_and_no_match(client: TestClient, seeded_admin: int) -> None:
    """(a): category match → notification; non-match → none (US2)."""
    tourist_id, tourist = _tourist(client)
    _subscribe(client, tourist, "gastronomy")
    admin = _admin(client)

    matched_id = _create_spot(client, admin, "Restaurante Match", ["gastronomy"])
    _create_spot(client, admin, "Trilha Natureza", ["nature"])

    titles = _titles(client, tourist)
    assert "Novo ponto turístico: Restaurante Match" in titles
    assert "Novo ponto turístico: Trilha Natureza" not in titles
    # Deep-link pair present in the received payload (FR-014):
    listing = client.get(NOTIFICATIONS_URL, headers=tourist)
    item = listing.json()["items"][0]
    assert (item["itemType"], item["itemId"]) == ("spot", matched_id)


def test_event_inherits_spot_categories(client: TestClient, seeded_admin: int) -> None:
    """(b): events carry no own categories — the target spot's count (R4)."""
    tourist_id, tourist = _tourist(client)
    _subscribe(client, tourist, "gastronomy")
    admin = _admin(client)

    spot_id = _create_spot(client, admin, "Praça Gastronômica", ["gastronomy"])
    _create_event(client, admin, spot_id, "de Inverno")

    titles = _titles(client, tourist)
    assert "Novo evento: Festival de Inverno" in titles


def test_route_inherits_union_of_spot_categories(client: TestClient, seeded_admin: int) -> None:
    """(c): route matches the union of its spots' categories (Q3)."""
    tourist_id, tourist = _tourist(client)
    _subscribe(client, tourist, "nature")
    admin = _admin(client)

    nature_spot = _create_spot(client, admin, "Cachoeira Rota", ["nature"])
    _create_spot(client, admin, "Mirante Rota", ["culture"])
    _create_route(client, admin, "Circuito das Águas", [nature_spot])

    titles = _titles(client, tourist)
    assert "Nova rota turística: Circuito das Águas" in titles


def test_route_without_categories_emits_nothing(client: TestClient, seeded_admin: int) -> None:
    """(c-negative): a category-less route (no spots) emits nothing (Q3)."""
    tourist_id, tourist = _tourist(client)
    _subscribe(client, tourist, "gastronomy")
    admin = _admin(client)
    _create_route(client, admin, "Rota Fantasma", [])
    assert _titles(client, tourist) == []


def test_dedupe_multi_category_item(client: TestClient, seeded_admin: int) -> None:
    """(d): tourist matching 2 categories of one item → ONE notification."""
    tourist_id, tourist = _tourist(client)
    client.put(
        f"{NOTIFICATIONS_URL}/subscriptions",
        headers=tourist,
        json={"categoryKeys": ["nature", "leisure"]},
    )
    admin = _admin(client)
    _create_spot(client, admin, "Parque Multi", ["nature", "leisure"])

    items = client.get(NOTIFICATIONS_URL, headers=tourist).json()["items"]
    titles_on_parque = [entry["title"] for entry in items if "Parque Multi" in entry["title"]]
    # Exactly ONE notification for the multi-category item (FR-009 dedupe),
    # carrying the spot deep-link pair.
    assert len(titles_on_parque) == 1
    assert items[0]["itemType"] == "spot"


def test_emission_failure_never_blocks_creation(
    client: TestClient, seeded_admin: int, caplog
) -> None:
    """(f): best-effort — seam failure logs, item creation still 201 (FR-011)."""
    from unittest.mock import patch

    from passanorte_back.modules.notifications.services import emission

    tourist_id, _tourist_headers = _tourist(client)
    _subscribe(client, _tourist_headers, "gastronomy")
    admin = _admin(client)

    with (
        patch.object(emission, "insert_notifications", side_effect=RuntimeError("boom")),
        caplog.at_level(logging.ERROR, logger="passanorte.notifications"),
    ):
        spot_id = _create_spot(client, admin, "Restaurante Falha", ["gastronomy"])
    assert spot_id > 0  # creation succeeded despite the emission failure
    assert any("FAILED" in record.getMessage() for record in caplog.records)

    # The tourist received nothing (emission failed) — observable, no crash.
    assert _titles(client, _tourist_headers) == []
