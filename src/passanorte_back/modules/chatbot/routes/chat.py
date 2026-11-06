"""HTTP routes of the ``chatbot`` module (feature 016 — contracts/chatbot-api.md).

Mounted on the canonical router (``MODULE_ROUTERS["chatbot"]``, prefix
``/api/v1/chatbot``). The tag comes exclusively from the central registry
via ``core/routers.py`` — no tag strings here (feature 006). Every endpoint
is tourist-exclusive (``require_tourist``, FR-001); missing/foreign
sessions are indistinguishable 404s (no enumeration). All failures flow
through ``HTTPException`` → unified ``ApiError``; provider failures never
surface as 5xx (FR-018 — degraded mode lives in the service).

Docs use camelCase ``{sessionId}`` in URL templates (spec 009 precedent):
code path variables stay snake_case; the OpenAPI border renders the HTTP
path as contracted.
"""

from typing import Annotated

from fastapi import Depends, HTTPException, status
from sqlalchemy.orm import Session

from passanorte_back.core.db import get_session
from passanorte_back.core.routers import MODULE_ROUTERS
from passanorte_back.modules.auth.services.security import (
    AuthenticatedUser,
    require_tourist,
)
from passanorte_back.modules.chatbot import schemas as chat_schemas
from passanorte_back.modules.chatbot.repositories.chat import ChatMessage
from passanorte_back.modules.chatbot.services.chat import (
    create_chat_session,
    default_provider,
    get_history,
    list_chat_sessions,
    send_message,
)
from passanorte_back.modules.chatbot.services.providers import LlmProvider

router = MODULE_ROUTERS["chatbot"]


def _message_view(message: ChatMessage) -> chat_schemas.ChatMessageView:
    return chat_schemas.ChatMessageView.from_internal(
        message_id=message.id,
        role=message.role,
        content=message.content,
        itinerary=chat_schemas.itinerary_snapshot_view(message.itinerary),
        created_at=message.created_at,
    )


@router.post(
    "/sessions",
    response_model=chat_schemas.CreateSessionResponse,
    status_code=status.HTTP_201_CREATED,
)
def post_session(
    session: Annotated[Session, Depends(get_session)],
    tourist: Annotated[AuthenticatedUser, Depends(require_tourist)],
) -> chat_schemas.CreateSessionResponse:
    """Create a chat session owned by the tourist (FR-002; 201)."""
    item = create_chat_session(session, tourist_id=tourist.account_id)
    return chat_schemas.CreateSessionResponse.from_internal(
        session_id=item.id, created_at=item.created_at
    )


@router.get("/sessions", response_model=chat_schemas.SessionListResponse)
def get_sessions(
    session: Annotated[Session, Depends(get_session)],
    tourist: Annotated[AuthenticatedUser, Depends(require_tourist)],
) -> chat_schemas.SessionListResponse:
    """List the tourist's own sessions, newest first (FR-002; 200)."""
    items = list_chat_sessions(session, tourist_id=tourist.account_id)
    return chat_schemas.SessionListResponse.from_internal(
        sessions=[
            chat_schemas.SessionListItem.from_internal(
                session_id=item.id,
                created_at=item.created_at,
                last_message_at=last_message_at,
            )
            for item, last_message_at in items
        ]
    )


@router.get("/sessions/{session_id}", response_model=chat_schemas.SessionHistoryResponse)
def get_session_history(
    session_id: int,
    session: Annotated[Session, Depends(get_session)],
    tourist: Annotated[AuthenticatedUser, Depends(require_tourist)],
) -> chat_schemas.SessionHistoryResponse:
    """Full history of an owned session (FR-003/FR-004; 200 — 404 when the
    session is missing or belongs to another tourist, FR-001)."""
    messages = get_history(session, session_id=session_id, tourist_id=tourist.account_id)
    if messages is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="session not found")
    return chat_schemas.SessionHistoryResponse.from_internal(
        session_id=session_id,
        messages=[_message_view(message) for message in messages],
    )


@router.post(
    "/sessions/{session_id}/messages",
    response_model=chat_schemas.SendMessageResponse,
    status_code=status.HTTP_201_CREATED,
)
def post_message(
    session_id: int,
    payload: chat_schemas.SendMessageRequest,
    session: Annotated[Session, Depends(get_session)],
    tourist: Annotated[AuthenticatedUser, Depends(require_tourist)],
    llm: Annotated[LlmProvider, Depends(default_provider)],
) -> chat_schemas.SendMessageResponse:
    """Send a tourist message and get the assistant reply (FR-003/FR-005;
    201 — 404 missing/foreign session). Provider failures are handled in
    the service as degraded mode; they never become HTTP 5xx (FR-018)."""
    pair = send_message(
        session,
        session_id=session_id,
        tourist_id=tourist.account_id,
        text=payload.text,
        provider=llm,
    )
    if pair is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="session not found")
    user_message, assistant_message = pair
    return chat_schemas.SendMessageResponse.from_internal(
        user_message=_message_view(user_message),
        assistant_message=_message_view(assistant_message),
    )
