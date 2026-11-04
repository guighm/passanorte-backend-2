"""Performance: discovery feed budget (feature 013, T019 — SC-006).

The ranked paginated listing must answer any single page below 1.0 s on an
approx. 1,000-spot reference dataset (clarified session 2026-11-03), with
the deterministic order intact (FR-003 — the budget never buys a different
order). Seeded through the repositories directly (single request path, no
HTTP fixture overhead beyond the TestClient); the dataset lives in the
isolated per-test SQLite in-memory database (StaticPool harness).
"""

import time

import pytest
from fastapi.testclient import TestClient

DISCOVER_URL = "/api/v1/tourist-spots/discover"
PAGE_BUDGET_SECONDS = 1.0
SPOT_COUNT = 1_000
EVENT_COUNT = 200
CATEGORY_POOL = ["gastronomy", "nature", "culture", "leisure", "art", "cinema"]


@pytest.fixture(autouse=True)
def _bootstrap_admin(seeded_admin: int) -> int:
    return seeded_admin


_REGISTER_COUNTER = [7000]


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


def _tourist_headers(client: TestClient, interests: list[str]) -> dict[str, str]:
    _REGISTER_COUNTER[0] += 1
    suffix = _REGISTER_COUNTER[0]
    email = f"perf-{suffix}@example.com"
    raw = _valid_cpf(f"111222{suffix % 1000:03d}")
    register = client.post(
        "/api/v1/tourists",
        json={
            "firstName": "Perf",
            "lastName": "Turista",
            "countryOfOrigin": "Brasil",
            "cpf": f"{raw[:3]}.{raw[3:6]}.{raw[6:]}",
            "passportNumber": None,
            "phone": f"+5511{suffix:08d}",
            "email": email,
            "password": "long-enough-password-1",
        },
    )
    assert register.status_code == 201, register.text
    login = client.post(
        "/api/v1/tourists/login",
        json={"email": email, "password": "long-enough-password-1"},
    )
    assert login.status_code == 200, login.text
    headers = {"Authorization": f"Bearer {login.json()['accessToken']}"}
    updated = client.put(
        "/api/v1/tourists/me/interests", json={"interests": interests}, headers=headers
    )
    assert updated.status_code == 200, updated.text
    return headers


def _seed_dataset(sessionfactory_for) -> None:
    """~1,000 active spots + events, seeded through the repositories."""
    from datetime import UTC, date, datetime, timedelta

    from passanorte_back.modules.events.repositories.events import Event
    from passanorte_back.modules.tourist_spots.repositories.tourist_spots import (
        TouristSpotCategory,
        add_spot,
    )

    now = datetime.now(UTC)
    today = date.today()
    ids: list[int] = []
    with sessionfactory_for() as session:
        index = 0
        while len(ids) < SPOT_COUNT:
            status = "open"
            if index % 97 == 0:
                status = "temporarilyClosed"
            index += 1
            spot = add_spot(
                session,
                name=f"Spot Perf {index:04d}",
                description="dataset spot for the discovery budget test",
                # Spread ~11 km around the anchor (still city-scale).
                latitude=-22.49 + (index % 100) / 1000,
                longitude=-45.0 + (index // 100) / 100,
                status=status,
            )
            session.add(TouristSpotCategory(spot_id=spot.id, category_key=CATEGORY_POOL[index % 6]))
            ids.append(spot.id)
        # Every eighth spot carries near-future events (spec US1 factor).
        for spot_id in ids[:EVENT_COUNT]:
            session.add(
                Event(
                    spot_id=spot_id,
                    occurrence_date=today + timedelta(days=7),
                    description="perf dataset event",
                    ticket_price_cents=0,
                    created_at=now,
                    updated_at=now,
                )
            )
        session.commit()
    assert len(ids) == SPOT_COUNT


def test_each_page_answers_below_budget(
    client: TestClient, sessionfactory_for, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Pages 1..5 with and without position: < 1 s each, order stable."""
    _seed_dataset(sessionfactory_for)

    def _timed_page(number: int, headers: dict, position: dict) -> list[int]:
        start = time.perf_counter()
        response = client.get(
            DISCOVER_URL,
            params={**position, "page": number, "pageSize": 20},
            headers=headers,
        )
        elapsed = time.perf_counter() - start
        assert response.status_code == 200, response.text
        assert elapsed < PAGE_BUDGET_SECONDS, (
            f"page {number} took {elapsed:.3f}s (budget {PAGE_BUDGET_SECONDS}s)"
        )
        return [item["id"] for item in response.json()["items"]]

    for tourist_interests, position in (
        (["gastronomy"], {"latitude": -22.49, "longitude": -45.0}),
        (["gastronomy"], {}),
        ([], {"latitude": -22.49, "longitude": -45.0}),
        ([], {}),
    ):
        headers = _tourist_headers(client, tourist_interests)

        whole = _timed_page(1, headers, position)  # warm-up ranking
        for page_number in range(1, 6):
            ids = _timed_page(page_number, headers, position)
            if page_number == 1:
                whole = ids  # keep the observed deterministic prefix

        # FR-003: repeats of the same request produce the identical order —
        # the budget test re-does page 1 and compares byte-for-byte.
        assert _timed_page(1, headers, position) == whole
        assert whole  # non-empty page 1


def test_scores_still_descend_within_budget_pages(client: TestClient, sessionfactory_for) -> None:
    """SC-006 order guarantee: concatenated pages keep score monotonicity."""
    _seed_dataset(sessionfactory_for)
    headers = _tourist_headers(client, ["nature"])

    seen_scores: list[float] = []
    page = 1
    while len(seen_scores) < 100:  # 5 pages
        response = client.get(DISCOVER_URL, params={"page": page, "pageSize": 20}, headers=headers)
        assert response.status_code == 200
        scores = [item["relevanceScore"] for item in response.json()["items"]]
        seen_scores.extend(scores)
        page += 1

    assert seen_scores == sorted(seen_scores, reverse=True)
    assert max(seen_scores) <= 1.0 and min(seen_scores) >= 0.0


def test_candidates_query_is_index_backed_not_a_full_scan(db_engine, sessionfactory_for) -> None:
    """T026 (tasks T020 sub-item): the discovery candidates query must be
    served by an index — never a full table scan (RNF12/plan §R3). The
    partial ``ix_tourist_spot_status_active`` must exist; SQLite's planner
    may equally pick the ``removed_at`` index (also index-backed) — both
    satisfy the bounded-work guarantee."""
    from sqlalchemy import inspect, text

    _seed_dataset(sessionfactory_for)

    inspector = inspect(db_engine)
    indexes = {index["name"] for index in inspector.get_indexes("tourist_spots")}
    assert "ix_tourist_spot_status_active" in indexes

    statement = text(
        "EXPLAIN QUERY PLAN SELECT * FROM tourist_spots "
        "WHERE removed_at IS NULL AND status != 'permanentlyClosed' "
        "ORDER BY id"
    )
    with db_engine.connect() as connection:
        rows = connection.execute(statement).fetchall()
    plans = " | ".join(str(row[3]) for row in rows)
    assert rows, "EXPLAIN QUERY PLAN returned no rows"
    assert "SCAN tourist_spots" not in plans, plans
    assert "SEARCH tourist_spots USING INDEX" in plans, plans
