"""Integration: tourist access recording + counter (feature 014, FR-007/RF07).

Real HTTP requests through the app: every tourist-authenticated request
(including public endpoints consulted with a tourist token) appends
exactly one ``access_events`` row; staff/anonymous requests append none;
a recording failure never fails the tourist request (FR-022 best-effort).
"""

import itertools
from datetime import datetime
from typing import Any

from fastapi.testclient import TestClient

from tests.conftest import TEST_ADMIN_PASSWORD

BASE_URL = "/api/v1/dashboard"
AUTH_LOGIN = "/api/v1/auth/login"
TOURISTS_URL = "/api/v1/tourists"
TOURIST_LOGIN = "/api/v1/tourists/login"

ADMIN_CREDENTIALS = {"username": "admin.panel", "password": TEST_ADMIN_PASSWORD}

_SPOT_SEQUENCE = itertools.count(1)


def _admin_headers(client: TestClient) -> dict[str, str]:
    login = client.post(AUTH_LOGIN, json=ADMIN_CREDENTIALS)
    assert login.status_code == 200, login.text
    return {"Authorization": f"Bearer {login.json()['accessToken']}"}


def _register_and_login(client: TestClient, *, country: str = "Brasil") -> dict[str, str]:
    sequence = next(_SPOT_SEQUENCE)
    email = f"access-tourist-{sequence}@example.com"
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
    register = client.post(TOURISTS_URL, json=payload)
    assert register.status_code == 201, register.text
    login = client.post(TOURIST_LOGIN, json={"email": email, "password": payload["password"]})
    assert login.status_code == 200, login.text
    return {"Authorization": f"Bearer {login.json()['accessToken']}", "email": email}


def _make_spot(sessionfactory_for, *, name: str) -> int:  # noqa: ANN001
    from passanorte_back.modules.tourist_spots.repositories.tourist_spots import add_spot

    with sessionfactory_for() as session:
        spot = add_spot(
            session,
            name=name,
            description="Spot for the access-flow test.",
            latitude=-22.40,
            longitude=-45.00,
        )
        session.commit()
        return int(spot.id)


def _use_test_session_for_recording(monkeypatch, sessionfactory_for) -> list[tuple[int, datetime]]:  # noqa: ANN001
    """Point the recording module at the isolated engine; return a reader
    that lists the recorded (tourist_id, day) rows so far."""
    import contextlib

    from passanorte_back.modules.dashboard.services import access_recording

    @contextlib.contextmanager
    def _session():
        with sessionfactory_for() as session:
            yield session

    monkeypatch.setattr(access_recording, "_open_session", _session)

    def _recorded() -> list[tuple[int, datetime]]:
        from sqlalchemy import select

        from passanorte_back.modules.dashboard.repositories.access_events import (
            AccessEvent,
        )

        out: list[tuple[int, datetime]] = []
        with sessionfactory_for() as reader:
            for event in reader.execute(select(AccessEvent)).scalars():
                out.append((event.tourist_id, event.occurred_at))
        return out

    return _recorded  # reader over the test ledger


def test_tourist_requests_are_recorded(
    client: TestClient, seeded_admin: int, seeded_employee: int, sessionfactory_for, monkeypatch
) -> None:
    """FR-008: tourist-authenticated requests (app PASSAPORTE) record one
    event each, including public endpoints consulted authenticated."""
    reader = _use_test_session_for_recording(monkeypatch, sessionfactory_for)
    tourist = _register_and_login(client)  # tourist token (registration is anonymous)
    spot_id = _make_spot(sessionfactory_for, name="Access Flow Spot")

    # Tourist-exclusive route (interests read).
    interests = client.get(f"{TOURISTS_URL}/me/interests", headers=tourist)
    assert interests.status_code == 200, interests.text
    # Public endpoint consulted WITH the tourist token (Q4 — still counts).
    detail = client.get(f"/api/v1/tourist-spots/{spot_id}", headers=tourist)
    assert detail.status_code == 200, detail.text
    # Anonymous public request does NOT record.
    anonymous = client.get(f"/api/v1/tourist-spots/{spot_id}")
    assert anonymous.status_code == 200, anonymous.text
    # Employee-authenticated request does NOT record.
    employee = client.post(
        AUTH_LOGIN,
        json={
            "username": "maria.panel",
            "password": "synthetic-employee-password-1",
        },
    )
    assert employee.status_code == 200

    captured = reader()
    recorded_tourists = [tourist_id for tourist_id, _moment in captured]
    assert recorded_tourists == [1, 1]  # exactly the two tourist requests recorded


def test_recording_failure_never_fails_the_tourist(
    client: TestClient, seeded_admin: int, sessionfactory_for, monkeypatch, caplog
) -> None:
    """FR-022: best-effort — a failing insert yields a structured error log
    and the tourist request still succeeds."""
    import logging

    from passanorte_back.modules.dashboard.services import access_recording

    def _broken_session():  # noqa: ANN202
        raise RuntimeError("simulated ledger outage")

    monkeypatch.setattr(access_recording, "_open_session", _broken_session)
    tourist = _register_and_login(client)
    with caplog.at_level(logging.ERROR, logger="passanorte.dashboard"):
        response = client.get(f"{TOURISTS_URL}/me/interests", headers=tourist)
    assert response.status_code == 200, response.text
    assert any("access event" in record.getMessage().lower() for record in caplog.records)
