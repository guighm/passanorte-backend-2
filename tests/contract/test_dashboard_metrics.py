"""Contract: dashboard metric endpoints (feature 014 — contracts/dashboard.md).

All endpoints ride the pre-mounted module router (tag ``Dashboard`` from
the central registry — spec 006) and are admin-only (``require_admin``, RF03:
401 anonymous / 403 employee-tourist / 200 admin). Every response shape is
camelCase via ``ApiModel`` and every failure path is the unified ``ApiError``
payload (spec 005). Seeds use REAL rows of the existing domains (spots,
visitations, tourists, interests) — the module reads, never invents
(SC-007).
"""

import itertools
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient

from tests.conftest import TEST_ADMIN_PASSWORD

BASE_URL = "/api/v1/dashboard"
AUTH_LOGIN = "/api/v1/auth/login"
TOURISTS_URL = "/api/v1/tourists"
TOURIST_LOGIN = "/api/v1/tourists/login"

ADMIN_CREDENTIALS = {"username": "admin.panel", "password": TEST_ADMIN_PASSWORD}
EMPLOYEE_CREDENTIALS = {
    "username": "maria.panel",
    "password": "synthetic-employee-password-1",
}

_SEQUENCE = itertools.count(1)


def _admin_headers(client: TestClient) -> dict[str, str]:
    login = client.post(AUTH_LOGIN, json=ADMIN_CREDENTIALS)
    assert login.status_code == 200, login.text
    return {"Authorization": f"Bearer {login.json()['accessToken']}"}


def _employee_headers(client: TestClient) -> dict[str, str]:
    login = client.post(AUTH_LOGIN, json=EMPLOYEE_CREDENTIALS)
    assert login.status_code == 200, login.text
    return {"Authorization": f"Bearer {login.json()['accessToken']}"}


def _register_tourist(
    client: TestClient,
    *,
    country: str = "Brasil",
    interests: list[str] | None = None,
) -> int:
    """Register a fresh tourist (unique email/identity) and return the id.
    Real registration path — sensitive columns never surface here."""
    sequence = next(_SEQUENCE)
    email = f"dashboard-tourist-{sequence}@example.com"
    payload: dict[str, Any] = {
        "firstName": "Ana",
        "lastName": "Silva",
        "countryOfOrigin": country,
        "cpf": None,
        "passportNumber": f"AB{sequence:06d}",
        "phone": "+5511999999999",
        "email": email,
        "password": "long-enough-password-1",
    }
    response = client.post(TOURISTS_URL, json=payload)
    assert response.status_code == 201, response.text
    tourist_id = int(response.json()["id"])
    if interests:
        login = client.post(TOURIST_LOGIN, json={"email": email, "password": payload["password"]})
        assert login.status_code == 200, login.text
        selected = client.put(
            f"{TOURISTS_URL}/me/interests",
            headers={"Authorization": f"Bearer {login.json()['accessToken']}"},
            json={"interests": interests},
        )
        assert selected.status_code == 200, selected.text
    return tourist_id


def _make_spot(sessionfactory_for, *, name: str, latitude: float, longitude: float) -> int:  # noqa: ANN001
    from passanorte_back.modules.tourist_spots.repositories.tourist_spots import add_spot

    with sessionfactory_for() as session:
        spot = add_spot(
            session,
            name=name,
            description="Spot seeded for the dashboard metrics.",
            latitude=latitude,
            longitude=longitude,
            status="open",
            tolerance_radius_m=None,
        )
        session.commit()
        return int(spot.id)


def _remove_spot(sessionfactory_for, spot_id: int) -> None:  # noqa: ANN001
    """Soft-delete a spot — historical visits keep counting (research R7)."""
    from passanorte_back.modules.tourist_spots.repositories.tourist_spots import (
        find_active_by_id,
    )

    with sessionfactory_for() as session:
        spot = find_active_by_id(session, spot_id)
        assert spot is not None
        spot.removed_at = datetime.now(UTC)
        session.commit()


def _make_visit(
    sessionfactory_for,  # noqa: ANN001
    *,
    tourist_id: int,
    spot_id: int,
    visited_at: datetime,
) -> None:
    from passanorte_back.modules.visitation.repositories.visitations import insert_visit

    with sessionfactory_for() as session:
        visitation = insert_visit(
            session,
            tourist_id=tourist_id,
            tourist_spot_id=spot_id,
            latitude=0.0,
            longitude=0.0,
        )
        # Deterministic history seeding (the API captures now()).
        visitation.visited_at = visited_at
        session.commit()


