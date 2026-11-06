"""Contract: notification endpoints (feature 015 — contracts/notifications.md).

All endpoints ride the pre-mounted module router (tag ``Notifications``
from the central registry — spec 006) and are tourist-exclusive
(``require_tourist``, RF03/FR-001): 401 anonymous · 403 staff · 200
tourist. Every response shape is camelCase via ``ApiModel`` and every
failure path is the unified ``ApiError`` payload (spec 005). Built per
user story: T009 US1 (subscriptions), T014 US2 (emission seam), T019 US3
(delivery), T024 (single-tag OpenAPI).
"""

import itertools

import pytest
from fastapi.testclient import TestClient

from tests.conftest import TEST_ADMIN_PASSWORD

BASE_URL = "/api/v1/notifications"
TOURISTS_URL = "/api/v1/tourists"
TOURIST_LOGIN = "/api/v1/tourists/login"

ADMIN_CREDENTIALS = {"username": "admin.panel", "password": TEST_ADMIN_PASSWORD}
EMPLOYEE_CREDENTIALS = {
    "username": "maria.panel",
    "password": "synthetic-employee-password-1",
}

_SEQUENCE = itertools.count(1)


def _tourist_headers(client: TestClient) -> tuple[int, dict[str, str]]:
    """Register a fresh tourist and authenticate; returns (id, bearer)."""
    sequence = next(_SEQUENCE)
    email = f"notif-tourist-{sequence}@example.com"
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
    login = client.post(TOURIST_LOGIN, json={"email": email, "password": payload["password"]})
    assert login.status_code == 200, login.text
    tourist_id = int(register.json()["id"])
    return tourist_id, {"Authorization": f"Bearer {login.json()['accessToken']}"}


def _admin_headers(client: TestClient) -> dict[str, str]:
    login = client.post("/api/v1/auth/login", json=ADMIN_CREDENTIALS)
    assert login.status_code == 200, login.text
    return {"Authorization": f"Bearer {login.json()['accessToken']}"}


def _employee_headers(client: TestClient) -> dict[str, str]:
    login = client.post("/api/v1/auth/login", json=EMPLOYEE_CREDENTIALS)
    assert login.status_code == 200, login.text
    return {"Authorization": f"Bearer {login.json()['accessToken']}"}


def test_subscriptions_contract(
    client: TestClient, seeded_admin: int, seeded_employee: int
) -> None:
    """GET/PUT/DELETE subscriptions (FR-004/FR-005/FR-006, Q1)."""
    _tourist_id, tourist = _tourist_headers(client)

    assert client.get(f"{BASE_URL}/subscriptions").status_code == 401

    # Empty selection initially, replace semantics and idempotent repeat.
    empty = client.get(f"{BASE_URL}/subscriptions", headers=tourist)
    assert empty.status_code == 200, empty.text
    assert empty.json() == {"categoryKeys": []}

    first = client.put(
        f"{BASE_URL}/subscriptions",
        headers=tourist,
        json={"categoryKeys": ["gastronomy", "nature", "nature"]},
    )
    assert first.status_code == 200, first.text
    assert first.json() == {"categoryKeys": ["gastronomy", "nature"]}

    # Replace whole selection (FR-004).
    second = client.put(
        f"{BASE_URL}/subscriptions",
        headers=tourist,
        json={"categoryKeys": ["culture"]},
    )
    assert second.json() == {"categoryKeys": ["culture"]}

    # Catalog-invalid key → 422 naming it (FR-005).
    invalid = client.put(
        f"{BASE_URL}/subscriptions",
        headers=tourist,
        json={"categoryKeys": ["teatro-inedito"]},
    )
    assert invalid.status_code == 422
    assert "teatro-inedito" in invalid.json()["message"]

    # Idempotent cancel (existing key 200; non-subscribed valid key 200).
    cancel = client.delete(f"{BASE_URL}/subscriptions/culture", headers=tourist)
    assert cancel.status_code == 200
    assert cancel.json() == {"categoryKeys": []}
    cancel_again = client.delete(f"{BASE_URL}/subscriptions/culture", headers=tourist)
    assert cancel_again.status_code == 200

    # Staff tokens → 403 (tourist-exclusive module, FR-001).
    staff = _employee_headers(client)
    assert client.get(f"{BASE_URL}/subscriptions", headers=staff).status_code == 403
    assert (
        client.put(
            f"{BASE_URL}/subscriptions", headers=staff, json={"categoryKeys": []}
        ).status_code
        == 403
    )


