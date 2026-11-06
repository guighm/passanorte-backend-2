"""HTTP-bound chatbot schemas (feature 016 — contracts/chatbot-api.md).

All inherit ``core.schemas.ApiModel``: camelCase JSON on the wire,
``extra="forbid"`` strict border, constructed in code via ``from_internal``
(snake_case keywords → camelCase alias). No module-external surface.
"""

from datetime import date, datetime
from typing import Annotated, Any

from pydantic import Field

from passanorte_back.core.schemas import ApiModel


class CreateSessionResponse(ApiModel):
    """POST /chatbot/sessions → 201."""

    session_id: int
    created_at: datetime


class SessionListItem(ApiModel):
    """One row of the tourist's session list (FR-002)."""

    session_id: int
    created_at: datetime
    last_message_at: datetime | None


class SessionListResponse(ApiModel):
    """GET /chatbot/sessions → 200."""

    sessions: list[SessionListItem]


class ItineraryItemView(ApiModel):
    """One ordered itinerary item — the FR-025 snapshot the Passaporte
    renders (SC-006)."""

    kind: str
    ref_id: int
    display_name: str
    suggested_at: datetime
    ticket_cost_cents: int


class ItineraryView(ApiModel):
    """The structured itinerary embedded in an assistant message."""

    generated_at: datetime
    target_date: date
    total_cost_cents: int
    items: list[ItineraryItemView]


class ChatMessageView(ApiModel):
    """One persisted message (tourist or chatbot) in a session history."""

    message_id: int
    role: str
    content: str
    itinerary: ItineraryView | None
    created_at: datetime


class SessionHistoryResponse(ApiModel):
    """GET /chatbot/sessions/{session_id} → 200."""

    session_id: int
    messages: list[ChatMessageView]


class SendMessageRequest(ApiModel):
    """POST .../messages body (FR-003) — non-empty text only."""

    text: Annotated[str, Field(min_length=1)]


class SendMessageResponse(ApiModel):
    """POST .../messages → 201: the tourist message + the assistant reply."""

    user_message: ChatMessageView
    assistant_message: ChatMessageView


def itinerary_snapshot_view(snapshot: dict[str, Any] | None) -> ItineraryView | None:
    """Adapt the persisted snapshot dict into the strict response schema."""
    if snapshot is None:
        return None
    return ItineraryView.from_internal(
        generated_at=datetime.fromisoformat(snapshot["generatedAt"]),
        target_date=snapshot["targetDate"],
        total_cost_cents=snapshot["totalCostCents"],
        items=[
            ItineraryItemView.from_internal(
                kind=item["kind"],
                ref_id=item["refId"],
                display_name=item["displayName"],
                suggested_at=datetime.fromisoformat(item["suggestedAt"]),
                ticket_cost_cents=item["ticketCostCents"],
            )
            for item in snapshot["items"]
        ],
    )
