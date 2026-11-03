"""Gamification domain flows (feature 009; research R2–R12).

Routes → services → repositories. This module owns the flows of the
gamification domain; every cross-module read validates targets ONLY through
the owners' public service interfaces (``tourists.services.get_tourist_account``,
``tourist_spots.services.get_active_spot`` — research R3); cross-module
writes never exist outside this module's own tables.

This foundational slice (T005) holds the domain exceptions (route-mapped per
contracts §6) and the redemption-code primitive (research R5). The flows are
implemented per user story (T007 US1, T012 US2, T017 US3, T022 US4).
"""

import secrets
from datetime import UTC, datetime
from typing import Final, NamedTuple

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from passanorte_back.core.audit import record_action
from passanorte_back.modules.gamification import repositories as gamification_repositories
from passanorte_back.modules.gamification import schemas as gamification_schemas
from passanorte_back.modules.gamification.repositories.gamification import (
    exists_code_value,  # noqa: F401 — collision check helper (R5)
    find_prize_by_id,  # noqa: F401 — re-exported for HTTP view building
    find_route_by_id,
)

_CODE_ENTROPY_BYTES: Final[int] = 16  # 128 bits (research R5)
_MAX_CODE_ATTEMPTS: Final[int] = 5

# ---
# Domain exceptions — route mapping lives in routes/ (contracts §6)
# ---


class RouteMissingError(Exception):
    """Route not found (or archived where the caller cannot see it) — 404."""


class InvalidRouteInputError(Exception):
    """Invalid payload beyond schema shape — 422."""


class TouristSpotMissingError(Exception):
    """Tourist spot not found (or removed) — 404.

    Single name for every "spot not found" path: route payloads (US1),
    seam validation (US2) and concession pickup (US4) (análise F3).
    """


class TouristMissingError(Exception):
    """Tourist not found — 404."""


class EnrollmentConflictError(Exception):
    """Duplicate enrollment of the same tourist on the same route — 409."""


class EnrollmentMissingError(Exception):
    """Enrollment not found (or owned by another tourist) — 404 (FR-013)."""


class PrizeStockInsufficientError(Exception):
    """No stock for the concession — 409; code stays valid (research R4)."""


class CodeAlreadyUsedError(Exception):
    """The redemption code was already honored — 409 (FR-009)."""


class PrizeMissingError(Exception):
    """Prize not found — 404."""


class CodeMissingError(Exception):
    """Redemption code not found — 404."""


# ---
# Redemption-code primitive (research R5)
# ---


def new_redemption_code(session: Session | None = None) -> str:
    """128-bit CSPRNG redemption code, URL-safe (RF36/SC-004; research R5).

    ``secrets.token_urlsafe(16)`` — 22 URL-safe characters, never expiring
    (Q4) and not derivable from any counter/identifier. When a session is
    given, values are retried against the stored codes until unseen
    (collision probability ≈ 0, bounded retries).
    """
    for _ in range(_MAX_CODE_ATTEMPTS):
        code = secrets.token_urlsafe(_CODE_ENTROPY_BYTES)
        if session is None:
            return code
        if not gamification_repositories.exists_code_value(session, code):
            return code
    raise RuntimeError(
        f"could not generate a unique redemption code after {_MAX_CODE_ATTEMPTS} attempts"
    )


# ---
# View helpers (routes) — wire status mapping (data-model §4)
# ---


def _route_status_wire(route) -> str:  # noqa: ANN001
    return "archived" if route.removed_at is not None else "active"


def route_to_view(route) -> gamification_schemas.TouristRouteView:  # noqa: ANN001
    """Full route view: create/edit/detail responses (contract §1)."""
    return gamification_schemas.TouristRouteView.from_internal(
        id=route.id,
        name=route.name,
        description=route.description,
        spots=[
            gamification_schemas.RouteSpotItemView.from_internal(
                spot_id=spot.tourist_spot_id, display_order=spot.display_order
            )
            for spot in route.route_spots
        ],
        prize=gamification_schemas.RoutePrizeView.from_internal(
            id=route.prize.id, name=route.prize.name, stock_quantity=route.prize.stock_quantity
        ),
        status=_route_status_wire(route),
    )


