"""Retrieval pipeline: candidates from the registered catalog (feature 016
— research R2, FR-007).

Structured SQL filters over the read-only projections do the coarse work:
only active spots (`status='open'`, not removed), open at the target
instant per their operating-schedule entries (FR-009), plus that target
day's events (FR-024). Relevance then ranks the survivors (US2, FR-020):
normalized lexical overlap (pt-BR accent/stopword-insensitive) between the
tourist query and name/description/category content, boosted for the
tourist's declared interest categories (FR-012). The ordering is
deterministic — ties keep a stable, reproducible sequence (SC-001).
"""

import unicodedata
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime, time

from sqlalchemy import select
from sqlalchemy.orm import Session

from passanorte_back.core.config import get_settings
from passanorte_back.modules.chatbot.repositories.read_projections import (
    EVENTS,
    TOURIST_INTERESTS,
    TOURIST_SPOT_CATEGORIES,
    TOURIST_SPOT_SCHEDULE_ENTRIES,
    TOURIST_SPOTS,
)

# Small pt-BR stopword set (lexical normalization tooling — not location
# data; RNF06: city/locality content lives in configuration).
STOPWORDS: frozenset[str] = frozenset(
    {
        "a",
        "o",
        "e",
        "as",
        "os",
        "um",
        "uma",
        "de",
        "do",
        "da",
        "dos",
        "das",
        "em",
        "no",
        "na",
        "nos",
        "nas",
        "para",
        "com",
        "por",
        "pra",
        "me",
        "meu",
        "minha",
        "quero",
        "queria",
        "gostaria",
        "favor",
        "hoje",
        "dia",
    }
)

# Interest match outranks any lexical-overlap difference (deterministic
# separation of the two ranking factors — FR-012).
INTEREST_BOOST: float = 1.0


@dataclass(frozen=True)
class Candidate:
    """One catalog candidate for the planner (spot coordinates also describe
    the event's location — events happen at their spot)."""

    kind: str  # "spot" | "event"
    ref_id: int
    name: str
    description: str
    category_keys: list[str]
    ticket_price_cents: int
    latitude: float
    longitude: float
    opens_at: time | None = None
    closes_at: time | None = None
    score: float = 0.0


def tourist_interests(session: Session, tourist_id: int) -> list[str]:
    """The tourist's interest category keys (FR-012; projection, read-only)."""
    rows = session.execute(
        select(TOURIST_INTERESTS.c.category_key).where(TOURIST_INTERESTS.c.tourist_id == tourist_id)
    ).all()
    return [row[0] for row in rows]


def _spot_open_at(weekday: int, moment: time, entries: list[tuple[int, time, time]]) -> bool:
    """True if the spot is open at ``weekday``/'time' per its schedule
    entries (FR-009)."""
    return any(
        entry_weekday == weekday and entry_opens <= moment < entry_closes
        for entry_weekday, entry_opens, entry_closes in entries
    )


def _tokenize(text: str) -> set[str]:
    """Lowercase, accent-stripped, stopword-free token set of ``text``."""
    lowered = unicodedata.normalize("NFKD", text.casefold())
    plain = "".join(character for character in lowered if not unicodedata.combining(character))
    return {token for token in plain.split() if token not in STOPWORDS}


def category_label_tokens(category_keys: list[str]) -> set[str]:
    """Tokens of the configured labels for the candidate's categories (data
    from ``config/location.json`` — RNF06, no hardcode)."""
    labels = {
        str(category.get("key", "")): str(category.get("label", ""))
        for category in get_settings().resolved_interest_categories()
    }
    tokens: set[str] = set()
    for key in category_keys:
        tokens |= _tokenize(key) | _tokenize(labels.get(key, ""))
    return tokens


def score_candidate(candidate: Candidate, query_tokens: set[str], interests: list[str]) -> float:
    """Deterministic relevance: lexical overlap fraction + interest boost."""
    candidate_tokens = (
        _tokenize(candidate.name)
        | _tokenize(candidate.description)
        | category_label_tokens(candidate.category_keys)
    )
    overlap = len(query_tokens & candidate_tokens)
    relevance = overlap / len(query_tokens) if query_tokens else 0.0
    interest = 1.0 if any(key in interests for key in candidate.category_keys) else 0.0
    return relevance + interest * INTEREST_BOOST


