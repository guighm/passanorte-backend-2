"""Contract: discovery feed (feature 013 — contracts/tourist-spots-discovery.md §1).

Ranked, paginated, tourist-exclusive feed (RF26). Ordering cases per the
spec acceptance criteria: with-interests vs. without, no position, future
events vs. none; visibility rules (temporarily closed in, permanently
closed out); strict camelCase border and unified ApiError failures.
"""

from datetime import UTC, date, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from tests.conftest import TEST_ADMIN_PASSWORD


@pytest.fixture(autouse=True)
def _bootstrap_admin(seeded_admin: int) -> int:
    """Admin panel credentials exist for every test in this module."""
    return seeded_admin


DISCOVER_URL = "/api/v1/tourist-spots/discover"
SPOTS_URL = "/api/v1/tourist-spots"
TOURIST_LOGIN = "/api/v1/tourists/login"
INTERESTS_URL = "/api/v1/tourists/me/interests"

ITEM_KEYS = {
    "id",
    "name",
    "description",
    "latitude",
    "longitude",
    "status",
    "categories",
    "relevanceScore",
    "upcomingEventDate",
    "mapLink",
}
RESPONSE_KEYS = {"items", "page", "pageSize", "totalItems", "totalPages"}

CITY_CENTER = (-22.4901, -45.0001)


def _admin_headers(client: TestClient) -> dict[str, str]:
    login = client.post(
        "/api/v1/auth/login",
        json={"username": "admin.panel", "password": TEST_ADMIN_PASSWORD},
    )
    assert login.status_code == 200, login.text
    return {"Authorization": f"Bearer {login.json()['accessToken']}"}


_TOURIST_COUNTER = [100]


def _valid_cpf(core: str) -> str:
    """Real CPF check digits — the tourists schema validates checksums."""
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


def _tourist_headers(client: TestClient, interests: list[str] | None = None) -> dict[str, str]:
    """Fresh tourist; optionally selects interest categories (spec 003)."""
    _TOURIST_COUNTER[0] += 1
    suffix = _TOURIST_COUNTER[0]
    raw = _valid_cpf(f"987654{suffix:03d}")
    cpf = f"{raw[:3]}.{raw[3:6]}.{raw[6:]}"
    register = client.post(
        "/api/v1/tourists",
        json={
            "firstName": "Bia",
            "lastName": "Descoberta",
            "countryOfOrigin": "Brasil",
            "cpf": cpf,
            "passportNumber": None,
            "phone": f"+5511977{suffix:06d}",
            "email": f"discovery-{suffix}@example.com",
            "password": "long-enough-password-1",
        },
    )
    assert register.status_code == 201, register.text
    login = client.post(
        TOURIST_LOGIN,
        json={"email": f"discovery-{suffix}@example.com", "password": "long-enough-password-1"},
    )
    assert login.status_code == 200, login.text
    headers = {"Authorization": f"Bearer {login.json()['accessToken']}"}
    if interests is not None:
        updated = client.put(INTERESTS_URL, json={"interests": interests}, headers=headers)
        assert updated.status_code == 200, updated.text
    return headers


def _create_spot(
    client: TestClient,
    name: str,
    latitude: float,
    longitude: float,
    categories: list[str],
    status: str = "open",
) -> int:
    payload = {
        "name": name,
        "description": f"desc of {name}",
        "latitude": latitude,
        "longitude": longitude,
        "categories": categories,
        "schedule": [{"weekday": "monday", "opensAt": "09:00", "closesAt": "17:00"}],
    }
    if status != "open":
        payload["status"] = status
    response = client.post(SPOTS_URL, json=payload, headers=_admin_headers(client))
    assert response.status_code == 201, response.text
    return response.json()["id"]


def _seed_event(session_fac, spot_id: int, days_offset: int) -> None:
    from passanorte_back.modules.events.repositories.events import Event
    from tests.conftest import TEST_DATABASE_URL  # noqa: F401

    with session_fac() as session:
        session.add(
            Event(
                spot_id=spot_id,
                occurrence_date=date.today() + timedelta(days=days_offset),
                description="synthetic upcoming event",
                ticket_price_cents=0,
                created_at=datetime.now(UTC),
                updated_at=datetime.now(UTC),
            )
        )
        session.commit()


def _discover(client: TestClient, headers: dict[str, str], **params: object) -> dict:
    response = client.get(DISCOVER_URL, params=params, headers=headers)
    assert response.status_code == 200, response.text
    return response.json()


