"""Integration: degraded chatbot behavior (feature 016 — T029 US4, FR-018,
SC-005).

All provider-side failures — absent settings, network/HTTP error, deadline
exceeded, malformed/unanchorable output — must answer 201 with a
localized unavailability message and NO itinerary, never an opaque 5xx.
The user message and the prior history stay intact in every scenario.
"""

import pytest
from fastapi.testclient import TestClient

from passanorte_back.modules.chatbot.services.chat import default_provider
from tests.helpers.chatbot_seeds import create_always_open_spot, register_tourist
from tests.helpers.fake_llm import (
    MalformedOutputFake,
    NeverCalledProvider,
    ProviderErrorFake,
    TimeoutFake,
)

BASE_URL = "/api/v1/chatbot"


def _tourist(client: TestClient) -> dict[str, str]:
    return register_tourist(client, prefix="chat-degraded")[1]


def _degraded_client(client: TestClient, provider) -> TestClient:
    client.app.dependency_overrides[default_provider] = lambda: provider  # type: ignore[attr-defined]
    return client


@pytest.fixture
def one_spot(sessionfactory_for) -> int:
    """One always-open spot: with candidates present, provider failures
    reach the degraded path (an empty base answers 'no compatible options'
    before any provider call)."""
    with sessionfactory_for() as session:
        spot_id = create_always_open_spot(
            session,
            name="Mirante do Vale",
            description="Mirante com vista para o vale, natureza.",
        )
        session.commit()
        return spot_id


def _create_session(client: TestClient, tourist: dict[str, str]) -> int:
    return client.post(f"{BASE_URL}/sessions", headers=tourist).json()["sessionId"]


def _send_history(
    client: TestClient, tourist: dict[str, str], session_id: int, text: str = "roteiro pra hoje"
) -> dict:
    sent = client.post(
        f"{BASE_URL}/sessions/{session_id}/messages", json={"text": text}, headers=tourist
    )
    assert sent.status_code == 201, sent.text
    return client.get(f"{BASE_URL}/sessions/{session_id}", headers=tourist).json()


def _assert_degraded(history: dict) -> None:
    """Shared expectation: assistant answered conversationally, no
    itinerary, session intact (SC-005)."""
    roles = [message["role"] for message in history["messages"]]
    assert roles == ["user", "assistant"]
    assistant = history["messages"][1]
    assert assistant["itinerary"] is None
    assert assistant["content"].strip() != ""
    assert "indispon" in assistant["content"].lower()


def test_absent_api_key_is_degraded_not_5xx(client: TestClient, monkeypatch, one_spot: int) -> None:
    """Scenario 1: no CHATBOT_LLM_* configured — the default provider falls
    back to the unavailable provider (FR-017: app boots; FR-018)."""
    for key in ("CHATBOT_LLM_API_KEY", "CHATBOT_LLM_BASE_URL", "CHATBOT_LLM_MODEL"):
        monkeypatch.delenv(key, raising=False)
    tourist = _tourist(client)
    history = _send_history(client, tourist, _create_session(client, tourist))
    _assert_degraded(history)


def test_provider_error_is_degraded_not_5xx(client: TestClient, one_spot: int) -> None:
    """Scenario 2: network/HTTP failure (ProviderError)."""
    tourist = _tourist(client)
    chat_client = _degraded_client(client, ProviderErrorFake())
    history = _send_history(chat_client, tourist, _create_session(chat_client, tourist))
    _assert_degraded(history)


def test_provider_timeout_is_degraded_not_5xx(client: TestClient, one_spot: int) -> None:
    """Scenario 3: deadline exceeded (~30s budget, FR-018/SC-005)."""
    tourist = _tourist(client)
    chat_client = _degraded_client(client, TimeoutFake(base=NeverCalledProvider()))
    history = _send_history(chat_client, tourist, _create_session(chat_client, tourist))
    _assert_degraded(history)


@pytest.mark.parametrize("mode", ["not-json", "unknown-ids", "empty"])
def test_malformed_output_is_degraded_not_5xx(client: TestClient, one_spot: int, mode: str) -> None:
    """Scenario 4: non-JSON / unknown ids / empty selection — the module
    communicates instead of presenting broken items (FR-021; edge case).
    'unknown-ids'/'empty' keep the narration (no itinerary), consistent
    with the anchored-selection edge case."""
    tourist = _tourist(client)
    chat_client = _degraded_client(client, MalformedOutputFake(mode=mode))
    history = _send_history(chat_client, tourist, _create_session(chat_client, tourist))
    roles = [message["role"] for message in history["messages"]]
    assert roles == ["user", "assistant"]
    assistant = history["messages"][1]
    assert assistant["itinerary"] is None
    assert assistant["content"].strip() != ""


def test_history_survives_degraded_exchange(client: TestClient, one_spot: int) -> None:
    """Story 4 acceptance 2: sessions/messages prior to the failure remain
    available and untouched."""
    tourist = _tourist(client)
    chat_client = _degraded_client(client, ProviderErrorFake())
    session_id = _create_session(chat_client, tourist)
    first_history = _send_history(chat_client, tourist, session_id)
    second_history = _send_history(chat_client, tourist, session_id, "segunda mensagem")
    assert len(first_history["messages"]) == 2
    assert len(second_history["messages"]) == 4  # prior pair + new pair
