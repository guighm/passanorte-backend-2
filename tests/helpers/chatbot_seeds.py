"""Shared chatbot seeding helpers (feature 016 — T033).

One place for the seeds the chatbot tests share: an always-open spot via
the owner-domain seam (``tourist_spots`` service), an event of a target day
and tourist registration/auth helpers. Patterns follow the project test
harness memory: sessionfactory seeds commit explicitly.
"""

import itertools
from datetime import datetime
from zoneinfo import ZoneInfo

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from passanorte_back.modules.tourist_spots import schemas as spot_schemas
from passanorte_back.modules.tourist_spots.services.tourist_spots import create_spot

CITY_TZ = ZoneInfo("America/Sao_Paulo")

EVERY_DAY = [
    {"weekday": day, "opensAt": "00:00", "closesAt": "23:59"}
    for day in ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday")
]

TOURISTS_URL = "/api/v1/tourists"
TOURIST_LOGIN = "/api/v1/tourists/login"

_SEQUENCE = itertools.count(1)


def create_always_open_spot(
    session: Session,
    *,
    name: str,
    description: str,
    latitude: float = -22.73,
    longitude: float = -45.01,
    categories: list[str] | None = None,
) -> int:
    """One spot open every day (chatbot tests never argue about weekdays
    unless they pass a custom schedule)."""
    payload = spot_schemas.SpotCreateRequest.from_internal(
        name=name,
        description=description,
        latitude=latitude,
        longitude=longitude,
        categories=categories or ["nature"],
        schedule=EVERY_DAY,
    )
    return create_spot(session, actor="admin.panel", payload=payload).id


def create_target_day_event(
    session: Session, *, spot_id: int, day: datetime, price_cents: int = 2500
) -> int:
    """One event of the target day via the events owner repository."""
    from passanorte_back.modules.events.repositories.events import add_event

    event = add_event(
        session,
        spot_id=spot_id,
        occurrence_date=day.date(),
        description="Festival de inverno no local",
        ticket_price_cents=price_cents,
    )
    session.flush()
    return event.id


def register_tourist(client: TestClient, *, prefix: str) -> tuple[int, dict[str, str]]:
    """Register + login a fresh tourist; returns (id, bearer headers)."""
    sequence = next(_SEQUENCE)
    email = f"{prefix}-tourist-{sequence}@example.com"
    payload = {
        "firstName": "Tur",
        "lastName": "Teste",
        "countryOfOrigin": "Brasil",
        "cpf": None,
        "passportNumber": f"T{sequence % 100:02d}{sequence:06d}",
        "phone": "+5511900000000",
        "email": email,
        "password": "long-enough-password-1",
    }
    register = client.post(TOURISTS_URL, json=payload)
    assert register.status_code == 201, register.text
    login = client.post(TOURIST_LOGIN, json={"email": email, "password": payload["password"]})
    assert login.status_code == 200, login.text
    return int(register.json()["id"]), {"Authorization": f"Bearer {login.json()['accessToken']}"}


def today_in_city_tz() -> datetime:
    """The conversation moment in the configured city timezone (spec
    assumption: target time defaults to the conversation moment)."""
    return datetime.now(CITY_TZ)