def test_contract_shape_and_relevance_score_present(client: TestClient, sessionfactory_for) -> None:
    spot = _create_spot(client, "Museu Central", -22.501, -45.001, ["culture"])
    body = _discover(client, _tourist_headers(client))
    assert set(body) == RESPONSE_KEYS
    assert body["page"] == 1 and body["totalItems"] >= 1
    item = next(entry for entry in body["items"] if entry["id"] == spot)
    assert set(item) == ITEM_KEYS
    assert isinstance(item["relevanceScore"], float)
    assert item["mapLink"].startswith("https://www.google.com/maps")
    assert item["upcomingEventDate"] is None


def test_interest_match_ranks_ahead(client: TestClient, sessionfactory_for) -> None:
    """Tourist with interests vs. without — SC-001/US1-AS1."""
    gastronomy = _create_spot(client, "Restaurante da Serra", *CITY_CENTER, ["gastronomy"])
    nature = _create_spot(client, "Mirante Verde", -22.60, -45.10, ["nature"])

    with_interests = _tourist_headers(client, interests=["gastronomy"])
    ordered = _discover(client, with_interests, latitude=CITY_CENTER[0], longitude=CITY_CENTER[1])
    assert [item["id"] for item in ordered["items"]][:2] == [gastronomy, nature]
    assert ordered["items"][0]["relevanceScore"] > ordered["items"][1]["relevanceScore"]

    without_interests = _tourist_headers(client, interests=[])
    neutral = _discover(
        client, without_interests, latitude=CITY_CENTER[0], longitude=CITY_CENTER[1]
    )
    neutral_ids = [item["id"] for item in neutral["items"]]
    assert set(neutral_ids) == {gastronomy, nature}


def test_without_interests_and_position_order_is_deterministic(
    client: TestClient, sessionfactory_for
) -> None:
    """No interests, no position — neutral factors, stable order (FR-005/006)."""
    _create_spot(client, "Cachoeira Alta", -22.61, -45.11, ["nature"])
    _create_spot(client, "Casa da Cultura", -22.51, -45.01, ["culture"])
    headers = _tourist_headers(client)  # no interests selected at all
    first = _discover(client, headers)
    second = _discover(client, headers)
    assert [item["id"] for item in first["items"]] == [item["id"] for item in second["items"]]


def test_upcoming_event_boosts_but_past_does_not(client: TestClient, sessionfactory_for) -> None:
    """Identical spots; one with imminent event ranks first (US1-AS4/SC-003)."""
    plain = _create_spot(client, "Praça Comum", -22.52, -45.02, ["leisure"])
    festive = _create_spot(client, "Praça Festiva", -22.53, -45.03, ["leisure"])
    _seed_event(sessionfactory_for, festive, 7)
    _seed_event(sessionfactory_for, plain, -3)  # past event — no boost

    body = _discover(client, _tourist_headers(client))
    ids = [item["id"] for item in body["items"]]
    assert ids.index(festive) < ids.index(plain)
    festive_item = next(item for item in body["items"] if item["id"] == festive)
    assert festive_item["upcomingEventDate"] == (date.today() + timedelta(days=7)).isoformat()
    plain_item = next(item for item in body["items"] if item["id"] == plain)
    assert plain_item["upcomingEventDate"] is None


def test_temporarily_closed_visible_and_permanently_closed_hidden(
    client: TestClient, sessionfactory_for
) -> None:
    """FR-007: only permanently closed spots vanish; status shown for closed."""
    closed = _create_spot(
        client, "Teatro Reforma", -22.54, -45.04, ["culture"], status="temporarilyClosed"
    )
    _create_spot(client, "Cine Abandonado", -22.55, -45.05, ["cinema"], status="permanentlyClosed")

    body = _discover(client, _tourist_headers(client))
    ids = {item["id"] for item in body["items"]}
    assert closed in ids
    closed_item = next(item for item in body["items"] if item["id"] == closed)
    assert closed_item["status"] == "temporarilyClosed"
    assert all(item["status"] != "permanentlyClosed" for item in body["items"])


def test_without_position_valid_order_and_scores(client: TestClient, sessionfactory_for) -> None:
    """US1-AS3: proximity neutral — the response shape does not change."""
    _create_spot(client, "Parque Norte", -22.56, -45.06, ["nature"])
    body = _discover(client, _tourist_headers(client))
    for item in body["items"]:
        assert item["relevanceScore"] >= 0.0