def route_to_summary_view(route) -> gamification_schemas.RouteSummaryView:  # noqa: ANN001
    """Listing item (contract §1)."""
    return gamification_schemas.RouteSummaryView.from_internal(
        id=route.id,
        name=route.name,
        description=route.description,
        spot_count=len(route.route_spots),
        prize=gamification_schemas.RoutePrizeView.from_internal(
            id=route.prize.id, name=route.prize.name, stock_quantity=route.prize.stock_quantity
        ),
        status=_route_status_wire(route),
    )


# ---
# US1: route-management flows (RF18/RF19) — one audit record per write
# ---


def _validate_spot_payload(spots: list[gamification_schemas.RouteSpotItemInput]) -> None:
    """Cross-entry shape rules (422): distinct spot ids, distinct display
    orders (positions are validated beyond the schema minima)."""
    spot_ids = [entry.spot_id for entry in spots]
    if len(spot_ids) != len(set(spot_ids)):
        raise InvalidRouteInputError("duplicated spotId entries in the submission")
    orders = [entry.display_order for entry in spots]
    if len(orders) != len(set(orders)):
        raise InvalidRouteInputError("duplicated displayOrder entries in the submission")


def _validate_targets_exist(
    session: Session, spots: list[gamification_schemas.RouteSpotItemInput]
) -> None:
    """Every spot id must reference an active spot (404 — research R3)."""
    from passanorte_back.modules.tourist_spots.services import tourist_spots as spots_service

    for entry in spots:
        try:
            spots_service.get_active_spot(session, entry.spot_id)
        except spots_service.SpotMissingError as error:
            raise TouristSpotMissingError(f"tourist spot {entry.spot_id} not found") from error


def create_route(
    session: Session,
    *,
    actor: str,
    payload: gamification_schemas.RouteCreateRequest,
):
    """Create the route + prize (RF18; F1 — prize bound at creation)."""
    _validate_spot_payload(payload.spots)
    _validate_targets_exist(session, payload.spots)

    prize = gamification_repositories.create_prize(
        session, name=payload.prize.name, stock_quantity=payload.prize.initial_stock
    )
    route = gamification_repositories.add_route(
        session,
        name=payload.name,
        description=payload.description,
        prize_id=prize.id,
    )
    gamification_repositories.replace_route_spots(
        session,
        route,
        spot_ids=[(entry.spot_id, entry.display_order) for entry in payload.spots],
    )
    session.flush()
    session.refresh(route)
    record_action(
        actor=actor,
        action="route.create",
        target=f"route:{route.id}",
        result="success",
        detail={"spotCount": len(payload.spots), "prizeId": prize.id},
    )
    return route


def update_route(
    session: Session,
    *,
    actor: str,
    route_id: int,
    payload: gamification_schemas.RouteUpdateRequest,
):
    """Partial edit (RF19); prize is not rebindable (F1) — names/description
    and the full spots list change; enrollments stay valid. Archived routes
    are not editable (Removal Decision — 404)."""
    route = get_route_available(session, route_id)

    changed = False
    if payload.name is not None:
        route.name = payload.name
        changed = True
    if payload.description is not None:
        route.description = payload.description
        changed = True
    if payload.spots is not None:
        _validate_spot_payload(payload.spots)
        _validate_targets_exist(session, payload.spots)
        gamification_repositories.replace_route_spots(
            session,
            route,
            spot_ids=[(entry.spot_id, entry.display_order) for entry in payload.spots],
        )
        changed = True

    if changed:
        session.flush()
        _reevaluate_in_progress_enrollments(session, route_id=route.id, actor=actor)
        session.refresh(route)
        record_action(
            actor=actor,
            action="route.update",
            target=f"route:{route.id}",
            result="success",
            detail={"spotCount": len(route.route_spots)},
        )
    return route


def _reevaluate_in_progress_enrollments(session: Session, *, route_id: int, actor: str) -> None:  # noqa: ANN001
    """Edge Case 1 (spec): after the spots list changes, an in-progress
    enrollment whose remaining spots are ALL already visited completes
    exactly once with the same reward flow (badge + code + reservation —
    the conditional-update guard makes repetition a no-op; no per-completion
    audit: the action belongs to the route edit). Edge Case 2a is covered by
    the derivation itself: added spots appear as pending in-progress."""
    for enrollment in gamification_repositories.list_in_progress_enrollments_of_route(
        session, route_id
    ):
        rate, visited_count, total = _enrollment_completion_rate(session, enrollment)
        if visited_count >= total:
            completed = (
                gamification_repositories.mark_enrollment_completed(session, enrollment.id) == 1
            )
            if completed:
                _emit_completion_rewards(session, enrollment)