def _no_regions_location(monkeypatch, tmp_path: Path) -> None:  # noqa: ANN001
    """Point the settings singleton at a location file WITHOUT ``regions``."""
    from passanorte_back.core.db import settings as live_settings

    data = json.loads(Path(live_settings.location_data_path).read_text(encoding="utf-8"))
    data.pop("regions", None)
    location = tmp_path / "location-no-regions.json"
    location.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    monkeypatch.setattr(live_settings, "location_data_path", location)


def test_heatmap_contract(client: TestClient, seeded_admin: int, sessionfactory_for) -> None:
    """GET /heatmap (FR-004/FR-006): markers per spot, weight = visits."""
    tourist_id = _register_tourist(client, country="Brasil")
    spot_a = _make_spot(
        sessionfactory_for, name="Cachoeira Contract A", latitude=-22.40, longitude=-45.00
    )
    spot_b = _make_spot(
        sessionfactory_for, name="Cachoeira Contract B", latitude=-22.50, longitude=-45.10
    )
    base = datetime(2026, 11, 4, 12, 0, tzinfo=UTC)
    for spot_id, count in ((spot_a, 3), (spot_b, 1)):
        for index in range(count):
            # spot_b's single visit is explicitly OUTSIDE the 11-04 window.
            extra_day = 1 if spot_id == spot_b else 0
            _make_visit(
                sessionfactory_for,
                tourist_id=tourist_id,
                spot_id=spot_id,
                visited_at=base - timedelta(days=index + extra_day),
            )

    admin = _admin_headers(client)
    response = client.get(f"{BASE_URL}/heatmap", headers=admin)
    assert response.status_code == 200, response.text
    body = response.json()
    assert set(body) == {"markers"}
    markers = body["markers"]
    by_spot = {marker["spotId"]: marker for marker in markers}
    assert set(by_spot) == {spot_a, spot_b}
    assert by_spot[spot_a]["weight"] == 3
    assert by_spot[spot_b]["weight"] == 1
    for marker in markers:
        assert set(marker) >= {"spotId", "name", "latitude", "longitude", "weight"}

    # Optional inclusive window (FR-006): only visits in range count.
    windowed = client.get(
        f"{BASE_URL}/heatmap",
        headers=admin,
        params={"startDate": "2026-11-04", "endDate": "2026-11-04"},
    )
    assert windowed.status_code == 200, windowed.text
    weights = {m["spotId"]: m["weight"] for m in windowed.json()["markers"]}
    assert weights.get(spot_a) == 1
    assert weights.get(spot_b) is None  # its visit is outside the window

    # Removed spot keeps counting its history (edge case, research R7).
    _remove_spot(sessionfactory_for, spot_b)
    after_removal = client.get(
        f"{BASE_URL}/heatmap",
        headers=admin,
        params={"startDate": "2026-11-01", "endDate": "2026-11-04"},
    )
    assert after_removal.status_code == 200
    weights = {m["spotId"]: m["weight"] for m in after_removal.json()["markers"]}
    assert weights.get(spot_b) == 1


def test_heatmap_region_contract(
    client: TestClient, seeded_admin: int, sessionfactory_for, monkeypatch, tmp_path
) -> None:
    """FR-005 (Q2): groupBy=region aggregates the configured spot-name groups."""
    tourist_id = _register_tourist(client, country="Brasil")
    # The default location data has regions: 'waterfalls' → ["Cachoeira Édem"]
    # and 'city' → unknown names (skipped by the resolver, data-driven).
    spot = _make_spot(sessionfactory_for, name="Cachoeira Édem", latitude=-22.40, longitude=-45.00)
    for _ in range(2):
        _make_visit(
            sessionfactory_for,
            tourist_id=tourist_id,
            spot_id=spot,
            visited_at=datetime(2026, 11, 5, 12, 0, tzinfo=UTC),
        )
    admin = _admin_headers(client)
    response = client.get(f"{BASE_URL}/heatmap", headers=admin, params={"groupBy": "region"})
    assert response.status_code == 200, response.text
    markers = response.json()["markers"]
    assert markers, "the configured waterfalls region had seeded visits"
    region = markers[0]
    assert region["spotId"] is None
    assert region["name"] == "Cachoeiras"
    assert region["weight"] == 2
    assert region["latitude"] == -22.40  # single known spot → its own coordinate

    # No regions block → 422 (FR-005, contracts §6).
    _no_regions_location(monkeypatch, tmp_path)
    response = client.get(f"{BASE_URL}/heatmap", headers=admin, params={"groupBy": "region"})
    assert response.status_code == 422
    assert "errorCode" in response.json()


