"""Integration: chatbot end-to-end flow (feature 016 — T010 US1).

Seeded base (spots/events via the owner repositories), tourist registered
through the public API, provider replaced by ``FakeLlmProvider`` (FR-023 —
no real network anywhere): the full journey create-session → send message
→ structured itinerary anchored to the seeded base → persisted history
(FR-004/FR-006/FR-013/FR-022).
"""

import pytest
from fastapi.testclient import TestClient

from passanorte_back.modules.chatbot.services.chat import default_provider
from tests.helpers.chatbot_seeds import (
    create_always_open_spot,
    create_target_day_event,
    register_tourist,
    today_in_city_tz,
)
from tests.helpers.fake_llm import FakeLlmProvider

BASE_URL = "/api/v1/chatbot"


def _tourist(client: TestClient) -> dict[str, str]:
    return register_tourist(client, prefix="chat-flow")[1]


def _today_local() -> str:
    """Today's date in the configured city timezone (target day — FR-024)."""
    return today_in_city_tz().date().isoformat()


@pytest.fixture
def seeded_catalog(sessionfactory_for) -> dict[str, int]:
    """Two always-open spots and one event of the target day (spec: FR-009/
    FR-024 deterministic base for the anchored itinerary)."""
    today = today_in_city_tz()
    with sessionfactory_for() as session:
        waterfall = create_always_open_spot(
            session,
            name="Cachoeira Édem",
            description="Cachoeira com piscina natural e trilha leve de natureza.",
            latitude=-22.7266,
            longitude=-45.0123,
            categories=["nature"],
        )
        museum = create_always_open_spot(
            session,
            name="Museu Ferroviário",
            description="Museu com peças históricas da ferrovia e exposição de cultura.",
            latitude=-22.7370,
            longitude=-45.0320,
            categories=["culture"],
        )
        session.commit()
    with sessionfactory_for() as session:
        event_id = create_target_day_event(session, spot_id=museum, day=today, price_cents=2500)
        session.commit()
    return {"waterfall": waterfall, "museum": museum, "event": event_id}


@pytest.fixture
def chat_provider(sessionfactory_for) -> FakeLlmProvider:
    provider = FakeLlmProvider(text="Ótimo roteiro para hoje!")
    provider.set_selection(spot_ids=[1], event_ids=[])
    return provider


@pytest.fixture
def chat_client(client: TestClient, chat_provider: FakeLlmProvider) -> TestClient:
    """App client with the LLM provider replaced by the canned fake."""
    client.app.dependency_overrides[default_provider] = lambda: chat_provider  # type: ignore[attr-defined]
    return client


def test_full_chat_flow(chat_client, chat_provider, sessionfactory_for, seeded_catalog) -> None:
    """US1 end-to-end: create session → send message → anchored itinerary →
    persisted history (FR-004, FR-006, FR-013)."""
    tourist = _tourist(chat_client)
    assert chat_provider.spot_ids == [1]

    session_id = chat_client.post(f"{BASE_URL}/sessions", headers=tourist).json()["sessionId"]

    chat_provider.set_selection(
        spot_ids=[seeded_catalog["waterfall"]], event_ids=[seeded_catalog["event"]]
    )

    sent = chat_client.post(
        f"{BASE_URL}/sessions/{session_id}/messages",
        json={"text": "Roteiro pra hoje, cachoeiras e o festival"},
        headers=tourist,
    )
    assert sent.status_code == 201, sent.text
    body = sent.json()["assistantMessage"]

    itinerary = body["itinerary"]
    assert itinerary is not None, "assistant message must embed the itinerary (FR-005)"
    assert itinerary["totalCostCents"] == 2500  # FR-010: event ticket price only
    ref_ids = {(item["kind"], item["refId"]) for item in itinerary["items"]}
    assert ref_ids == {
        ("spot", seeded_catalog["waterfall"]),
        ("event", seeded_catalog["event"]),
    }  # FR-006: only registered items
    for item in itinerary["items"]:
        expected_keys = {"kind", "refId", "displayName", "suggestedAt", "ticketCostCents"}
        assert set(item) == expected_keys  # FR-025 snapshot shape (SC-006)
    assert itinerary["targetDate"] == _today_local()

    history = chat_client.get(f"{BASE_URL}/sessions/{session_id}", headers=tourist).json()
    roles = [message["role"] for message in history["messages"]]
    assert roles == ["user", "assistant"]
    assert history["messages"][1]["itinerary"] is not None
    assert history["messages"][0]["itinerary"] is None


