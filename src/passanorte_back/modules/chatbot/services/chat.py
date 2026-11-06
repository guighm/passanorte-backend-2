"""Chat flows: sessions, messages, itinerary generation, degraded mode
(feature 016 — research R3/R4).

Orchestration only: persistence queries come from ``repositories.chat``,
candidates from ``services.retrieval``, structure from
``services.planning``, constraints from ``services.validator``; the
generative provider is reached ONLY through the injectable ``LlmProvider``
seam (``services.providers``). Every provider-side failure path becomes a
localized unavailability assistant message — no opaque errors (FR-018).
"""

from datetime import datetime
from typing import Final
from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session

from passanorte_back.core.config import Settings, get_settings
from passanorte_back.modules.chatbot.repositories import chat as chat_repo
from passanorte_back.modules.chatbot.repositories.chat import ChatMessage, ChatSession
from passanorte_back.modules.chatbot.services import retrieval
from passanorte_back.modules.chatbot.services.planning import (
    ItineraryItem,
    anchor_selection,
    build_itinerary,
)
from passanorte_back.modules.chatbot.services.providers import (
    HistoryTurn,
    LlmProvider,
    PlannerCandidate,
    PlannerPrompt,
    PlannerReply,
    ProviderError,
    ProviderMalformedOutput,
    ProviderTimeout,
    ProviderUnavailable,
)
from passanorte_back.modules.chatbot.services.validator import validate_plan

# US3 bounded context window: how many prior turns ride along (bounded
# history — no cross-session leakage).
HISTORY_TURNS: Final[int] = 8

# Localized fallback texts (i18n-ready, FR-019): keys are the configured
# languages; Portuguese is the canonical default (assumption).
UNAVAILABLE_TEXT: Final[dict[str, str]] = {
    "pt-BR": "Desculpe, não consigo gerar roteiros agora — o assistente de "
    "IA está temporariamente indisponível. Tente novamente em instantes; "
    "suas conversas anteriores continuam salvas.",
}
NO_CANDIDATES_TEXT: Final[dict[str, str]] = {
    "pt-BR": "Não encontrei pontos turísticos ou eventos compatíveis com o "
    "que você pediu no catálogo cadastrado. Tente um pedido diferente, ou "
    "confira os pontos e eventos disponíveis no Passaporte.",
}


class _UnavailableProvider:
    """Fallback provider for absent settings (FR-017): every call reports
    degraded mode instead of failing the app boot."""

    def plan_itinerary(self, prompt: PlannerPrompt) -> PlannerReply:
        raise ProviderUnavailable("chatbot provider not configured")


def default_provider() -> LlmProvider:
    """Resolve the provider from settings; incomplete settings → degraded
    fallback (usable directly and as a FastAPI dependency — tests override
    it via ``app.dependency_overrides``)."""
    try:
        provider: LlmProvider = _build_provider(get_settings())
        return provider
    except ProviderUnavailable:
        return _UnavailableProvider()  # type: ignore[return-value]


def _build_provider(settings: Settings) -> LlmProvider:
    """Import inside the function so a provider factory stays swappable."""
    from passanorte_back.modules.chatbot.services.providers import HttpLlmProvider

    return HttpLlmProvider.from_settings(settings)


def _city_now(settings: Settings) -> datetime:
    """The conversation moment in the configured city timezone (assumption:
    target time defaults to the conversation moment)."""
    return datetime.now(ZoneInfo(settings.resolved_city_timezone()))


def _first_language(settings: Settings) -> str:
    languages = settings.resolved_languages()
    return languages[0] if languages else "pt-BR"


def _localize(texts: dict[str, str], language: str) -> str:
    """Pick the localized text (FR-019): exact match, then language base,
    then Portuguese."""
    if language in texts:
        return texts[language]
    base = language.split("-")[0].lower()
    for candidate_language in texts:
        if candidate_language.split("-")[0].lower() == base:
            return texts[candidate_language]
    return texts["pt-BR"]


# --- Session flows (FR-001/FR-002) ------------------------------------------


def create_chat_session(session: Session, *, tourist_id: int) -> ChatSession:
    return chat_repo.create_session(session, tourist_id=tourist_id)


def list_chat_sessions(
    session: Session, *, tourist_id: int
) -> list[tuple[ChatSession, datetime | None]]:
    sessions = chat_repo.list_sessions_for_tourist(session, tourist_id=tourist_id)
    return [(item, chat_repo.get_last_message_at(session, session_id=item.id)) for item in sessions]


def get_history(session: Session, *, session_id: int, tourist_id: int) -> list[ChatMessage] | None:
    """Full message list of an OWNED session; ``None`` = missing/foreign
    (404 at the HTTP border)."""
    item = chat_repo.get_owned_session(session, session_id=session_id, tourist_id=tourist_id)
    if item is None:
        return None
    return chat_repo.list_messages(session, session_id=item.id)


# --- Message flow (FR-003/FR-013) -------------------------------------------