def archive_route_flow(session: Session, *, actor: str, route_id: int) -> None:
    """Archive (remove) with history preserved (FR-012 Removal Decision)."""
    route = get_route_for_admin(session, route_id)
    gamification_repositories.archive_route(session, route, when=datetime.now(UTC))
    record_action(
        actor=actor,
        action="route.delete",
        target=f"route:{route_id}",
        result="success",
        detail={"name": route.name},
    )


def list_routes_active(session: Session):
    """Browsing listing: active routes only (contract §1)."""
    return gamification_repositories.list_routes(session)


def list_routes_admin(session: Session, *, include_archived: bool = False):
    """Administrative listing; archived routes on explicit request."""
    return gamification_repositories.list_routes(session, include_archived=include_archived)


def get_route_for_admin(session: Session, route_id: int):
    """Admin read: any state (Removal Decision); unknown → 404."""
    route = find_route_by_id(session, route_id)
    if route is None:
        raise RouteMissingError("tourist route not found")
    return route


def get_route_available(session: Session, route_id: int):
    """Non-admin read (tourists browsing the Passaporte app): active only."""
    route = get_route_for_admin(session, route_id)
    if route.removed_at is not None:
        raise RouteMissingError("tourist route not found")
    return route


# ---
# US2: enrollment + progress + the touristic-visit seam (RF29/RF30/RF34)
# ---


class VisitRouteOutcome(NamedTuple):
    """One affected route of a registered visit (Q5; research R8)."""

    route_id: int
    completion_rate: int  # integer 0..100 (floor — R8)
    completed: bool


def _require_tourist(session: Session, tourist_id: int) -> None:
    """Tourist validation through the tourists public seam (404 — R3)."""
    from passanorte_back.modules.tourists.services.tourists import get_tourist_account

    account = get_tourist_account(session, tourist_id)
    if account is None or not account.active:
        raise TouristMissingError("tourist not found")


def enroll_tourist(session: Session, *, tourist_id: int, route_id: int):
    """Enroll in a route available for enrollment (RF29).

    Duplicate subscription → ``EnrollmentConflictError`` (409); archived/
    unknown route → ``RouteMissingError`` (404); unknown tourist →
    ``TouristMissingError`` (404).
    """
    _require_tourist(session, tourist_id)
    get_route_available(session, route_id)
    try:
        return gamification_repositories.add_enrollment(
            session, route_id=route_id, tourist_id=tourist_id
        )
    except IntegrityError as error:
        raise EnrollmentConflictError("tourist is already enrolled in this route") from error


def _enrollment_completion_rate(session: Session, enrollment) -> tuple[int, int, int]:  # noqa: ANN001
    """Derived progress (research R1): (rate, visited_count, total)."""
    spot_ids = [
        spot_id
        for spot_id, _order in gamification_repositories.list_route_spot_ids(
            session, enrollment.route_id
        )
    ]
    visited = gamification_repositories.find_visited_spot_ids(
        session, tourist_id=enrollment.tourist_id, spot_ids=spot_ids
    )
    visited_count = len(visited)
    total = len(spot_ids)
    rate = (visited_count * 100) // total if total else 0
    return rate, visited_count, total


def _enrollment_status_wire(enrollment) -> str:  # noqa: ANN001
    return "inProgress" if enrollment.status == "in_progress" else enrollment.status


def enrollment_to_summary_view(session, enrollment):  # noqa: ANN001
    """Enrollment summary (contract §2)."""
    rate, _visited, _total = _enrollment_completion_rate(session, enrollment)
    if enrollment.status == "completed":
        rate = 100  # completion invariant (Edge Case 2)
    return gamification_schemas.EnrollmentSummaryView.from_internal(
        id=enrollment.id,
        route_id=enrollment.route_id,
        status=_enrollment_status_wire(enrollment),
        completion_rate=rate,
        created_at=enrollment.created_at,
        completed_at=enrollment.completed_at,
    )