def test_history_persists_between_calls(
    chat_client, chat_provider, sessionfactory_for, seeded_catalog
) -> None:
    """FR-022/SC-004: messages persist across separate HTTP requests (fresh
    session read after each send)."""
    tourist = _tourist(chat_client)
    session_id = chat_client.post(f"{BASE_URL}/sessions", headers=tourist).json()["sessionId"]

    chat_provider.set_selection(spot_ids=[seeded_catalog["museum"]])
    chat_client.post(
        f"{BASE_URL}/sessions/{session_id}/messages",
        json={"text": "quero museu"},
        headers=tourist,
    )
    chat_provider.set_selection(spot_ids=[seeded_catalog["waterfall"]])
    chat_client.post(
        f"{BASE_URL}/sessions/{session_id}/messages",
        json={"text": "achou caro, prefiro a cachoeira"},
        headers=tourist,
    )

    history = chat_client.get(f"{BASE_URL}/sessions/{session_id}", headers=tourist).json()
    assert [message["role"] for message in history["messages"]] == [
        "user",
        "assistant",
        "user",
        "assistant",
    ]
    assert history["messages"][2]["content"] == "achou caro, prefiro a cachoeira"


def test_assistant_context_comes_only_from_seeded_base(
    chat_client, chat_provider, sessionfactory_for, seeded_catalog
) -> None:
    """FR-007: the candidates handed to the provider exist in the seeded
    base — nothing invented (fake records the prompt it received)."""
    tourist = _tourist(chat_client)
    session_id = chat_client.post(f"{BASE_URL}/sessions", headers=tourist).json()["sessionId"]

    chat_provider.set_selection(spot_ids=[seeded_catalog["waterfall"]])
    chat_client.post(
        f"{BASE_URL}/sessions/{session_id}/messages",
        json={"text": "cachoeira"},
        headers=tourist,
    )

    prompt = chat_provider.last_prompt
    assert prompt is not None
    candidate_refs = {(candidate.kind, candidate.ref_id) for candidate in prompt.candidates}
    assert ("spot", seeded_catalog["waterfall"]) in candidate_refs
    assert ("spot", seeded_catalog["museum"]) in candidate_refs
    assert ("event", seeded_catalog["event"]) in candidate_refs


def test_second_message_uses_session_history(
    chat_client, chat_provider, sessionfactory_for, seeded_catalog
) -> None:
    """US3/FR-013: the second send carries the session's prior turns in the
    provider prompt (FR-022 bounded context, no cross-session leakage);
    history read afterwards holds all four messages."""
    tourist = _tourist(chat_client)
    session_id = chat_client.post(f"{BASE_URL}/sessions", headers=tourist).json()["sessionId"]

    chat_provider.set_selection(spot_ids=[seeded_catalog["museum"]])
    chat_client.post(
        f"{BASE_URL}/sessions/{session_id}/messages",
        json={"text": "quero museu hoje"},
        headers=tourist,
    )
    first_prompt_after = len(chat_provider.prompts)

    chat_provider.set_selection(spot_ids=[seeded_catalog["waterfall"]])
    chat_client.post(
        f"{BASE_URL}/sessions/{session_id}/messages",
        json={"text": "troque por algo mais barato"},
        headers=tourist,
    )

    second_prompt = chat_provider.prompts[first_prompt_after]
    history_texts = [turn.content for turn in second_prompt.history]
    assert "quero museu hoje" in history_texts
    assert "troque por algo mais barato" not in history_texts  # current query is separate
    assert all("outra-conversa" not in turn.content for turn in second_prompt.history)

    history = chat_client.get(f"{BASE_URL}/sessions/{session_id}", headers=tourist).json()
    assert [message["role"] for message in history["messages"]] == [
        "user",
        "assistant",
        "user",
        "assistant",
    ]