def _planner_candidates(candidates: list, settings: Settings) -> list[PlannerCandidate]:
    category_labels = {
        category.get("key", ""): category.get("label", "")
        for category in settings.resolved_interest_categories()
    }
    rendered: list[PlannerCandidate] = []
    for candidate in candidates:
        labeled_keys = []
        for key in candidate.category_keys:
            label = category_labels.get(key)
            labeled_keys.append(f"{key} ({label})" if label else key)
        rendered.append(
            PlannerCandidate(
                kind=candidate.kind,
                ref_id=candidate.ref_id,
                name=candidate.name,
                description=candidate.description,
                category_keys=labeled_keys,
                ticket_price_cents=candidate.ticket_price_cents,
                opens_at=(
                    candidate.opens_at.isoformat(timespec="minutes") if candidate.opens_at else None
                ),
                closes_at=(
                    candidate.closes_at.isoformat(timespec="minutes")
                    if candidate.closes_at
                    else None
                ),
            )
        )
    return rendered


def _history_turns(
    session: Session, *, session_id: int, exclude_id: int | None
) -> list[HistoryTurn]:
    """The bounded prior exchange of THIS session (US3 — FR-013)."""
    messages = chat_repo.list_messages(session, session_id=session_id)
    return [
        HistoryTurn(role=message.role, content=message.content)
        for message in messages[-HISTORY_TURNS:]
        if message.id != exclude_id
    ]


def send_message(
    session: Session,
    *,
    session_id: int,
    tourist_id: int,
    text: str,
    provider: LlmProvider | None = None,
) -> tuple[ChatMessage, ChatMessage] | None:
    """Send one tourist message and produce the assistant reply.

    Returns ``(user_message, assistant_message)`` or ``None`` when the
    session is missing/foreign (404 at the HTTP border). Degraded mode
    (research R4): provider failure/timeout/unavailable/malformed output →
    unavailability assistant message with no itinerary; the user message
    is always persisted (Story 4).
    """
    chat_session = chat_repo.get_owned_session(
        session, session_id=session_id, tourist_id=tourist_id
    )
    if chat_session is None:
        return None

    user_message = chat_repo.add_message(session, session_id=session_id, role="user", content=text)

    settings = get_settings()
    now_city = _city_now(settings)
    target_day = now_city.date()
    language = _first_language(settings)

    candidates = retrieval.retrieve_candidates(
        session, tourist_id=tourist_id, at=now_city, target_day=target_day, query=text
    )
    if not candidates:
        assistant_message = chat_repo.add_message(
            session,
            session_id=session_id,
            role="assistant",
            content=_localize(NO_CANDIDATES_TEXT, language),
        )
        return user_message, assistant_message

    prompt = PlannerPrompt(
        query=text,
        city=settings.resolved_city(),
        language=language,
        target_time=now_city.isoformat(timespec="minutes"),
        interests=retrieval.tourist_interests(session, tourist_id),
        candidates=_planner_candidates(candidates, settings),
        history=_history_turns(session, session_id=session_id, exclude_id=user_message.id),
    )

    provider = provider or default_provider()
    try:
        reply = provider.plan_itinerary(prompt)
    except (ProviderUnavailable, ProviderError, ProviderTimeout, ProviderMalformedOutput):
        assistant_message = chat_repo.add_message(
            session,
            session_id=session_id,
            role="assistant",
            content=_localize(UNAVAILABLE_TEXT, language),
        )
        return user_message, assistant_message

    anchored = anchor_selection(reply.spot_ids, reply.event_ids, candidates)
    if not anchored:
        # Edge case: the selection could not be anchored — communicate in
        # natural language instead of presenting impossible items (spec
        # edge case; FR-014 spirit).
        assistant_message = chat_repo.add_message(
            session,
            session_id=session_id,
            role="assistant",
            content=reply.text.strip() or _localize(NO_CANDIDATES_TEXT, language),
        )
        return user_message, assistant_message

    plan = build_itinerary(
        anchored,
        generated_at=now_city,
        target_day=target_day.isoformat(),
        dwell_minutes=settings.chatbot_dwell_minutes,
    )
    validation = validate_plan(plan, candidates, target_day=target_day.isoformat())
    if not validation.ok:
        # Never present broken items (FR-021): keep only the valid subset.
        plan = build_itinerary(
            _candidates_of(validation.valid_items, candidates),
            generated_at=now_city,
            target_day=target_day.isoformat(),
            dwell_minutes=settings.chatbot_dwell_minutes,
        )
    if not plan.items:
        # Edge case: after all criteria nothing is schedulable — communicate
        # instead of presenting an empty itinerary (spec edge case).
        assistant_message = chat_repo.add_message(
            session,
            session_id=session_id,
            role="assistant",
            content=_localize(NO_CANDIDATES_TEXT, language),
        )
        return user_message, assistant_message

    assistant_message = chat_repo.add_message(
        session,
        session_id=session_id,
        role="assistant",
        content=reply.text.strip() or _localize(NO_CANDIDATES_TEXT, language),
        itinerary=plan.snapshot(),
    )
    return user_message, assistant_message


def _candidates_of(items: list[ItineraryItem], candidates: list) -> list:
    """Map surviving items back to their candidates, preserving order."""
    by_ref = {(candidate.kind, candidate.ref_id): candidate for candidate in candidates}
    return [by_ref[(item.kind, item.ref_id)] for item in items]
