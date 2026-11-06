"""Itinerary assembly (feature 016 — research R3, FR-005/FR-006/FR-009/
FR-010/FR-011).

Deterministic structure: the selection the provider returned is anchored to
retrieved candidates (FR-006), re-ordered by greedy nearest-neighbor with
the great-circle distance between spots (FR-011/SC-003 — reuse of the
visitation public geolocation seam), placed at operating-hour-safe
suggested times (FR-009) and priced honestly (FR-010). The snapshot
embedded in the message carries generation-moment display data (FR-025).
"""

from dataclasses import dataclass, field
from datetime import datetime, timedelta

from passanorte_back.modules.chatbot.services.retrieval import Candidate
from passanorte_back.modules.visitation.services.geolocation import haversine_distance_m

# Cap on itinerary items (spec assumption: "meia dúzia de itens").
MAX_ITEMS: int = 6


@dataclass(frozen=True)
class ItineraryItem:
    """One ordered entry of the itinerary snapshot (FR-025)."""

    kind: str  # "spot" | "event"
    ref_id: int
    display_name: str
    suggested_at: datetime
    ticket_cost_cents: int


@dataclass(frozen=True)
class ItineraryPlan:
    """The structured itinerary produced for one assistant message."""

    generated_at: datetime
    target_day: str
    items: list[ItineraryItem] = field(default_factory=list)

    @property
    def total_cost_cents(self) -> int:
        return sum(item.ticket_cost_cents for item in self.items)

    def snapshot(self) -> dict:
        """The JSON snapshot embedded in the message (data-model §chat_messages)."""
        return {
            "generatedAt": self.generated_at.isoformat(),
            "targetDate": self.target_day,
            "totalCostCents": self.total_cost_cents,
            "items": [
                {
                    "kind": item.kind,
                    "refId": item.ref_id,
                    "displayName": item.display_name,
                    "suggestedAt": item.suggested_at.isoformat(),
                    "ticketCostCents": item.ticket_cost_cents,
                }
                for item in self.items
            ],
        }


def anchor_selection(
    reply_spot_ids: list[int], reply_event_ids: list[int], candidates: list[Candidate]
) -> list[Candidate]:
    """Provider ids → candidates in the provider's order (FR-006); unknown
    ids are silently dropped (constraint FR-021 re-validates downstream)."""
    spots = {candidate.ref_id: candidate for candidate in candidates if candidate.kind == "spot"}
    events = {candidate.ref_id: candidate for candidate in candidates if candidate.kind == "event"}
    anchored: list[Candidate] = []
    for ref_id in reply_event_ids:
        candidate = events.get(int(ref_id))
        if candidate is not None:
            anchored.append(candidate)
    for ref_id in reply_spot_ids:
        candidate = spots.get(int(ref_id))
        if candidate is not None:
            anchored.append(candidate)
    return anchored[:MAX_ITEMS] if len(anchored) > MAX_ITEMS else anchored


def order_geographically(selection: list[Candidate]) -> list[Candidate]:
    """Greedy nearest-neighbor over the spot coordinates (FR-011/SC-003):
    the first selected item anchors the start; each next item is the
    geographically nearest still-unvisited one — no zigzag across the city."""
    if len(selection) <= 2:
        return list(selection)
    ordered = [selection[0]]
    remaining = list(selection[1:])
    while remaining:
        last = ordered[-1]
        nearest = min(
            remaining,
            key=lambda candidate: (
                haversine_distance_m(
                    last.latitude, last.longitude, candidate.latitude, candidate.longitude
                ),
                candidate.ref_id,
            ),
        )
        ordered.append(nearest)
        remaining.remove(nearest)
    return ordered


def _suggested_time(candidate: Candidate, moment: datetime) -> datetime | None:
    """The earliest visit time at/after ``moment`` inside the candidate's
    operating window (FR-009); ``None`` when that day's window is already
    closed."""
    if candidate.kind != "spot" or candidate.opens_at is None or candidate.closes_at is None:
        return moment  # events have no daily window (FR-024 covers the day)
    opens = datetime.combine(moment.date(), candidate.opens_at, tzinfo=moment.tzinfo)
    closes = datetime.combine(moment.date(), candidate.closes_at, tzinfo=moment.tzinfo)
    if moment >= closes:
        return None
    return max(moment, opens)


def build_itinerary(
    selection: list[Candidate], *, generated_at: datetime, target_day: str, dwell_minutes: int
) -> ItineraryPlan:
    """Geographic order + sequential suggested times + per-item costs."""
    ordered = order_geographically(selection[:MAX_ITEMS])
    items: list[ItineraryItem] = []
    moment = generated_at
    for candidate in ordered:
        if items:
            moment = items[-1].suggested_at + timedelta(minutes=dwell_minutes)
        suggested = _suggested_time(candidate, moment)
        if suggested is None:
            continue  # spot already closed at the would-be time (FR-009)
        items.append(
            ItineraryItem(
                kind=candidate.kind,
                ref_id=candidate.ref_id,
                display_name=candidate.name,
                suggested_at=suggested,
                ticket_cost_cents=candidate.ticket_price_cents,
            )
        )
    return ItineraryPlan(generated_at=generated_at, target_day=target_day, items=items)
