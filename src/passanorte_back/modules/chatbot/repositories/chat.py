"""Chat session and message persistence (feature 016 data-model §1).

The ``chat_sessions``/``chat_messages`` tables belong exclusively to the
``chatbot`` domain. A session belongs to exactly one tourist and lives on
forever — no closure state (spec clarification Q1). The assistant's
structured itinerary is embedded in the assistant message (clarification
Q2) as a JSON snapshot with display data of the generation moment (FR-025
— renderizable even if the referenced spot/event changes or is removed
later).
"""

from datetime import UTC, datetime
from typing import Final, Literal

from sqlalchemy import ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, Session, mapped_column
from sqlalchemy.types import JSON

from passanorte_back.core.db import Base

ROLE_LENGTH: Final[int] = 20
ROLE_USER: Final[Literal["user"]] = "user"
ROLE_ASSISTANT: Final[Literal["assistant"]] = "assistant"
VALID_ROLES: Final[frozenset[str]] = frozenset({ROLE_USER, ROLE_ASSISTANT})

# SQLAlchemy JSON variant: JSONB on PostgreSQL, JSON elsewhere (SQLite).
JSONVariant = JSON().with_variant(JSONB(), "postgresql")


def _utc_now() -> datetime:
    return datetime.now(UTC)


class ChatSession(Base):
    """One conversation of one tourist (data-model.md §chat_sessions)."""

    __tablename__ = "chat_sessions"

    id: Mapped[int] = mapped_column(primary_key=True)
    tourist_id: Mapped[int] = mapped_column(ForeignKey("tourists.id"), index=True)
    created_at: Mapped[datetime] = mapped_column(default=_utc_now)


class ChatMessage(Base):
    """One message of a session — authored by the tourist or the chatbot
    (data-model.md §chat_messages). Immutable once written."""

    __tablename__ = "chat_messages"

    id: Mapped[int] = mapped_column(primary_key=True)
    session_id: Mapped[int] = mapped_column(ForeignKey("chat_sessions.id"), index=True)
    role: Mapped[str] = mapped_column(String(ROLE_LENGTH))
    content: Mapped[str] = mapped_column(Text)
    itinerary: Mapped[dict | None] = mapped_column(JSONVariant, default=None)
    created_at: Mapped[datetime] = mapped_column(default=_utc_now)


def create_session(session: Session, *, tourist_id: int) -> ChatSession:
    """Create a session owned by ``tourist_id`` (FR-002)."""
    chat_session = ChatSession(tourist_id=tourist_id)
    session.add(chat_session)
    session.flush()
    return chat_session


def list_sessions_for_tourist(session: Session, *, tourist_id: int) -> list[ChatSession]:
    """All sessions owned by ``tourist_id``, newest first (FR-002)."""
    return (
        session.query(ChatSession)
        .filter(ChatSession.tourist_id == tourist_id)
        .order_by(ChatSession.id.desc())
        .all()
    )


def get_owned_session(session: Session, *, session_id: int, tourist_id: int) -> ChatSession | None:
    """The session only if it exists AND is owned by ``tourist_id`` (FR-001);
    foreign or missing sessions look identical to the caller (contract: 404)."""
    return (
        session.query(ChatSession)
        .filter(ChatSession.id == session_id, ChatSession.tourist_id == tourist_id)
        .one_or_none()
    )


def get_last_message_at(session: Session, *, session_id: int) -> datetime | None:
    """Timestamp of the newest message in the session, if any."""
    row = (
        session.query(ChatMessage.created_at)
        .filter(ChatMessage.session_id == session_id)
        .order_by(ChatMessage.id.desc())
        .first()
    )
    return None if row is None else row[0]


def add_message(
    session: Session,
    *,
    session_id: int,
    role: str,
    content: str,
    itinerary: dict | None = None,
) -> ChatMessage:
    """Persist one message (FR-003). ``role`` must be in ``VALID_ROLES``."""
    if role not in VALID_ROLES:
        raise ValueError(f"invalid chat message role: '{role}'")
    message = ChatMessage(session_id=session_id, role=role, content=content, itinerary=itinerary)
    session.add(message)
    session.flush()
    return message


def list_messages(session: Session, *, session_id: int) -> list[ChatMessage]:
    """All messages of a session, oldest first (FR-003/FR-004)."""
    return (
        session.query(ChatMessage)
        .filter(ChatMessage.session_id == session_id)
        .order_by(ChatMessage.id)
        .all()
    )