def retrieve_candidates(
    session: Session,
    *,
    tourist_id: int,
    at: datetime,
    target_day: date,
    query: str = "",
) -> list[Candidate]:
    """Active, open-now spots + that day's events, ranked by relevance
    (research R2 stages 1–2).

    ``at`` carries the target instant in the city timezone; ``target_day``
    is the target date used for events (FR-024). ``query`` drives the
    lexical ranking (SC-001); interest categories boost ranked order
    (FR-012).
    """
    weekday = at.isoweekday()
    moment = at.time()

    spot_rows = session.execute(
        select(
            TOURIST_SPOTS.c.id,
            TOURIST_SPOTS.c.name,
            TOURIST_SPOTS.c.description,
            TOURIST_SPOTS.c.latitude,
            TOURIST_SPOTS.c.longitude,
        ).where(TOURIST_SPOTS.c.status == "open", TOURIST_SPOTS.c.removed_at.is_(None))
    ).all()

    spot_ids = [row.id for row in spot_rows]
    if not spot_ids:
        return []

    schedule_by_spot: dict[int, list[tuple[int, time, time]]] = defaultdict(list)
    for row in session.execute(
        select(
            TOURIST_SPOT_SCHEDULE_ENTRIES.c.spot_id,
            TOURIST_SPOT_SCHEDULE_ENTRIES.c.weekday,
            TOURIST_SPOT_SCHEDULE_ENTRIES.c.opens_at,
            TOURIST_SPOT_SCHEDULE_ENTRIES.c.closes_at,
        ).where(TOURIST_SPOT_SCHEDULE_ENTRIES.c.spot_id.in_(spot_ids))
    ).all():
        schedule_by_spot[int(row.spot_id)].append((int(row.weekday), row.opens_at, row.closes_at))

    categories_by_spot: dict[int, list[str]] = defaultdict(list)
    for row in session.execute(
        select(
            TOURIST_SPOT_CATEGORIES.c.spot_id,
            TOURIST_SPOT_CATEGORIES.c.category_key,
        ).where(TOURIST_SPOT_CATEGORIES.c.spot_id.in_(spot_ids))
    ).all():
        categories_by_spot[int(row.spot_id)].append(str(row.category_key))

    candidates: list[Candidate] = []
    for row in spot_rows:
        entries = schedule_by_spot.get(int(row.id), [])
        if not _spot_open_at(weekday, moment, entries):
            continue  # FR-009: closed spots never become candidates
        openings = [entry for entry in entries if entry[0] == weekday]
        candidates.append(
            Candidate(
                kind="spot",
                ref_id=int(row.id),
                name=str(row.name),
                description=str(row.description or ""),
                category_keys=categories_by_spot.get(int(row.id), []),
                ticket_price_cents=0,
                latitude=float(row.latitude),
                longitude=float(row.longitude),
                opens_at=min(entry[1] for entry in openings),
                closes_at=max(entry[2] for entry in openings),
            )
        )

    # Events need no opening-hour check of their own (FR-024: day match is
    # the availability rule); they inherit the spot's location.
    event_rows = session.execute(
        select(
            EVENTS.c.id,
            EVENTS.c.spot_id,
            EVENTS.c.description,
            EVENTS.c.ticket_price_cents,
            TOURIST_SPOTS.c.name,
            TOURIST_SPOTS.c.latitude,
            TOURIST_SPOTS.c.longitude,
        )
        .join(TOURIST_SPOTS, EVENTS.c.spot_id == TOURIST_SPOTS.c.id)
        .where(
            EVENTS.c.occurrence_date == target_day,
            TOURIST_SPOTS.c.status == "open",
            TOURIST_SPOTS.c.removed_at.is_(None),
        )
    ).all()
    for row in event_rows:
        candidates.append(
            Candidate(
                kind="event",
                ref_id=int(row.id),
                name=str(row.name),
                description=str(row.description or ""),
                category_keys=categories_by_spot.get(int(row.spot_id), []),
                ticket_price_cents=int(row.ticket_price_cents),
                latitude=float(row.latitude),
                longitude=float(row.longitude),
            )
        )

    return ranked_candidates(candidates, query, interests=tourist_interests(session, tourist_id))


def ranked_candidates(
    candidates: list[Candidate], query: str, *, interests: list[str]
) -> list[Candidate]:
    """Assign scores and sort descending (stable ties — SC-001)."""
    query_tokens = _tokenize(query)
    scored = [
        Candidate(
            kind=candidate.kind,
            ref_id=candidate.ref_id,
            name=candidate.name,
            description=candidate.description,
            category_keys=candidate.category_keys,
            ticket_price_cents=candidate.ticket_price_cents,
            latitude=candidate.latitude,
            longitude=candidate.longitude,
            opens_at=candidate.opens_at,
            closes_at=candidate.closes_at,
            score=score_candidate(candidate, query_tokens, interests),
        )
        for candidate in candidates
    ]
    scored.sort(key=lambda candidate: (-candidate.score, candidate.ref_id))
    return scored