def test_pagination_walk_no_duplicates_no_omissions(client: TestClient, sessionfactory_for) -> None:
    """SC-005/US1-AS6: concatenating pages reproduces the full order."""
    for index in range(5):
        _create_spot(client, f"Eco Ponto {index:02d}", -22.57 - index / 100, -45.07, ["nature"])
    headers = _tourist_headers(client)
    first_paged = _discover(client, headers, page=1, pageSize=2)
    assert first_paged["pageSize"] == 2 and first_paged["totalItems"] >= 5
    expected_total = first_paged["totalItems"]

    seen: list[int] = []
    page = 1
    while True:
        body = _discover(client, headers, page=page, pageSize=2)
        seen.extend(item["id"] for item in body["items"])
        if not body["items"]:
            break
        page += 1
    assert len(seen) == len(set(seen)) == expected_total

    # Full-order prefix agreement: pages 1..n in the same order as one page.
    whole = _discover(client, headers, pageSize=100)
    assert seen == [item["id"] for item in whole["items"]]


def test_page_beyond_last_is_empty_not_error(client: TestClient, sessionfactory_for) -> None:
    _create_spot(client, "Único Ponto", -22.58, -45.08, ["art"])
    body = _discover(client, _tourist_headers(client), page=99, pageSize=10)
    assert body["items"] == []


def test_invalid_coordinates_are_unified_422(client: TestClient, sessionfactory_for) -> None:
    headers = _tourist_headers(client)
    response = client.get(DISCOVER_URL, params={"latitude": 999, "longitude": -45}, headers=headers)
    assert response.status_code == 422
    assert response.json()["errorCode"]


def test_non_tourist_tokens_forbidden(client: TestClient, sessionfactory_for) -> None:
    anonymous = client.get(DISCOVER_URL)
    assert anonymous.status_code == 401  # authentication precedes RBAC
    assert anonymous.json()["errorCode"]

    admin = client.get(DISCOVER_URL, headers=_admin_headers(client))
    assert admin.status_code == 403
    assert admin.json()["errorCode"] == "authorization_failed"


def test_catalog_shrink_orphan_spot_ranks_as_non_matching(
    client: TestClient,
    sessionfactory_for,
    _bootstrap_admin: int,  # noqa: ARG001
) -> None:
    """FR-007 edge case (T024) — data predating a location.json catalog
    shrink survives storage (spec 007 persistence) but ranks as
    NON-matching in discovery: the spot category and the tourist interest
    are seeded through the repositories exactly as they would exist before
    the shrink, against the CURRENT (already shrunk) catalog."""
    from passanorte_back.modules.tourist_spots.repositories.tourist_spots import (
        TouristSpotCategory,
        add_spot,
    )
    from passanorte_back.modules.tourists.repositories.tourist_interests import (
        TouristInterest,
    )
    from tests.conftest import sessionfactory_for as _sf  # noqa: F401

    survivor = _create_spot(client, "Serra Pós-Shrink", -22.58, -45.08, ["nature"])

    # Real tourist via the API (token + account id), orphan interest via the
    # repository (the catalog rejected this key at selection time today).
    _TOURIST_COUNTER[0] += 1
    suffix = _TOURIST_COUNTER[0]
    raw = _valid_cpf(f"556677{suffix:03d}")
    register = client.post(
        "/api/v1/tourists",
        json={
            "firstName": "Orfa",
            "lastName": "Sobrevivente",
            "countryOfOrigin": "Brasil",
            "cpf": f"{raw[:3]}.{raw[3:6]}.{raw[6:]}",
            "passportNumber": None,
            "phone": f"+5511988{suffix:06d}",
            "email": f"shrink-{suffix}@example.com",
            "password": "long-enough-password-1",
        },
    )
    assert register.status_code == 201, register.text
    tourist_id = register.json()["id"]

    with sessionfactory_for() as session:
        orphan = add_spot(
            session,
            name="Serra Pré-Shrink",
            description="stored category no longer in the catalog",
            latitude=-22.59,
            longitude=-45.09,
        )
        session.add(TouristSpotCategory(spot_id=orphan.id, category_key="vanishing"))
        session.add(TouristInterest(tourist_id=tourist_id, category_key="vanishing"))
        session.commit()
        orphan_id = orphan.id

    login = client.post(
        TOURIST_LOGIN,
        json={"email": f"shrink-{suffix}@example.com", "password": "long-enough-password-1"},
    )
    assert login.status_code == 200, login.text
    headers = {"Authorization": f"Bearer {login.json()['accessToken']}"}
    body = _discover(client, headers)
    ids = [item["id"] for item in body["items"]]
    assert orphan_id in ids and survivor in ids  # feed never breaks (FR-007)

    by_id = {item["id"]: item for item in body["items"]}
    # The orphan spot cannot match the stored-but-vanished interest: its
    # score equals the plain non-matching spot's (same neutral factors).
    assert by_id[orphan_id]["relevanceScore"] == by_id[survivor]["relevanceScore"]
    # Label of a catalog-orphan key resolves to null (spec 007 behaviour).
    assert by_id[orphan_id]["categories"] == [{"key": "vanishing", "label": None}]
