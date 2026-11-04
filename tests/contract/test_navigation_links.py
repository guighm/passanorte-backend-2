"""Contract: navigation links (feature 013 — contracts §2–§3, T015).

RF28 surface: ready-to-open map/Uber/99 links per spot; origin fallback is
self-documenting; the existing public detail gains additive uber/99 fields
while every spec 007 expectation survives; provider switch is config-only.
"""

import pytest
from fastapi.testclient import TestClient

from tests.conftest import TEST_ADMIN_PASSWORD


@pytest.fixture(autouse=True)
def _bootstrap_admin(seeded_admin: int) -> int:
    return seeded_admin


SPOTS_URL = "/api/v1/tourist-spots"
TOURIST_LOGIN = "/api/v1/tourists/login"

SPOT = (-22.4968, -45.0086)
ORIGIN = (-22.4901, -45.0001)

LINK_KEYS = {"origin", "mapLink", "uberLink", "ninetyNineLink"}

_REGISTER_COUNTER = [500]


def _admin_headers(client: TestClient) -> dict[str, str]:
    login = client.post(
        "/api/v1/auth/login",
        json={"username": "admin.panel", "password": TEST_ADMIN_PASSWORD},
    )
    assert login.status_code == 200, login.text
    return {"Authorization": f"Bearer {login.json()['accessToken']}"}


def _valid_cpf(core: str) -> str:
    digits = [int(char) for char in core]
    first = (
        sum(value * weight for value, weight in zip(digits, range(10, 1, -1), strict=False)) % 11
    )
    dv1 = 0 if first < 2 else 11 - first
    second = (
        sum(value * weight for value, weight in zip([*digits, dv1], range(11, 1, -1), strict=False))
        % 11
    )
    dv2 = 0 if second < 2 else 11 - second
    return f"{core}{dv1}{dv2}"


def _tourist_headers(client: TestClient) -> dict[str, str]:
    _REGISTER_COUNTER[0] += 1
    suffix = _REGISTER_COUNTER[0]
    raw = _valid_cpf(f"456789{suffix:03d}")
    register = client.post(
        "/api/v1/tourists",
        json={
            "firstName": "Nina",
            "lastName": "Navegante",
            "countryOfOrigin": "Brasil",
            "cpf": f"{raw[:3]}.{raw[3:6]}.{raw[6:]}",
            "passportNumber": None,
            "phone": f"+5511966{suffix:06d}",
            "email": f"navigation-{suffix}@example.com",
            "password": "long-enough-password-1",
        },
    )
    assert register.status_code == 201, register.text
    login = client.post(
        TOURIST_LOGIN,
        json={"email": f"navigation-{suffix}@example.com", "password": "long-enough-password-1"},
    )
    assert login.status_code == 200, login.text
    return {"Authorization": f"Bearer {login.json()['accessToken']}"}


def _spot(client: TestClient, name: str = "Mirante Links") -> int:
    response = client.post(
        SPOTS_URL,
        json={
            "name": name,
            "description": f"contract spot {name}",
            "latitude": SPOT[0],
            "longitude": SPOT[1],
            "categories": ["nature"],
            "schedule": [{"weekday": "sunday", "opensAt": "08:00", "closesAt": "16:00"}],
        },
        headers=_admin_headers(client),
    )
    assert response.status_code == 201, response.text
    return response.json()["id"]


