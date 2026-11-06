"""Contract: chatbot endpoints (feature 016 — contracts/chatbot-api.md).

All endpoints ride the pre-mounted module router (tag ``Chatbot`` from the
central registry — spec 006) and are tourist-exclusive (``require_tourist``,
FR-001): 401 anonymous · 403 staff · 2xx tourist. Every response shape is
camelCase via ``ApiModel`` and every failure path is the unified
``ApiError`` payload (spec 005). Built per task: T009 (sessions, history,
strict border, OpenAPI tag).
"""

import itertools

from fastapi.testclient import TestClient

from tests.conftest import TEST_ADMIN_PASSWORD
from tests.helpers.chatbot_seeds import register_tourist

BASE_URL = "/api/v1/chatbot"

ADMIN_CREDENTIALS = {"username": "admin.panel", "password": TEST_ADMIN_PASSWORD}
EMPLOYEE_CREDENTIALS = {
    "username": "maria.panel",
    "password": "synthetic-employee-password-1",
}

_SEQUENCE = itertools.count(1)


def _admin_headers(client: TestClient) -> dict[str, str]:
    login = client.post("/api/v1/auth/login", json=ADMIN_CREDENTIALS)
    assert login.status_code == 200, login.text
    return {"Authorization": f"Bearer {login.json()['accessToken']}"}


def _employee_headers(client: TestClient) -> dict[str, str]:
    login = client.post("/api/v1/auth/login", json=EMPLOYEE_CREDENTIALS)
    assert login.status_code == 200, login.text
    return {"Authorization": f"Bearer {login.json()['accessToken']}"}


def test_create_session_contract(
    client: TestClient, seeded_admin: int, seeded_employee: int
) -> None:
    """POST /chatbot/sessions (FR-002): 401/403/201 + camelCase payload."""
    tourist = register_tourist(client, prefix="chat")[1]

    assert client.post(f"{BASE_URL}/sessions").status_code == 401
    assert client.post(f"{BASE_URL}/sessions", headers=_admin_headers(client)).status_code == 403
    assert client.post(f"{BASE_URL}/sessions", headers=_employee_headers(client)).status_code == 403

    first = client.post(f"{BASE_URL}/sessions", headers=tourist)
    assert first.status_code == 201, first.text
    body = first.json()
    assert set(body) == {"sessionId", "createdAt"}
    assert isinstance(body["sessionId"], int)
    assert "createdAt" in body

    second = client.post(f"{BASE_URL}/sessions", headers=tourist)
    assert second.json()["sessionId"] != body["sessionId"]


def test_list_sessions_contract(client: TestClient) -> None:
    """GET /chatbot/sessions lists ONLY the tourist's own sessions (FR-002)."""
    tourist = register_tourist(client, prefix="chat")[1]
    other = register_tourist(client, prefix="chat")[1]

    mine = client.post(f"{BASE_URL}/sessions", headers=tourist).json()
    theirs = client.post(f"{BASE_URL}/sessions", headers=other).json()

    listed = client.get(f"{BASE_URL}/sessions", headers=tourist)
    assert listed.status_code == 200, listed.text
    body = listed.json()
    assert set(body) == {"sessions"}
    ids = [session["sessionId"] for session in body["sessions"]]
    assert mine["sessionId"] in ids
    assert theirs["sessionId"] not in ids
    assert set(body["sessions"][0]) == {"sessionId", "createdAt", "lastMessageAt"}


def test_history_contract(client: TestClient) -> None:
    """GET /chatbot/sessions/{id}: own history 200; foreign/unknown 404
    (FR-001 — no enumeration via difference between 404 and 403)."""
    tourist = register_tourist(client, prefix="chat")[1]
    other = register_tourist(client, prefix="chat")[1]

    session_id = client.post(f"{BASE_URL}/sessions", headers=tourist).json()["sessionId"]

    empty = client.get(f"{BASE_URL}/sessions/{session_id}", headers=tourist)
    assert empty.status_code == 200, empty.text
    assert empty.json()["sessionId"] == session_id
    assert empty.json()["messages"] == []

    assert client.get(f"{BASE_URL}/sessions/{session_id}", headers=other).status_code == 404
    assert client.get(f"{BASE_URL}/sessions/999999", headers=tourist).status_code == 404
    assert client.get(f"{BASE_URL}/sessions/{session_id}").status_code == 401


def test_send_message_strict_border(client: TestClient) -> None:
    """POST .../messages: strict ApiModel border (extra/snake keys → 422)."""
    tourist = register_tourist(client, prefix="chat")[1]
    session_id = client.post(f"{BASE_URL}/sessions", headers=tourist).json()["sessionId"]
    url = f"{BASE_URL}/sessions/{session_id}/messages"

    assert client.post(url, json={}, headers=tourist).status_code == 422
    assert (
        client.post(url, json={"text": "oi", "unexpected": 1}, headers=tourist).status_code == 422
    )
    assert client.post(url, json={"some_text": "oi"}, headers=tourist).status_code == 422


def test_send_message_access_rules(client: TestClient, seeded_admin: int) -> None:
    """POST .../messages: 401 anon, 403 admin, 404 foreign/unknown session
    (FR-001); tourist passes access and reaches the service layer (the
    degraded provider flow answers 201 — no network in tests, FR-023)."""
    tourist = register_tourist(client, prefix="chat")[1]
    other = register_tourist(client, prefix="chat")[1]
    session_id = client.post(f"{BASE_URL}/sessions", headers=tourist).json()["sessionId"]
    url = f"{BASE_URL}/sessions/{session_id}/messages"

    assert client.post(url, json={"text": "oi"}).status_code == 401
    assert client.post(url, json={"text": "oi"}, headers=_admin_headers(client)).status_code == 403
    assert client.post(url, json={"text": "oi"}, headers=other).status_code == 404

    sent = client.post(url, json={"text": "oi"}, headers=tourist)
    assert sent.status_code == 201, sent.text
    body = sent.json()
    assert set(body) == {"userMessage", "assistantMessage"}
    assert body["userMessage"]["role"] == "user"
    assert body["userMessage"]["content"] == "oi"
    assert body["assistantMessage"]["role"] == "assistant"


def test_chatbot_tag_in_openapi(client: TestClient) -> None:
    """Every chatbot route carries exactly the central 'Chatbot' tag (spec 006)."""
    openapi = client.get("/openapi.json").json()
    tag_paths = [
        path
        for path, methods in openapi["paths"].items()
        for operation in methods.values()
        if "chatbot" in path and operation.get("tags") != ["Chatbot"]
    ]
    assert tag_paths == []