def test_heatmap_validation_contract(client: TestClient, seeded_admin: int) -> None:
    """Edge cases: inverted range → 422; unknown groupBy → 422."""
    admin = _admin_headers(client)
    inverted = client.get(
        f"{BASE_URL}/heatmap",
        headers=admin,
        params={"startDate": "2026-11-02", "endDate": "2026-11-01"},
    )
    assert inverted.status_code == 422
    assert "errorCode" in inverted.json()
    unknown = client.get(f"{BASE_URL}/heatmap", headers=admin, params={"groupBy": "street"})
    assert unknown.status_code == 422


def test_heatmap_requires_admin(
    client: TestClient, seeded_admin: int, seeded_employee: int
) -> None:
    """RF03: anonymous → 401; employee session → 403."""
    assert client.get(f"{BASE_URL}/heatmap").status_code == 401
    employee = _employee_headers(client)
    assert client.get(f"{BASE_URL}/heatmap", headers=employee).status_code == 403


def _seed_access_events(sessionfactory_for, *, tourist_id: int, days: list[str]) -> None:  # noqa: ANN001
    """Append access events at fixed days (deterministic ledger)."""
    from datetime import datetime as _datetime

    from passanorte_back.modules.dashboard.repositories.access_events import (
        add_access_event,
    )

    with sessionfactory_for() as session:
        for day in days:
            add_access_event(
                session,
                tourist_id=tourist_id,
                occurred_at=_datetime.fromisoformat(f"{day}T12:00:00+00:00"),
            )
        session.commit()


def _seed_access_on_days(sessionfactory_for, *, by_tourist: dict[int, list[str]]) -> None:  # noqa: ANN001
    for tourist_id, days in by_tourist.items():
        _seed_access_events(sessionfactory_for, tourist_id=tourist_id, days=days)


def test_access_counts_contract(client: TestClient, seeded_admin: int, sessionfactory_for) -> None:
    """GET /access-counts (FR-009/FR-010): unique tourist×day + total events."""
    _seed_access_on_days(
        sessionfactory_for,
        by_tourist={
            1: ["2026-11-04", "2026-11-04", "2026-11-05"],  # same-day repeats collapse
            2: ["2026-11-05"],
        },
    )
    admin = _admin_headers(client)

    custom = client.get(
        f"{BASE_URL}/access-counts",
        headers=admin,
        params={"period": "custom", "startDate": "2026-11-02", "endDate": "2026-11-07"},
    )
    assert custom.status_code == 200, custom.text
    body = custom.json()
    assert set(body) >= {"uniqueTouristDays", "totalAccessEvents", "daily"}
    # Events: 3 + 1 = 4; distinct tourist×day pairs: (1,04) (1,05) (2,05) = 3.
    assert body["totalAccessEvents"] == 4
    assert body["uniqueTouristDays"] == 3
    daily = {item["date"]: item for item in body["daily"]}
    assert set(daily) == {"2026-11-04", "2026-11-05"}
    assert daily["2026-11-04"] == {"date": "2026-11-04", "uniqueTourists": 1, "accessEvents": 2}
    assert daily["2026-11-05"] == {
        "date": "2026-11-05",
        "uniqueTourists": 2,
        "accessEvents": 2,
    }

    # Empty window → zeros (edge case).
    empty = client.get(
        f"{BASE_URL}/access-counts",
        headers=admin,
        params={"period": "custom", "startDate": "2026-01-01", "endDate": "2026-01-02"},
    )
    assert empty.status_code == 200
    assert empty.json()["totalAccessEvents"] == 0
    assert empty.json()["uniqueTouristDays"] == 0
    assert empty.json()["daily"] == []


