"""Performance: dashboard metric budget (feature 014 — SC-006, T034).

Each of the five dashboard aggregates must answer under 2 s on the SC-006
reference dataset — 10,000 visitation events and 50,000 access events —
with the set-based SQL intact (FR-020; no Python-loop recompute). Seeded
through the repositories/Core in bulk (single-connection StaticPool
harness); the same per-endpoint shape/aggregation as the acceptance flow
is exercised, so a regression to per-row loops is caught by both budget
and shape.
"""

import time
from datetime import UTC, date, datetime

import pytest
from fastapi.testclient import TestClient

BASE_URL = "/api/v1/dashboard"
AUTH_LOGIN = "/api/v1/auth/login"

# SC-006 reference volumes:
SPOT_COUNT = 10
VISIT_COUNT = 10_000
TOURIST_COUNT = 100
ACCESS_EVENT_COUNT = 50_000

DASHBOARD_BUDGET_SECONDS = 2.0

BASE_DAY = date(2026, 11, 5)


def _admin_headers(client: TestClient) -> dict[str, str]:
    from tests.conftest import TEST_ADMIN_PASSWORD

    login = client.post(
        AUTH_LOGIN,
        json={"username": "admin.panel", "password": TEST_ADMIN_PASSWORD},
    )
    assert login.status_code == 200, login.text
    return {"Authorization": f"Bearer {login.json()['accessToken']}"}


def _seed_dataset(sessionfactory_for) -> None:  # noqa: ANN001
    """SC-006 reference dataset: 10 spots, 100 tourists/interests,
    10k visitations, 50k access events — bulk inserts."""
    from sqlalchemy import insert

    from passanorte_back.modules.dashboard.repositories.access_events import (
        AccessEvent,
    )
    from passanorte_back.modules.tourist_spots.repositories.tourist_spots import (
        TouristSpot,
    )
    from passanorte_back.modules.tourists.repositories.tourist_interests import (
        TouristInterest,
    )
    from passanorte_back.modules.tourists.repositories.tourists import Tourist
    from passanorte_back.modules.visitation.repositories.visitations import (
        Visitation,
    )

    with sessionfactory_for() as session:
        for index in range(1, SPOT_COUNT + 1):
            session.add(
                TouristSpot(
                    name=f"Spot Budget {index:02d}",
                    description="dashboard budget dataset spot",
                    latitude=-22.40 + index / 1000,
                    longitude=-45.00 + index / 100,
                    status="open",
                )
            )
        session.flush()
        spot_ids: list[int] = [
            int(spot.id) for spot in session.query(TouristSpot).order_by(TouristSpot.id)
        ]
        tourists: list[int] = []
        for index in range(1, TOURIST_COUNT + 1):
            tourist = Tourist(
                first_name=f"Turista{index}",
                last_name="Budget",
                country_of_origin=f"Pais{index % 8}",
                email_encrypted=f"enc{index}",
                email_lookup=f"perf-budget-{index:04d}",
                phone_encrypted=f"tel{index}",
                cpf_encrypted=None,
                cpf_lookup=None,
                passport_encrypted=None,
                passport_lookup=None,
                password_hash="synthetic",
            )
            session.add(tourist)
            tourists.append(None)  # filled after the flush below
        session.flush()
        tourists = [int(tourist.id) for tourist in session.query(Tourist)]
        category_pool = ["nature", "gastronomy", "culture", "leisure", "art", "cinema"]
        session.add_all(
            TouristInterest(
                tourist_id=tourists[index],
                category_key=category_pool[index % len(category_pool)],
            )
            for index in range(TOURIST_COUNT)
        )
        session.flush()

        visitations = [
            {
                "tourist_id": tourists[i % TOURIST_COUNT],
                "tourist_spot_id": spot_ids[i % SPOT_COUNT],
                "visited_at": datetime(2026, 11, (i % 30) + 1, 12, 0, tzinfo=UTC),
                "latitude": 0.0,
                "longitude": 0.0,
            }
            for i in range(VISIT_COUNT)
        ]
        # Chunked bulk inserts — SQLite caps bound variables per statement.
        _CHUNK = 100
        for start in range(0, len(visitations), _CHUNK):
            session.execute(insert(Visitation).values(visitations[start : start + _CHUNK]))

        access_events = [
            {
                "tourist_id": tourists[i % TOURIST_COUNT],
                "occurred_at": datetime(2026, 11, (i % 15) + 1, (i % 24), 0, tzinfo=UTC),
                "day": BASE_DAY,
            }
            for i in range(ACCESS_EVENT_COUNT)
        ]
        for start in range(0, len(access_events), _CHUNK):
            session.execute(insert(AccessEvent).values(access_events[start : start + _CHUNK]))

        session.commit()
    # Categories need the flush above committed as part of the same txn.


@pytest.fixture(autouse=True)
def _dataset(seeded_admin: int, sessionfactory_for) -> None:  # noqa: ANN001
    _seed_dataset(sessionfactory_for)


def _assert_budget(client: TestClient, headers: dict[str, str], path: str, params: str) -> None:
    started = time.perf_counter()
    response = client.get(f"{BASE_URL}{path}", headers=headers, params=params)
    elapsed = time.perf_counter() - started
    assert response.status_code == 200, (path, response.text)
    assert elapsed < DASHBOARD_BUDGET_SECONDS, (path, elapsed)


def test_dashboard_endpoints_under_two_seconds(client: TestClient, seeded_admin: int) -> None:
    """SC-006: five aggregates × < 2 s (10k visits + 50k access events)."""
    headers = _admin_headers(client)
    _assert_budget(client, headers, "/heatmap", params={"groupBy": "spot"})
    _assert_budget(client, headers, "/heatmap", params={"groupBy": "region"})
    _assert_budget(
        client,
        headers,
        "/access-counts",
        params={"period": "custom", "startDate": "2026-11-01", "endDate": "2026-11-30"},
    )
    _assert_budget(
        client,
        headers,
        "/spot-ranking",
        params={"granularity": "month", "referenceDate": "2026-11-05"},
    )
    _assert_budget(client, headers, "/visitor-countries", params={})
    _assert_budget(client, headers, "/visitor-interests", params={})