def get_enrollment_for_tourist(session: Session, tourist_id: int, enrollment_id: int):
    """Own-enrollment read (FR-013): foreign/unknown are both 404."""
    enrollment = gamification_repositories.find_enrollment_by_id(session, enrollment_id)
    if enrollment is None or enrollment.tourist_id != tourist_id:
        raise EnrollmentMissingError("enrollment not found")
    return enrollment


def get_enrollment_progress_view(session: Session, tourist_id: int, enrollment_id: int):
    """Full progress (contract §2): spots visited/pending + rate; badge and
    code embedded when completed (emitted once — RF35/RF36)."""
    enrollment = get_enrollment_for_tourist(session, tourist_id, enrollment_id)
    spot_entries = gamification_repositories.list_route_spot_ids(session, enrollment.route_id)
    visited = gamification_repositories.find_visited_spot_ids(
        session, tourist_id=tourist_id, spot_ids=[spot_id for spot_id, _ in spot_entries]
    )
    total = len(spot_entries)
    visited_count = len(visited)
    rate = (visited_count * 100) // total if total else 0
    if enrollment.status == "completed":
        # Edge Case 2 (spec): a completed enrollment never regresses — added
        # later spots render as pending entries among the spot flags, but the
        # rate and the earned rewards stay frozen at the completion invariant.
        rate = 100
    badge = None
    code_view = None
    if enrollment.status == "completed":
        badge_row = gamification_repositories.find_badge(
            session, route_id=enrollment.route_id, tourist_id=tourist_id
        )
        if badge_row is not None:
            badge = gamification_schemas.BadgeView.from_internal(
                route_id=badge_row.route_id, granted_at=badge_row.granted_at
            )
        code_row = gamification_repositories.find_code_for_owner(
            session, route_id=enrollment.route_id, tourist_id=tourist_id
        )
        if code_row is not None:
            code_view = gamification_schemas.RedemptionCodeView.from_internal(
                code=code_row.code, status=code_row.status
            )
    return gamification_schemas.EnrollmentProgressView.from_internal(
        id=enrollment.id,
        route_id=enrollment.route_id,
        status=_enrollment_status_wire(enrollment),
        completion_rate=rate,
        created_at=enrollment.created_at,
        completed_at=enrollment.completed_at,
        spots=[
            gamification_schemas.ProgressSpotView.from_internal(
                spot_id=spot_id, visited=spot_id in visited
            )
            for spot_id, _order in spot_entries
        ],
        visited_count=visited_count,
        total_spots=total,
        badge=badge,
        redemption_code=code_view,
    )


def list_tourist_enrollments(session: Session, tourist_id: int):
    """The tourist's enrollments, summaries, newest first (contract §2)."""
    return [
        enrollment_to_summary_view(session, enrollment)
        for enrollment in gamification_repositories.list_enrollments_of_tourist(session, tourist_id)
    ]


# ---
# The public domain seam (RF34/Q5) — the ONLY cross-module entry for visits
# ---


def _completion_rate_of(session: Session, enrollment) -> int:  # noqa: ANN001
    rate, _visited, _total = _enrollment_completion_rate(session, enrollment)
    return rate


def register_spot_visit(
    session: Session,
    *,
    tourist_id: int,
    tourist_spot_id: int,
) -> list[VisitRouteOutcome]:
    """Record the visit and update EVERY in-progress enrollment containing
    the spot (RF34) — one call, one transaction; on the last pending spot,
    completes the enrollment exactly once and emits the rewards (US3).

    Returns one outcome per affected route (route_id + completion_rate +
    completed — Q5; research R8/R12). Domain-exception surface (the caller
    maps to HTTP): ``TouristMissingError``/``TouristSpotMissingError``.
    """
    from passanorte_back.modules.tourist_spots.services import tourist_spots as spots_service

    _require_tourist(session, tourist_id)
    try:
        spots_service.get_active_spot(session, tourist_spot_id)
    except spots_service.SpotMissingError as error:
        raise TouristSpotMissingError(f"tourist spot {tourist_spot_id} not found") from error

    gamification_repositories.record_visit(
        session, tourist_id=tourist_id, tourist_spot_id=tourist_spot_id
    )

    outcomes: list[VisitRouteOutcome] = []
    enrollments = gamification_repositories.list_in_progress_enrollments_for_spot(
        session, tourist_id=tourist_id, tourist_spot_id=tourist_spot_id
    )
    for enrollment in enrollments:
        rate, visited_count, total = _enrollment_completion_rate(session, enrollment)
        completed = False
        if visited_count >= total:  # last pending spot → complete (US3, T017)
            completed = (
                gamification_repositories.mark_enrollment_completed(session, enrollment.id) == 1
            )
            if completed:
                _emit_completion_rewards(session, enrollment)
                rate = 100
        outcomes.append(
            VisitRouteOutcome(
                route_id=enrollment.route_id,
                completion_rate=rate,
                completed=completed,
            )
        )
    session.flush()
    return outcomes