def test_access_counts_period_anchors(
    client: TestClient, seeded_admin: int, sessionfactory_for, monkeypatch
) -> None:
    """FR-009: today/week/month anchors in the city tz (RNF06)."""
    from passanorte_back.modules.dashboard.repositories.access_events import city_tz

    city_now = datetime.now(UTC).astimezone(city_tz())
    monday = city_now.replace(hour=12, microsecond=0) - timedelta(days=city_now.weekday())
    _seed_access_on_days(
        sessionfactory_for,
        by_tourist={
            1: [monday.date().isoformat(), city_now.date().isoformat()],
            2: [city_now.date().isoformat()],
        },
    )
    admin = _admin_headers(client)
    today = client.get(f"{BASE_URL}/access-counts", headers=admin, params={"period": "today"})
    assert today.status_code == 200
    body = today.json()
    assert body["totalAccessEvents"] == 2
    assert body["uniqueTouristDays"] == 2
    week = client.get(f"{BASE_URL}/access-counts", headers=admin, params={"period": "week"})
    assert week.status_code == 200
    # The Monday seeded event + today's two → 3 events, 3 tourist-days.
    assert week.json()["totalAccessEvents"] == 3
    assert week.json()["uniqueTouristDays"] == 3


def test_access_counts_validation_contract(client: TestClient, seeded_admin: int) -> None:
    """contracts §6: custom without dates / unknown period / inverted → 422."""
    admin = _admin_headers(client)
    cases = [
        {"period": "custom"},
        {"period": "custom", "endDate": "2026-11-01"},
        {"period": "custom", "startDate": "2026-11-02", "endDate": "2026-11-01"},
        {"period": "year"},
    ]
    for params in cases:
        response = client.get(f"{BASE_URL}/access-counts", headers=admin, params=params)
        assert response.status_code == 422, (params, response.text)
        assert "errorCode" in response.json()


def test_access_counts_requires_admin(
    client: TestClient, seeded_admin: int, seeded_employee: int
) -> None:
    """RF03: anonymous → 401; employee session → 403."""
    assert client.get(f"{BASE_URL}/access-counts").status_code == 401
    employee = _employee_headers(client)
    response = client.get(f"{BASE_URL}/access-counts", headers=employee, params={"period": "today"})
    assert response.status_code == 403


def test_spot_ranking_contract(client: TestClient, seeded_admin: int, sessionfactory_for) -> None:
    """GET /spot-ranking (FR-012/FR-013/FR-014): one window per query."""
    tourist_id = _register_tourist(client)
    spot_a = _make_spot(sessionfactory_for, name="Rank A", latitude=-22.4, longitude=-45.0)
    spot_b = _make_spot(sessionfactory_for, name="Rank B", latitude=-22.6, longitude=-45.2)
    _make_spot(sessionfactory_for, name="Rank Zero", latitude=-22.7, longitude=-45.3)
    base = datetime(2026, 11, 5, 12, 0, tzinfo=UTC)
    # November 2026: A=3 visits, B=1; zero-visit spot excluded.
    for offset in (0, 1, 2):
        _make_visit(
            sessionfactory_for,
            tourist_id=tourist_id,
            spot_id=spot_a,
            visited_at=base - timedelta(days=offset),
        )
    _make_visit(sessionfactory_for, tourist_id=tourist_id, spot_id=spot_b, visited_at=base)

    admin = _admin_headers(client)
    ranking = client.get(
        f"{BASE_URL}/spot-ranking",
        headers=admin,
        params={"granularity": "month", "referenceDate": "2026-11-05", "limit": 2},
    )
    assert ranking.status_code == 200, ranking.text
    body = ranking.json()
    assert body["granularity"] == "month"
    assert body["referenceDate"] == "2026-11-05"
    items = body["items"]
    assert [(item["spotId"], item["name"], item["visits"]) for item in items] == [
        (spot_a, "Rank A", 3),
        (spot_b, "Rank B", 1),
    ]
    assert [item["position"] for item in items] == [1, 2]

    # Day granularity: only that day's visits (day 2026-11-03 → A once).
    day = client.get(
        f"{BASE_URL}/spot-ranking",
        headers=admin,
        params={"granularity": "day", "referenceDate": "2026-11-03"},
    )
    assert day.status_code == 200
    day_items = day.json()["items"]
    assert [(item["spotId"], item["visits"]) for item in day_items] == [(spot_a, 1)]

    # Default limit (5) applies when not provided; ties by spotId (stable).
    default_limit = client.get(
        f"{BASE_URL}/spot-ranking",
        headers=admin,
        params={"granularity": "month", "referenceDate": "2026-11-05"},
    )
    assert default_limit.status_code == 200
    assert len(default_limit.json()["items"]) == 2  # only visited spots

    # Validation: unknown granularity / out-of-range limit → 422.
    assert (
        client.get(
            f"{BASE_URL}/spot-ranking",
            headers=admin,
            params={"granularity": "week", "referenceDate": "2026-11-05"},
        ).status_code
        == 422
    )
    assert (
        client.get(
            f"{BASE_URL}/spot-ranking",
            headers=admin,
            params={"granularity": "day", "limit": 0},
        ).status_code
        == 422
    )
    assert (
        client.get(
            f"{BASE_URL}/spot-ranking",
            headers=admin,
            params={"granularity": "day", "limit": 101},
        ).status_code
        == 422
    )


