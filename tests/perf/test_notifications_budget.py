"""Performance: notification delivery budget (feature 015 — SC-005).

Delivery queries must answer under 2 s through the real HTTP endpoints on
the SC-005 reference dataset — 1,000 tourists with subscriptions and a
5,000-row notification history (100 distinct items) — with set-based SQL
(framing per the 013/014 budgets). Seeding is bulk and chunked (SQLite caps
bound variables per statement).
"""

import itertools
import time
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

TOURIST_COUNT = 1_000
ITEM_COUNT = 100
CATEGORY_POOL = ["gastronomy", "nature", "culture", "leisure", "art", "cinema"]

NOTIFICATIONS_BUDGET_SECONDS = 2.0
NOTIFICATIONS_URL = "/api/v1/notifications"
TOURISTS_URL = "/api/v1/tourists"
TOURIST_LOGIN = "/api/v1/tourists/login"

# Each seeded tourist receives 5 distinct items (index // TOURIST_COUNT) —
# within the unique tourist×item constraint, no collision.
_HISTOGRAM_PER_TOURIST = 5

_EMAIL_SEQUENCE = itertools.count(1)


def _register_and_login(client: TestClient) -> tuple[int, dict[str, str]]:
    sequence = next(_EMAIL_SEQUENCE)
    email = f"perf-notif-{sequence}@example.com"
    payload = {
        "firstName": "Perf",
        "lastName": "Notificacoes",
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


def _seed_dataset(sessionfactory_for) -> None:  # noqa: ANN001
    """1,000 tourists + subscriptions + the 5,000-row history (bulk)."""
    from passanorte_back.modules.notifications.repositories.notifications import (
        Notification,
    )
    from passanorte_back.modules.notifications.repositories.subscriptions import (
        NotificationSubscription,
    )
    from passanorte_back.modules.tourists.repositories.tourists import Tourist

    base = datetime(2026, 11, 6, 12, 0, tzinfo=UTC)
    with sessionfactory_for() as session:
        for index in range(1, TOURIST_COUNT + 1):
            session.add(
                Tourist(
                    first_name=f"Perf{index}",
                    last_name="Notificacoes",
                    country_of_origin="Brasil",
                    email_encrypted=f"enc{index}",
                    email_lookup=f"perf-notif-seed-{index:05d}",
                    phone_encrypted=f"tel{index}",
                    cpf_encrypted=None,
                    cpf_lookup=None,
                    passport_encrypted=None,
                    passport_lookup=None,
                    password_hash="synthetic-not-a-real-hash",
                )
            )
        session.flush()
        tourist_ids = [int(tourist.id) for tourist in session.query(Tourist)]
        session.add_all(
            NotificationSubscription(
                tourist_id=tourist_id,
                category_key=CATEGORY_POOL[tourist_id % len(CATEGORY_POOL)],
            )
            for tourist_id in tourist_ids
        )
        session.flush()

        notifications = [
            {
                "tourist_id": tourist_ids[index % TOURIST_COUNT],
                "item_type": "spot",
                "item_id": (index // TOURIST_COUNT) + 1,
                "title": f"Novo ponto turístico: Item {(index // TOURIST_COUNT) + 1:03d}",
                "description": "Budget dataset notification.",
                "created_at": base - timedelta(minutes=index % 60),
            }
            for index in range(TOURIST_COUNT * _HISTOGRAM_PER_TOURIST)
        ]
        chunk = 100
        for start in range(0, len(notifications), chunk):
            session.execute(
                Notification.__table__.insert().values(notifications[start : start + chunk])
            )
        session.commit()


@pytest.fixture(autouse=True)
def _dataset(seeded_admin: int, sessionfactory_for) -> None:  # noqa: ANN001
    _seed_dataset(sessionfactory_for)


def test_notifications_delivery_under_two_seconds(client: TestClient, seeded_admin: int) -> None:
    """SC-005: list (unread/history) and unread-count each under 2 s."""
    tourist_id, tourist = _register_and_login(client)
    _ = tourist_id  # the probe tourist rides the seeded volume

    probes = (
        ("list-unread", {}, {}),
        ("list-history", {}, {"onlyUnread": "false"}),
        ("unread-count", {"path": "/unread-count"}, {}),
    )
    for name, path_override, params in probes:
        url = NOTIFICATIONS_URL.rstrip("/") + path_override.get("path", "")
        started = time.perf_counter()
        response = client.get(url, headers=tourist, params=params or None)
        elapsed = time.perf_counter() - started
        assert response.status_code == 200, (name, response.text)
        assert elapsed < NOTIFICATIONS_BUDGET_SECONDS, (name, elapsed)