def test_links_with_position_use_it_as_pickup(
    client: TestClient,
    sessionfactory_for,
    seeded_admin: int,  # noqa: ARG001
) -> None:
    spot_id = _spot(client)
    response = client.get(
        f"{SPOTS_URL}/{spot_id}/navigation-links",
        params={"latitude": ORIGIN[0], "longitude": ORIGIN[1]},
        headers=_tourist_headers(client),
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert set(body) == LINK_KEYS
    assert body["origin"] == {"latitude": ORIGIN[0], "longitude": ORIGIN[1]}
    assert f"destination={SPOT[0]},{SPOT[1]}" in body["mapLink"]
    assert (
        f"pickup[latitude]={ORIGIN[0]}&pickup[longitude]={ORIGIN[1]}"
        f"&dropoff[latitude]={SPOT[0]}&dropoff[longitude]={SPOT[1]}" in body["uberLink"]
    )
    assert (
        f"pickupLatitude={ORIGIN[0]}&pickupLongitude={ORIGIN[1]}"
        f"&dropLatitude={SPOT[0]}&dropLongitude={SPOT[1]}" in body["ninetyNineLink"]
    )


def test_links_without_position_fallback_origin_is_self_documented(
    client: TestClient, sessionfactory_for
) -> None:
    """FR-010/US2-AS3: origin echoes back as the spot itself, no failure."""
    spot_id = _spot(client, "Praça Sem Origem")
    response = client.get(
        f"{SPOTS_URL}/{spot_id}/navigation-links", headers=_tourist_headers(client)
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["origin"] == {"latitude": SPOT[0], "longitude": SPOT[1]}


def test_unknown_spot_is_unified_404(client: TestClient, sessionfactory_for) -> None:
    response = client.get(f"{SPOTS_URL}/999999/navigation-links", headers=_tourist_headers(client))
    assert response.status_code == 404
    assert response.json()["errorCode"]


def test_invalid_coordinates_are_422(client: TestClient, sessionfactory_for) -> None:
    spot_id = _spot(client, "Praça Coordenada Ruim")
    response = client.get(
        f"{SPOTS_URL}/{spot_id}/navigation-links",
        params={"latitude": 150.0, "longitude": -45.0},
        headers=_tourist_headers(client),
    )
    assert response.status_code == 422
    assert response.json()["errorCode"]


def test_anonymous_401_and_admin_403_links(client: TestClient, sessionfactory_for) -> None:
    spot_id = _spot(client, "Praça Protegida")
    anonymous = client.get(f"{SPOTS_URL}/{spot_id}/navigation-links")
    assert anonymous.status_code == 401
    admin = client.get(f"{SPOTS_URL}/{spot_id}/navigation-links", headers=_admin_headers(client))
    assert admin.status_code == 403


def test_detail_gains_additive_uber_and_99_links_and_keeps_007(
    client: TestClient, sessionfactory_for
) -> None:
    """FR-008: additive fields; every previously-contracted field intact."""
    spot_id = _spot(client, "Mirante Detalhe")
    response = client.get(f"{SPOTS_URL}/{spot_id}")
    assert response.status_code == 200, response.text
    body = response.json()
    # Existing 007 public-detail expectations survive unchanged:
    assert body["id"] == spot_id
    assert body["name"] == "Mirante Detalhe"
    assert body["status"] == "open"
    assert body["categories"] == [{"key": "nature", "label": "Natureza"}]
    assert body["mapLink"].startswith("https://www.google.com/maps/search")
    assert body["events"] == []
    # New additive fields (origin = the spot itself — no request position):
    assert f"pickup[latitude]={SPOT[0]}" in body["uberLink"]
    assert f"dropLatitude={SPOT[0]}" in body["ninetyNineLink"]


def test_provider_switch_changes_only_map_target(
    client: TestClient, sessionfactory_for, monkeypatch: pytest.MonkeyPatch
) -> None:
    """SC-007/FR-011: configuration-only provider swap; shapes identical."""
    spot_id = _spot(client, "Mirante Provedor")
    headers = _tourist_headers(client)
    with_position = {
        "latitude": ORIGIN[0],
        "longitude": ORIGIN[1],
    }
    google = client.get(
        f"{SPOTS_URL}/{spot_id}/navigation-links", params=with_position, headers=headers
    ).json()
    monkeypatch.setenv("DISCOVERY_MAP_PROVIDER", "osm")
    from passanorte_back.core.config import get_settings

    get_settings.cache_clear()
    try:
        osm = client.get(
            f"{SPOTS_URL}/{spot_id}/navigation-links", params=with_position, headers=headers
        ).json()
    finally:
        get_settings.cache_clear()
    assert set(osm) == set(google)
    assert osm["mapLink"].startswith(
        "https://www.openstreetmap.org/directions?engine=fossgis_osrm_car&route="
    )
    assert osm["origin"] == google["origin"]
    assert osm["uberLink"] == google["uberLink"]
    assert osm["ninetyNineLink"] == google["ninetyNineLink"]