def test_spot_ranking_requires_admin(
    client: TestClient, seeded_admin: int, seeded_employee: int
) -> None:
    """RF03: anonymous → 401; employee session → 403."""
    assert client.get(f"{BASE_URL}/spot-ranking", params={"granularity": "day"}).status_code == 401
    employee = _employee_headers(client)
    response = client.get(
        f"{BASE_URL}/spot-ranking",
        headers=employee,
        params={"granularity": "day"},
    )
    assert response.status_code == 403


def test_visitor_countries_contract(
    client: TestClient, seeded_admin: int, seeded_employee: int, sessionfactory_for
) -> None:
    """GET /visitor-countries (FR-015/FR-016): proportions over visitors."""
    # Two Brazilians and one Argentine with visits; one Chilean registered
    # but with NO visit (excluded from the population — FR-016).
    brazil_1 = _register_tourist(client, country="Brasil")
    brazil_2 = _register_tourist(client, country="Brasil")
    argentina = _register_tourist(client, country="Argentina")
    _register_tourist(client, country="Chile")
    spot = _make_spot(sessionfactory_for, name="Country Spot", latitude=-22.3, longitude=-44.9)
    base = datetime(2026, 11, 5, 12, 0, tzinfo=UTC)
    for tourist_id in (brazil_1, brazil_1, brazil_2, argentina):
        _make_visit(sessionfactory_for, tourist_id=tourist_id, spot_id=spot, visited_at=base)

    admin = _admin_headers(client)
    response = client.get(f"{BASE_URL}/visitor-countries", headers=admin)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["totalVisitors"] == 3  # distinct visitors (brazil_1 twice)
    items = body["items"]
    shares = {item["country"]: (item["tourists"], item["share"]) for item in items}
    assert shares == {
        "Brasil": (2, 66.7),
        "Argentina": (1, 33.3),
    }
    assert abs(sum(item["share"] for item in items) - 100.0) <= 0.5

    # Optional inclusive window (FR-016): visitors inside the window only.
    windowed = client.get(
        f"{BASE_URL}/visitor-countries",
        headers=admin,
        params={"startDate": "2026-11-06", "endDate": "2026-11-06"},
    )
    assert windowed.status_code == 200
    assert windowed.json()["totalVisitors"] == 0
    assert windowed.json()["items"] == []

    # Anonymous → 401; employee session → 403 (RF03).
    assert client.get(f"{BASE_URL}/visitor-countries").status_code == 401
    employee = _employee_headers(client)
    assert client.get(f"{BASE_URL}/visitor-countries", headers=employee).status_code == 403