def _emit_completion_rewards(session: Session, enrollment) -> None:  # noqa: ANN001
    """Exactly once per enrollment (research R2): badge + unique code +
    idempotent stock reservation — same transaction as the completion."""
    from sqlalchemy.exc import IntegrityError

    gamification_repositories.grant_badge(
        session, route_id=enrollment.route_id, tourist_id=enrollment.tourist_id
    )
    route = gamification_repositories.find_route_by_id(session, enrollment.route_id)
    assert route is not None  # enrollment FK guarantees it
    for _attempt in range(_MAX_CODE_ATTEMPTS):
        code = new_redemption_code(session)
        try:
            gamification_repositories.add_code(
                session,
                code=code,
                route_id=enrollment.route_id,
                tourist_id=enrollment.tourist_id,
                prize_id=route.prize_id,
            )
            break
        except IntegrityError:
            session.rollback()
    gamification_repositories.try_reserve_prize(session, route.prize_id)


# ---
# US4: prize stock control + staff concession (RF20/RF36 — Q3)
# ---


def adjust_prize_stock(
    session: Session,
    *,
    actor: str,
    prize_id: int,
    stock_quantity: int,
):
    """Adjust the stock of a prize (RF20): ≥ 0 and never below the units
    already committed to reservations (edge case); 1 audit record."""
    prize = gamification_repositories.find_prize_by_id(session, prize_id)
    if prize is None:
        raise PrizeMissingError("prize not found")
    if stock_quantity < prize.reserved_quantity:
        raise InvalidRouteInputError(
            f"stock quantity {stock_quantity} is below the already "
            f"committed reservations ({prize.reserved_quantity})"
        )
    gamification_repositories.adjust_stock(session, prize, stock_quantity=stock_quantity)
    record_action(
        actor=actor,
        action="prize.stock_update",
        target=f"prize:{prize.id}",
        result="success",
        detail={"stockQuantity": stock_quantity},
    )
    return prize


def concede_prize(session: Session, *, actor: str, code: str, spot_id: int):
    """Register the physical prize concession against a single-use code
    (RF36/Q3): the stock guard runs FIRST (rowcount 0 → insufficient);
    the code flips unused → used exactly once in the same transaction
    (research R4); pickup spot must exist (Q3)."""
    code_row = gamification_repositories.find_code_by_value(session, code)
    if code_row is None:
        raise CodeMissingError("redemption code not found")
    if code_row.status != "unused":
        raise CodeAlreadyUsedError("redemption code has already been used")
    # pickup spot must be an active tourist spot (Q3; research R3)
    from passanorte_back.modules.tourist_spots.services import tourist_spots as spots_service

    try:
        spots_service.get_active_spot(session, spot_id)
    except spots_service.SpotMissingError as error:
        raise TouristSpotMissingError(f"tourist spot {spot_id} not found") from error

    if gamification_repositories.try_consume_stock(session, code_row.prize_id) != 1:
        raise PrizeStockInsufficientError("insufficient stock to concede the prize")
    if (
        gamification_repositories.claim_redemption_code(
            session, code_row.id, pickup_spot_id=spot_id, conceded_by=actor
        )
        != 1
    ):
        raise CodeAlreadyUsedError("redemption code has already been used")

    record_action(
        actor=actor,
        action="prize.concede",
        target=f"code:{code_row.code}",
        result="success",
        detail={"routeId": code_row.route_id, "pickupSpotId": spot_id},
    )
    return gamification_repositories.find_code_by_value(session, code)
