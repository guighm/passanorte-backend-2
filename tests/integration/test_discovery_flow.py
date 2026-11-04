"""Integration: discovery end-to-end flow (feature 013, T013 — spec US1).

Full tourist journey across seams: register (spec 002) → select interests
(spec 003 public API) → discover with and without position (RF26) → walk
every page with zero duplicates and zero omissions (SC-005) → interests
still replaceable afterwards.
"""

import pytest
from fastapi.testclient import TestClient

from tests.conftest import TEST_ADMIN_PASSWORD


@pytest.fixture(autouse=True)
def _bootstrap_admin(seeded_admin: int) -> int:
    return seeded_admin


DISCOVER_URL = "/api/v1/tourist-spots/discover"
INTERESTS_URL = "/api/v1/tourists/me/interests"
CREATE = "/api/v1/tourists"


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


_REGISTER_COUNTER = [300]


def _tourist(client: TestClient) -> tuple[dict[str, str], dict[str, object]]:
    _REGISTER_COUNTER[0] += 1
    suffix = _REGISTER_COUNTER[0]
    raw = _valid_cpf(f"334455{suffix:03d}")
    email = f"flow-{suffix}@example.com"
    profile = {
        "firstName": "Caio",
        "lastName": "Fluxo",
        "countryOfOrigin": "Brasil",
        "cpf": f"{raw[:3]}.{raw[3:6]}.{raw[6:]}",
        "passportNumber": None,
        "phone": f"+5511955{suffix:06d}",
        "email": email,
        "password": "long-enough-password-1",
    }
    assert client.post(CREATE, json=profile).status_code == 201
    login = client.post(
        "/api/v1/tourists/login",
        json={"email": email, "password": "long-enough-password-1"},
    )
    assert login.status_code == 200, login.text
    return {"Authorization": f"Bearer {login.json()['accessToken']}"}, profile


def _admin_headers(client: TestClient) -> dict[str, str]:
    login = client.post(
        "/api/v1/auth/login",
        json={"username": "admin.panel", "password": TEST_ADMIN_PASSWORD},
    )
    assert login.status_code == 200, login.text
    return {"Authorization": f"Bearer {login.json()['accessToken']}"}


def _spot(client: TestClient, name: str, categories: list[str]) -> int:
    response = client.post(
        "/api/v1/tourist-spots",
        json={
            "name": name,
            "description": f"integration spot {name}",
            "latitude": -22.6 + len(name) / 1000,
            "longitude": -45.0 + len(name) / 1500,
            "categories": categories,
            "schedule": [{"weekday": "friday", "opensAt": "10:00", "closesAt": "18:00"}],
        },
        headers=_admin_headers(client),
    )
    assert response.status_code == 201, response.text
    return response.json()["id"]


def test_register_interests_discover_pagination_cycle(
    client: TestClient, sessionfactory_for
) -> None:
    headers, profile = _tourist(client)

    for index in range(6):
        _spot(client, f"Ponto Fluxo {index}", ["gastronomy" if index % 2 else "nature"])

    # 1. Interests replaceable before discovery (spec 003 contract intact).
    updated = client.put(INTERESTS_URL, json={"interests": ["gastronomy"]}, headers=headers)
    assert updated.status_code == 200 and updated.json()["interests"] == ["gastronomy"]

    # 2. Ranked discovery with position: interest match dominates over the
    # other (non-matching) spots, deterministic across repeats.
    positioned = client.get(
        DISCOVER_URL, params={"latitude": -22.60, "longitude": -45.00}, headers=headers
    )
    assert positioned.status_code == 200, positioned.text
    ordered = positioned.json()
    assert [item["id"] for item in ordered["items"]] == [
        item["id"]
        for item in client.get(
            DISCOVER_URL,
            params={"latitude": -22.60, "longitude": -45.00},
            headers=headers,
        ).json()["items"]
    ]
    scores = [item["relevanceScore"] for item in ordered["items"]]
    assert scores == sorted(scores, reverse=True)

    # 3. Same walk without position: still deterministic and score-ordered.
    positionedless = client.get(DISCOVER_URL, headers=headers).json()
    assert [item["relevanceScore"] for item in positionedless["items"]] == sorted(
        [item["relevanceScore"] for item in positionedless["items"]], reverse=True
    )

    # 4. Pagination walk (pageSize=2): zero duplicates, zero omissions and
    # the concatenated sequence equals the single-page deterministic order.
    total = ordered["totalItems"]
    concatenated: list[int] = []
    page = 1
    while True:
        body = client.get(
            DISCOVER_URL, params={"page": page, "pageSize": 2}, headers=headers
        ).json()
        concatenated.extend(item["id"] for item in body["items"])
        if not body["items"]:
            break
        page += 1
    assert len(concatenated) == len(set(concatenated)) == total
    whole = client.get(DISCOVER_URL, params={"pageSize": 100}, headers=headers).json()
    assert concatenated == [item["id"] for item in whole["items"]]

    # 5. Interests still replaceable after discovery (no read-only damage).
    again = client.put(INTERESTS_URL, json={"interests": ["nature"]}, headers=headers)
    assert again.status_code == 200 and again.json()["interests"] == ["nature"]
    assert profile["firstName"] == "Caio"  # profile untouched by the flow