def test_visitor_interests_contract(
    client: TestClient, seeded_admin: int, seeded_employee: int, sessionfactory_for
) -> None:
    """GET /visitor-interests (FR-017/FR-018): same visitor population;
    a tourist counts once per declared interest (US5)."""
    # Visitor with 2 interests; visitor with 1 (different key); a tourist
    # with interests but no visit does NOT contribute; a visitor with NO
    # interests contributes nothing either.
    nature = _register_tourist(client, country="Brasil", interests=["nature", "culture"])
    gastronomy = _register_tourist(client, country="Chile", interests=["gastronomy"])
    _register_tourist(client, country="Peru", interests=["art"])
    no_interests = _register_tourist(client, country="Uruguai")
    spot = _make_spot(sessionfactory_for, name="Interest Spot", latitude=-22.3, longitude=-44.9)
    _make_visit(
        sessionfactory_for,
        tourist_id=nature,
        spot_id=spot,
        visited_at=datetime(2026, 11, 5, 12, 0, tzinfo=UTC),
    )
    _make_visit(
        sessionfactory_for,
        tourist_id=gastronomy,
        spot_id=spot,
        visited_at=datetime(2026, 11, 5, 12, 0, tzinfo=UTC),
    )
    _make_visit(
        sessionfactory_for,
        tourist_id=no_interests,
        spot_id=spot,
        visited_at=datetime(2026, 11, 5, 12, 0, tzinfo=UTC),
    )

    admin = _admin_headers(client)
    response = client.get(f"{BASE_URL}/visitor-interests", headers=admin)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["totalVisitors"] == 3  # incl. the visitor without interests
    assert body["totalSelections"] == 3  # 2 + 1 + 0
    by_key = {item["interestKey"]: (item["tourists"], item["share"]) for item in body["items"]}
    assert by_key["nature"] == (1, round(1 / 3 * 100, 1))
    assert by_key["culture"] == (1, round(1 / 3 * 100, 1))
    assert by_key["gastronomy"] == (1, round(1 / 3 * 100, 1))
    assert "art" not in by_key  # declared but this visitor never visited
    labels = {item["interestKey"]: item["interestLabel"] for item in body["items"]}
    assert labels["nature"] == "Natureza"  # label from location categories
    assert labels["gastronomy"] == "Gastronomia"

    # Anonymous → 401; employee session → 403 (RF03).
    assert client.get(f"{BASE_URL}/visitor-interests").status_code == 401
    employee = _employee_headers(client)
    assert client.get(f"{BASE_URL}/visitor-interests", headers=employee).status_code == 403


_ALL_ENDPOINT_PARAMS: dict[str, dict[str, str]] = {
    "/heatmap": {"groupBy": "spot"},
    "/access-counts": {"period": "today"},
    "/spot-ranking": {"granularity": "day"},
    "/visitor-countries": {},
    "/visitor-interests": {},
}


def test_all_endpoints_admin_only(
    client: TestClient,
    seeded_admin: int,
    seeded_employee: int,
) -> None:
    """RF03/SC-005 matrix: five endpoints × {anonymous, employee, tourist}."""
    tourist = _tourist_token_headers(client)
    # Sanity: the tourist session itself is a valid bearer identity.
    assert client.get(f"{TOURISTS_URL}/me/interests", headers=tourist).status_code == 200
    employee = _employee_headers(client)
    for endpoint, params in _ALL_ENDPOINT_PARAMS.items():
        url = f"{BASE_URL}{endpoint}"
        assert client.get(url, params=params).status_code == 401, endpoint
        employee_response = client.get(url, headers=employee, params=params)
        assert employee_response.status_code == 403, (endpoint, employee_response.status_code)
        tourist_response = client.get(url, headers=tourist, params=params)
        assert tourist_response.status_code == 403, (endpoint, tourist_response.status_code)


def test_openapi_single_dashboard_tag(client: TestClient, seeded_admin: int) -> None:
    """FR-002: every dashboard endpoint is listed under the ONE Dashboard tag."""
    openapi = client.get("/openapi.json").json()
    paths = [path for path in openapi["paths"] if path.startswith("/api/v1/dashboard")]
    assert len(paths) == 5, paths
    for path in paths:
        for method in openapi["paths"][path]:
            assert openapi["paths"][path][method]["tags"] == ["Dashboard"], (path, method)


def _tourist_token_headers(client: TestClient) -> dict[str, str]:  # noqa: ANN201
    """Register a fresh tourist and authenticate — bearer headers."""
    sequence = next(_SEQUENCE)
    email = f"dashboard-tourist-{sequence}@example.com"
    payload: dict[str, Any] = {
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
    login = client.post(TOURIST_LOGIN, json={"email": email, "password": payload["password"]})
    assert login.status_code == 200, login.text
    return {"Authorization": f"Bearer {login.json()['accessToken']}"}