def test_delivery_contract(
    client: TestClient, seeded_admin: int, seeded_employee: int, sessionfactory_for
) -> None:
    """GET list + unread-count + read marking (FR-012/FR-013/FR-013a)."""
    from datetime import UTC, datetime

    from passanorte_back.modules.notifications.repositories.notifications import (
        insert_notifications,
    )

    tourist_id, tourist = _tourist_headers(client)
    base = datetime(2026, 11, 5, 12, 0, tzinfo=UTC)
    with sessionfactory_for() as session:
        insert_notifications(
            session,
            rows=[
                {
                    "tourist_id": tourist_id,
                    "item_type": "event",
                    "item_id": 3,
                    "title": "Novo evento: Festival",
                    "description": "Peixes no centro.",
                    "created_at": base,
                },
                {
                    "tourist_id": tourist_id,
                    "item_type": "spot",
                    "item_id": 2,
                    "title": "Novo ponto turístico: Mirante",
                    "description": "Vista do vale.",
                    "created_at": base,
                },
            ],
        )
        # A foreign tourist's notification must never leak.
        insert_notifications(
            session,
            rows=[
                {
                    "tourist_id": tourist_id + 1000,
                    "item_type": "spot",
                    "item_id": 9,
                    "title": "Novo ponto turístico: Alheio",
                    "description": "Outro turista.",
                }
            ],
        )
        session.commit()

    listing = client.get(BASE_URL, headers=tourist)
    assert listing.status_code == 200, listing.text
    body = listing.json()
    assert set(body) == {"unreadCount", "items"}
    assert body["unreadCount"] == 2
    assert [item["itemType"] for item in body["items"]] == ["spot", "event"]
    item = body["items"][0]
    assert set(item) >= {"id", "itemType", "itemId", "title", "description", "createdAt", "readAt"}

    # explicit filter false → full history (same two items).
    history = client.get(BASE_URL, headers=tourist, params={"onlyUnread": "false"})
    assert history.status_code == 200
    assert len(history.json()["items"]) == 2

    count = client.get(f"{BASE_URL}/unread-count", headers=tourist)
    assert count.status_code == 200
    assert count.json() == {"unreadCount": 2}

    # Mark one as read → unreadCount 1; idempotent mark keeps first readAt.
    notification_id = client.get(BASE_URL, headers=tourist).json()["items"][0]["id"]
    marked = client.post(f"{BASE_URL}/{notification_id}/read", headers=tourist)
    assert marked.status_code == 200
    first_read_at = marked.json()["readAt"]
    assert first_read_at is not None
    remarried = client.post(f"{BASE_URL}/{notification_id}/read", headers=tourist)
    assert remarried.json()["readAt"] == first_read_at
    assert client.get(f"{BASE_URL}/unread-count", headers=tourist).json() == {"unreadCount": 1}

    # Foreign notification id → 404 (isolation).
    foreign = client.post(f"{BASE_URL}/999999/read", headers=tourist)
    assert foreign.status_code == 404
    assert foreign.json()["errorCode"] == "resource_not_found"

    # Read all → zero (FR-013).
    read_all = client.post(f"{BASE_URL}/read-all", headers=tourist)
    assert read_all.status_code == 200
    assert read_all.json() == {"unreadCount": 0}

    # Empty tourist → zeros without error (US3/AC5).
    _other_id, other = _tourist_headers(client)
    fresh = client.get(BASE_URL, headers=other)
    assert fresh.json() == {"unreadCount": 0, "items": []}

    # Staff tokens → 403.
    staff = _employee_headers(client)
    assert client.get(BASE_URL, headers=staff).status_code == 403
    assert client.get(f"{BASE_URL}/unread-count", headers=staff).status_code == 403


def test_emission_seam_contract(sessionfactory_for, client, seeded_admin) -> None:
    """Module-to-module seam shape (FR-008/FR-009/FR-010, research R3)."""
    from passanorte_back.modules.notifications.repositories.subscriptions import (
        add_subscription,
    )
    from passanorte_back.modules.notifications.services.emission import (
        create_interest_notification,
    )

    tourist_id, _tourist = _tourist_headers(client)
    with sessionfactory_for() as session:
        add_subscription(session, tourist_id=tourist_id, category_key="gastronomy")
        session.commit()

    with sessionfactory_for() as session:
        first = create_interest_notification(
            session,
            item_type="event",
            item_id=1,
            item_name="Festival",
            item_description="Festival de peixes.",
            category_keys=["gastronomy"],
        )
        assert first == 1  # notified count (FR-008 seam return)
        re_emit = create_interest_notification(
            session,
            item_type="event",
            item_id=1,
            item_name="Festival",
            item_description="Festival de peixes.",
            category_keys=["gastronomy"],
        )
        assert re_emit == 0  # dedupe: tourist×item already received (FR-009)
        zero_match = create_interest_notification(
            session,
            item_type="event",
            item_id=2,
            item_name="Trilha",
            item_description="Trilha noturna.",
            category_keys=["nature"],
        )
        assert zero_match == 0  # no subscriptions for the key (US2/AC5)
        session.commit()

    from fastapi import HTTPException

    with sessionfactory_for() as session:
        with pytest.raises(HTTPException) as error:
            create_interest_notification(
                session,
                item_type="prize",
                item_id=1,
                item_name="X",
                item_description="X.",
                category_keys=["gastronomy"],
            )
        assert error.value.status_code == 422


def test_openapi_single_notifications_tag(client: TestClient, seeded_admin: int) -> None:
    """FR-002: every notifications path listed under the one Notifications tag."""
    openapi = client.get("/openapi.json").json()
    paths = [path for path in openapi["paths"] if path.startswith("/api/v1/notifications")]
    # 7 operations across 6 paths (PUT+GET share /subscriptions).
    operations = sum(len(openapi["paths"][path]) for path in paths)
    assert len(paths) == 6, paths
    assert operations == 7, operations
    for path in paths:
        for method in openapi["paths"][path]:
            assert openapi["paths"][path][method]["tags"] == ["Notifications"], (path, method)
