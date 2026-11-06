"""Integration: dashboard acceptance flow (feature 014 — spec criteria).

Populates REAL data through the public paths — tourists of distinct
countries with distinct interest sets (registered via the API), visits
across several days and spots (via the visitation ledger, including a
soft-removed spot), and access events in the ledger — then validates the
five admin endpoints EXACTLY against the seeded expectation
(SC-001..SC-004, SC-007: every number reconstructible, none synthetic).
"""

import itertools
from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient

from tests.conftest import TEST_ADMIN_PASSWORD

BASE_URL = "/api/v1/dashboard"
AUTH_LOGIN = "/api/v1/auth/login"
TOURISTS_URL = "/api/v1/tourists"

ADMIN = {"username": "admin.panel", "password": TEST_ADMIN_PASSWORD}

_SEQUENCE = itertools.count(1)

# Fixed history: five days in November 2026 (window = 2026-11-02..11-06).
DAY = datetime(2026, 11, 5, 12, 0, tzinfo=UTC)


def _register(client: TestClient, *, country: str, interests: list[str]) -> int:
    sequence = next(_SEQUENCE)
    email = f"flow-tourist-{sequence}@example.com"
    payload = {
        "firstName": "Turista",
        "lastName": f"De Fluxo {sequence}",
        "countryOfOrigin": country,
        "cpf": None,
        "passportNumber": f"ZZ{sequence:06d}",
        "phone": "+5511999999999",
        "email": email,
        "password": "long-enough-password-1",
    }
    register = client.post(TOURISTS_URL, json=payload)
    assert register.status_code == 201, register.text
    tourist_id = int(register.json()["id"])
    if interests:
        login = client.post(
            "/api/v1/tourists/login",
            json={"email": email, "password": payload["password"]},
        )
        assert login.status_code == 200, login.text
        selected = client.put(
            f"{TOURISTS_URL}/me/interests",
            headers={"Authorization": f"Bearer {login.json()['accessToken']}"},
            json={"interests": interests},
        )
        assert selected.status_code == 200, selected.text
    return tourist_id


def _spot(sessionfactory_for, *, name: str, latitude: float, longitude: float) -> int:  # noqa: ANN001
    from passanorte_back.modules.tourist_spots.repositories.tourist_spots import add_spot

    with sessionfactory_for() as session:
        spot = add_spot(
            session,
            name=name,
            description="Acceptance-flow spot.",
            latitude=latitude,
            longitude=longitude,
        )
        session.commit()
        return int(spot.id)


def _visit(sessionfactory_for, *, tourist_id: int, spot_id: int, at: datetime) -> None:  # noqa: ANN001
    from passanorte_back.modules.visitation.repositories.visitations import insert_visit

    with sessionfactory_for() as session:
        visitation = insert_visit(
            session,
            tourist_id=tourist_id,
            tourist_spot_id=spot_id,
            latitude=0.0,
            longitude=0.0,
        )
        visitation.visited_at = at
        session.commit()


def _remove(sessionfactory_for, spot_id: int) -> None:  # noqa: ANN001
    from passanorte_back.modules.tourist_spots.repositories.tourist_spots import (
        find_active_by_id,
    )

    with sessionfactory_for() as session:
        spot = find_active_by_id(session, spot_id)
        assert spot is not None
        spot.removed_at = datetime.now(UTC)
        session.commit()


def _access_events(sessionfactory_for, *, by_tourist: dict[int, list[str]]) -> None:  # noqa: ANN001
    from datetime import datetime as _datetime

    from passanorte_back.modules.dashboard.repositories.access_events import (
        add_access_event,
    )

    with sessionfactory_for() as session:
        for tourist_id, days in by_tourist.items():
            for day in days:
                add_access_event(
                    session,
                    tourist_id=tourist_id,
                    occurred_at=_datetime.fromisoformat(f"{day}T12:00:00+00:00"),
                )
        session.commit()


def test_dashboard_acceptance_flow(
    client: TestClient, seeded_admin: int, seeded_employee: int, sessionfactory_for
) -> None:
    """SC-001..SC-004, SC-007 over the five endpoints."""
    # ── Population: 4 registered tourists (2× Brasil, 1× Argentina, 1× Chile)
    cassia = _register(client, country="Brasil", interests=["nature", "gastronomy"])
    bia = _register(client, country="Brasil", interests=["nature"])
    lucas = _register(client, country="Argentina", interests=["culture"])
    _register(client, country="Chile", interests=[])  # registered, no visits
    _register(client, country="Portugal", interests=["art"])  # visitor never

    # ── Spots: two active + one removed (its history KEEPS counting — R7).
    falls = _spot(sessionfactory_for, name="Cascata da Pedra", latitude=-22.30, longitude=-44.90)
    lookout = _spot(sessionfactory_for, name="Mirante do Vale", latitude=-22.45, longitude=-45.05)
    closed_spot = _spot(sessionfactory_for, name="Parque Antigo", latitude=-22.50, longitude=-45.10)

    # ── Visits (window 2026-11-02..11-06): falls=4, lookout=1, old park=2.
    _visit(sessionfactory_for, tourist_id=cassia, spot_id=falls, at=DAY - timedelta(days=1))
    _visit(sessionfactory_for, tourist_id=cassia, spot_id=falls, at=DAY)
    _visit(sessionfactory_for, tourist_id=bia, spot_id=falls, at=DAY)
    _visit(sessionfactory_for, tourist_id=lucas, spot_id=falls, at=DAY - timedelta(days=2))
    _visit(sessionfactory_for, tourist_id=lucas, spot_id=lookout, at=DAY)
    _visit(sessionfactory_for, tourist_id=cassia, spot_id=closed_spot, at=DAY - timedelta(days=3))
    _visit(sessionfactory_for, tourist_id=bia, spot_id=closed_spot, at=DAY - timedelta(days=3))
    _remove(sessionfactory_for, closed_spot)

    # Outside the queried window (2026-10-31) — must NOT count.
    _visit(
        sessionfactory_for,
        tourist_id=cassia,
        spot_id=falls,
        at=datetime(2026, 10, 31, 12, 0, tzinfo=UTC),
    )

    # ── Access ledger (window same): 4 unique tourist-days, 6 events.
    _access_events(
        sessionfactory_for,
        by_tourist={
            cassia: ["2026-11-02", "2026-11-04", "2026-11-04"],
            bia: ["2026-11-03"],
            lucas: ["2026-11-04", "2026-11-05"],
        },
    )

    admin = {"Authorization": f"Bearer {client.post(AUTH_LOGIN, json=ADMIN).json()['accessToken']}"}

    # ── US1: heat map, spot mode — weights equal the real counts (SC-001):
    # the all-history map ALSO includes the out-of-window visit (10-31).
    full_map = client.get(f"{BASE_URL}/heatmap", headers=admin).json()
    assert {marker["spotId"]: marker["weight"] for marker in full_map["markers"]} == {
        falls: 5,
        lookout: 1,
        closed_spot: 2,
    }
    heatmap = client.get(
        f"{BASE_URL}/heatmap",
        headers=admin,
        params={"startDate": "2026-11-02", "endDate": "2026-11-06"},
    ).json()
    weights = {marker["spotId"]: marker["weight"] for marker in heatmap["markers"]}
    assert weights == {falls: 4, lookout: 1, closed_spot: 2}
    marker = next(
        marker for marker in heatmap["markers"] if marker["spotId"] == falls
    )  # the spot's own coordinates (RNF06 — nothing hardcoded)
    assert (marker["latitude"], marker["longitude"]) == (-22.30, -44.90)

    # ── US2: access counter for the custom window (SC-002).
    counter = client.get(
        f"{BASE_URL}/access-counts",
        headers=admin,
        params={"period": "custom", "startDate": "2026-11-02", "endDate": "2026-11-06"},
    ).json()
    assert counter["totalAccessEvents"] == 6
    # Distinct tourist×day: cassia(11-02), cassia(11-04), bia(11-03),
    # lucas(11-04), lucas(11-05) = 5 pairs from 6 events.
    assert counter["uniqueTouristDays"] == 5
    daily = {item["date"]: item for item in counter["daily"]}
    assert daily["2026-11-04"] == {
        "date": "2026-11-04",
        "uniqueTourists": 2,
        "accessEvents": 3,
    }

    # ── US3: monthly ranking — order, counts, top N (SC-003).
    ranking = client.get(
        f"{BASE_URL}/spot-ranking",
        headers=admin,
        params={"granularity": "month", "referenceDate": "2026-11-05", "limit": 2},
    ).json()
    assert [(item["spotId"], item["visits"]) for item in ranking["items"]] == [
        (falls, 4),
        (closed_spot, 2),
    ]

    # ── US4: country distribution over visitors only (SC-004).
    countries = client.get(f"{BASE_URL}/visitor-countries", headers=admin).json()
    assert countries["totalVisitors"] == 3  # Chile + Portugal tourists never visited
    country_shares = {
        item["country"]: (item["tourists"], item["share"]) for item in countries["items"]
    }
    assert country_shares == {"Brasil": (2, 66.7), "Argentina": (1, 33.3)}

    # ── US5: interest distribution over the same visitor population.
    interests = client.get(f"{BASE_URL}/visitor-interests", headers=admin).json()
    assert interests["totalVisitors"] == 3
    assert interests["totalSelections"] == 4  # 2 (cassia) + 1 (bia) + 1 (lucas)
    by_key = {item["interestKey"]: (item["tourists"], item["share"]) for item in interests["items"]}
    assert by_key == {
        "nature": (2, 50.0),
        "gastronomy": (1, 25.0),
        "culture": (1, 25.0),
    }
    assert by_key["nature"][0] == 2  # cassia + bia; shares relative to selections

    # ── Every number reconstructible from the ledger (SC-007 spot-check):
    # the windowed heat map for a single day equals that day's rows.
    day_map = client.get(
        f"{BASE_URL}/heatmap",
        headers=admin,
        params={"startDate": "2026-11-05", "endDate": "2026-11-05"},
    ).json()
    day_weights = {marker["spotId"]: marker["weight"] for marker in day_map["markers"]}
    assert day_weights == {falls: 2, lookout: 1}
