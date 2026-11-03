"""Gamification persistence (feature 009 data-model §1; gamification module).

The seven tables belong exclusively to the ``gamification`` domain.
``tourist_id``/``tourist_spot_id`` are read-only references into
``tourists``/``tourist_spots`` — written here only after the flows validated
the targets through those modules' public service interfaces (research R3).
Progress is derived at read time from ``spot_visits`` (research R1) — never
stored separately. ``spot_visits`` is gamification-owned for this feature;
the visitation module (spec 010) enters exclusively through
``register_spot_visit`` (research R1/R12).

No business rule lives here: services own every rule. The stock and
completion guards ARE data access — atomic conditional UPDATEs, whose
rowcount is the decision the services map (research R4/R2).
"""

from datetime import UTC, datetime
from typing import Final

from sqlalchemy import (
    CheckConstraint,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
    func,
    text,
    update,
)
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Mapped, Session, mapped_column, relationship

from passanorte_back.core.db import Base

NAME_LENGTH: Final[int] = 200
DESCRIPTION_LENGTH: Final[int] = 2000
STATUS_LENGTH: Final[int] = 20
CODE_LENGTH: Final[int] = 64

STATUS_IN_PROGRESS: Final[str] = "in_progress"  # storage; wire is "inProgress"
STATUS_COMPLETED: Final[str] = "completed"
CODE_STATUS_UNUSED: Final[str] = "unused"
CODE_STATUS_USED: Final[str] = "used"


def _utc_now() -> datetime:
    return datetime.now(UTC)


class Prize(Base):
    """A physical completion prize ("brinde") — catalog entity (Q1)."""

    __tablename__ = "prizes"
    __table_args__ = (
        CheckConstraint("stock_quantity >= 0", name="ck_prizes_stock_non_negative"),
        CheckConstraint("reserved_quantity >= 0", name="ck_prizes_reserved_non_negative"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(NAME_LENGTH))
    stock_quantity: Mapped[int] = mapped_column(Integer)
    reserved_quantity: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(default=_utc_now)
    updated_at: Mapped[datetime] = mapped_column(default=_utc_now, onupdate=_utc_now)


class TouristRoute(Base):
    """A gamified itinerary with a permanently bound prize (RF18, F1)."""

    __tablename__ = "tourist_routes"
    __table_args__ = (
        # Q1: one prize bound to at most one active route; binding is
        # permanent (created with the route — F1), so archived routes keep
        # pointing at their prize.
        Index(
            "uq_tourist_routes_active_prize",
            "prize_id",
            unique=True,
            sqlite_where=text("removed_at IS NULL"),
            postgresql_where=text("removed_at IS NULL"),
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(NAME_LENGTH))
    description: Mapped[str] = mapped_column(String(DESCRIPTION_LENGTH))
    prize_id: Mapped[int] = mapped_column(ForeignKey("prizes.id"))
    removed_at: Mapped[datetime | None] = mapped_column(index=True, default=None)
    created_at: Mapped[datetime] = mapped_column(default=_utc_now)
    updated_at: Mapped[datetime] = mapped_column(default=_utc_now, onupdate=_utc_now)

    prize: Mapped[Prize] = relationship()
    route_spots: Mapped[list["RouteSpot"]] = relationship(
        cascade="all, delete-orphan",
        order_by="RouteSpot.display_order",  # display order only (Q2)
    )


class RouteSpot(Base):
    """A spot's membership in a route with a display-order position (Q2)."""

    __tablename__ = "route_spots"
    __table_args__ = (UniqueConstraint("route_id", "tourist_spot_id", name="uq_route_spots"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    route_id: Mapped[int] = mapped_column(
        ForeignKey("tourist_routes.id", ondelete="CASCADE"), index=True
    )
    tourist_spot_id: Mapped[int] = mapped_column(ForeignKey("tourist_spots.id"))
    display_order: Mapped[int] = mapped_column(Integer)


class RouteEnrollment(Base):
    """The tourist's subscription to a route — unique per pair (FR-005)."""

    __tablename__ = "route_enrollments"
    __table_args__ = (UniqueConstraint("route_id", "tourist_id", name="uq_route_enrollments"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    route_id: Mapped[int] = mapped_column(ForeignKey("tourist_routes.id"), index=True)
    tourist_id: Mapped[int] = mapped_column(ForeignKey("tourists.id"), index=True)
    status: Mapped[str] = mapped_column(String(STATUS_LENGTH), default=STATUS_IN_PROGRESS)
    completed_at: Mapped[datetime | None] = mapped_column(default=None)
    created_at: Mapped[datetime] = mapped_column(default=_utc_now)


class SpotVisit(Base):
    """A recorded spot visit — idempotent per tourist-spot pair (R1)."""

    __tablename__ = "spot_visits"
    __table_args__ = (UniqueConstraint("tourist_id", "tourist_spot_id", name="uq_spot_visits"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    tourist_id: Mapped[int] = mapped_column(ForeignKey("tourists.id"))
    tourist_spot_id: Mapped[int] = mapped_column(ForeignKey("tourist_spots.id"))
    visited_at: Mapped[datetime] = mapped_column(default=_utc_now)


class CompletionBadge(Base):
    """The digital badge granted once per tourist-route completion (RF35)."""

    __tablename__ = "completion_badges"
    __table_args__ = (UniqueConstraint("route_id", "tourist_id", name="uq_completion_badges"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    route_id: Mapped[int] = mapped_column(ForeignKey("tourist_routes.id"), index=True)
    tourist_id: Mapped[int] = mapped_column(ForeignKey("tourists.id"), index=True)
    granted_at: Mapped[datetime] = mapped_column(default=_utc_now)


class RedemptionCode(Base):
    """The single-use prize redemption code issued once per completion (RF36)."""

    __tablename__ = "redemption_codes"
    __table_args__ = (
        UniqueConstraint("route_id", "tourist_id", name="uq_redemption_codes"),
        CheckConstraint("status IN ('unused', 'used')", name="ck_redemption_codes_status"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(CODE_LENGTH), unique=True, index=True)
    route_id: Mapped[int] = mapped_column(ForeignKey("tourist_routes.id"), index=True)
    tourist_id: Mapped[int] = mapped_column(ForeignKey("tourists.id"), index=True)
    prize_id: Mapped[int] = mapped_column(ForeignKey("prizes.id"))
    status: Mapped[str] = mapped_column(String(10), default=CODE_STATUS_UNUSED)
    created_at: Mapped[datetime] = mapped_column(default=_utc_now)
    used_at: Mapped[datetime | None] = mapped_column(default=None)
    pickup_spot_id: Mapped[int | None] = mapped_column(ForeignKey("tourist_spots.id"), default=None)
    conceded_by: Mapped[str | None] = mapped_column(String(150), default=None)


# ---
# Prizes — data access (stock rules themselves live at service level)
# ---


def create_prize(session: Session, *, name: str, stock_quantity: int) -> Prize:
    """Insert one prize (embedded in route creation — RF18)."""
    prize = Prize(name=name, stock_quantity=stock_quantity)
    session.add(prize)
    session.flush()
    return prize


def find_prize_by_id(session: Session, prize_id: int) -> Prize | None:
    return session.get(Prize, prize_id)


def adjust_stock(session: Session, prize: Prize, *, stock_quantity: int) -> Prize:
    """Set the new stock quantity (guard against < reserved stays in service)."""
    prize.stock_quantity = stock_quantity
    session.flush()
    return prize


def try_reserve_prize(session: Session, prize_id: int) -> int:
    """Atomic reservation guard (research R4): +1 reserved unit only when
    stock covers it. Rowcount 1 = reserved; 0 = no stock available."""
    result = session.execute(
        update(Prize)
        .where(
            Prize.id == prize_id,
            Prize.stock_quantity - Prize.reserved_quantity >= 1,
        )
        .values(reserved_quantity=Prize.reserved_quantity + 1)
    )
    session.flush()
    return int(getattr(result, "rowcount", 0) or 0)


def try_consume_stock(session: Session, prize_id: int) -> int:
    """Atomic concession guard (research R4): -1 stock only when stock
    exists; releases the held reservation if one exists. Rowcount 0 =
    insufficient stock."""
    result = session.execute(
        update(Prize)
        .where(Prize.id == prize_id, Prize.stock_quantity >= 1)
        .values(
            stock_quantity=Prize.stock_quantity - 1,
            reserved_quantity=func.max(Prize.reserved_quantity - 1, 0),
        )
    )
    session.flush()
    return int(getattr(result, "rowcount", 0) or 0)


# ---
# Tourist routes — data access
# ---


def add_route(session: Session, *, name: str, description: str, prize_id: int) -> TouristRoute:
    """Insert the route (prize already created/persisted)."""
    route = TouristRoute(name=name, description=description, prize_id=prize_id)
    session.add(route)
    session.flush()
    return route


def find_route_by_id(session: Session, route_id: int) -> TouristRoute | None:
    return session.get(TouristRoute, route_id)


def list_routes(session: Session, *, include_archived: bool = False) -> list[TouristRoute]:
    """Stable (name, id) order; archived routes only on explicit request."""
    query = session.query(TouristRoute)
    if not include_archived:
        query = query.filter(TouristRoute.removed_at.is_(None))
    return list(query.order_by(TouristRoute.name, TouristRoute.id).all())


def add_route_spot(
    session: Session, *, route_id: int, tourist_spot_id: int, display_order: int
) -> RouteSpot:
    spot = RouteSpot(
        route_id=route_id, tourist_spot_id=tourist_spot_id, display_order=display_order
    )
    session.add(spot)
    session.flush()
    return spot


def replace_route_spots(
    session: Session, route: TouristRoute, *, spot_ids: list[tuple[int, int]]
) -> None:
    """Replace the whole spots list (ordered (spot_id, display_order) entries)."""
    session.query(RouteSpot).filter(RouteSpot.route_id == route.id).delete()
    for spot_id, display_order in spot_ids:
        add_route_spot(
            session,
            route_id=route.id,
            tourist_spot_id=spot_id,
            display_order=display_order,
        )
    session.flush()


def archive_route(session: Session, route: TouristRoute, *, when: datetime) -> None:
    """Archive (soft delete) — enrollments/badges/codes stay untouched (FR-012)."""
    route.removed_at = when
    session.flush()


def count_route_spots(session: Session, route_id: int) -> int:
    return int(session.query(RouteSpot).filter(RouteSpot.route_id == route_id).count())


def list_route_spot_ids(session: Session, route_id: int) -> list[tuple[int, int]]:
    """(tourist_spot_id, display_order) in display order (progress payload)."""
    rows = (
        session.query(RouteSpot.tourist_spot_id, RouteSpot.display_order)
        .filter(RouteSpot.route_id == route_id)
        .order_by(RouteSpot.display_order, RouteSpot.id)
        .all()
    )
    return [(row[0], row[1]) for row in rows]


# ---
# Enrollments — data access
# ---


def add_enrollment(session: Session, *, route_id: int, tourist_id: int) -> RouteEnrollment:
    enrollment = RouteEnrollment(route_id=route_id, tourist_id=tourist_id)
    session.add(enrollment)
    session.flush()
    return enrollment


def find_enrollment(session: Session, *, route_id: int, tourist_id: int) -> RouteEnrollment | None:
    return (
        session.query(RouteEnrollment)
        .filter(RouteEnrollment.route_id == route_id, RouteEnrollment.tourist_id == tourist_id)
        .one_or_none()
    )


def find_enrollment_by_id(session: Session, enrollment_id: int) -> RouteEnrollment | None:
    return session.get(RouteEnrollment, enrollment_id)


def list_enrollments_of_tourist(session: Session, tourist_id: int) -> list[RouteEnrollment]:
    return list(
        session.query(RouteEnrollment)
        .filter(RouteEnrollment.tourist_id == tourist_id)
        .order_by(RouteEnrollment.created_at.desc(), RouteEnrollment.id.desc())
        .all()
    )


def list_in_progress_enrollments_for_spot(
    session: Session, *, tourist_id: int, tourist_spot_id: int
) -> list[RouteEnrollment]:
    """Every in-progress enrollment of the tourist on a route containing the
    spot (RF34 — one visit updates ALL matching enrollments; archived routes
    keep their in-progress enrollments, FR-012)."""
    return list(
        session.query(RouteEnrollment)
        .join(RouteSpot, RouteSpot.route_id == RouteEnrollment.route_id)
        .filter(
            RouteEnrollment.tourist_id == tourist_id,
            RouteEnrollment.status == STATUS_IN_PROGRESS,
            RouteSpot.tourist_spot_id == tourist_spot_id,
        )
        .all()
    )


def mark_enrollment_completed(session: Session, enrollment_id: int) -> int:
    """Conditional completion guard (research R2): rowcount 1 = this call
    completed the enrollment (the rewards issuer); 0 = already completed."""
    result = session.execute(
        update(RouteEnrollment)
        .where(
            RouteEnrollment.id == enrollment_id,
            RouteEnrollment.status == STATUS_IN_PROGRESS,
        )
        .values(status=STATUS_COMPLETED, completed_at=_utc_now())
    )
    session.flush()
    return int(getattr(result, "rowcount", 0) or 0)


# ---
# Spot visits — data access
# ---


def record_visit(
    session: Session, *, tourist_id: int, tourist_spot_id: int
) -> tuple[SpotVisit, bool]:
    """Idempotent insert-or-lookup per tourist-spot pair (spec edge case).

    Returns ``(visit, created)`` — ``created`` False when the visit already
    existed (a re-registration is a no-op).
    """
    existing = (
        session.query(SpotVisit)
        .filter(
            SpotVisit.tourist_id == tourist_id,
            SpotVisit.tourist_spot_id == tourist_spot_id,
        )
        .one_or_none()
    )
    if existing is not None:
        return existing, False
    try:
        visit = SpotVisit(tourist_id=tourist_id, tourist_spot_id=tourist_spot_id)
        session.add(visit)
        session.flush()
        return visit, True
    except IntegrityError:
        session.rollback()
        visit = (
            session.query(SpotVisit)
            .filter(
                SpotVisit.tourist_id == tourist_id,
                SpotVisit.tourist_spot_id == tourist_spot_id,
            )
            .one()
        )
        return visit, False


def find_visited_spot_ids(session: Session, *, tourist_id: int, spot_ids: list[int]) -> set[int]:
    """Visited ids among the given candidates (progress derivation, R1)."""
    if not spot_ids:
        return set()
    rows = (
        session.query(SpotVisit.tourist_spot_id)
        .filter(
            SpotVisit.tourist_id == tourist_id,
            SpotVisit.tourist_spot_id.in_(spot_ids),
        )
        .all()
    )
    return {row[0] for row in rows}


# ---
# Badges and redemption codes — data access
# ---


def find_badge(session: Session, *, route_id: int, tourist_id: int) -> CompletionBadge | None:
    return (
        session.query(CompletionBadge)
        .filter(
            CompletionBadge.route_id == route_id,
            CompletionBadge.tourist_id == tourist_id,
        )
        .one_or_none()
    )


def grant_badge(session: Session, *, route_id: int, tourist_id: int) -> CompletionBadge:
    """Idempotent lookup-first badge grant (RF35 — exactly one per pair)."""
    badge = find_badge(session, route_id=route_id, tourist_id=tourist_id)
    if badge is not None:
        return badge
    badge = CompletionBadge(route_id=route_id, tourist_id=tourist_id)
    session.add(badge)
    session.flush()
    return badge


def add_code(
    session: Session, *, code: str, route_id: int, tourist_id: int, prize_id: int
) -> RedemptionCode:
    redemption = RedemptionCode(
        code=code, route_id=route_id, tourist_id=tourist_id, prize_id=prize_id
    )
    session.add(redemption)
    session.flush()
    return redemption


def find_code_by_value(session: Session, code: str) -> RedemptionCode | None:
    return session.query(RedemptionCode).filter(RedemptionCode.code == code).one_or_none()


def exists_code_value(session: Session, code: str) -> bool:
    return session.query(RedemptionCode.id).filter(RedemptionCode.code == code).first() is not None


def claim_redemption_code(
    session: Session,
    code_id: int,
    *,
    pickup_spot_id: int,
    conceded_by: str,
) -> int:
    """Conditional single-use claim (research R2/R4): flips the code to
    ``used`` only when still unused — rowcount 1 = claimed; 0 = already used
    (caller runs the stock guard first, so a refused claim rolls nothing)."""
    result = session.execute(
        update(RedemptionCode)
        .where(
            RedemptionCode.id == code_id,
            RedemptionCode.status == CODE_STATUS_UNUSED,
        )
        .values(
            status=CODE_STATUS_USED,
            used_at=_utc_now(),
            pickup_spot_id=pickup_spot_id,
            conceded_by=conceded_by,
        )
    )
    session.flush()
    return int(getattr(result, "rowcount", 0) or 0)


def find_code_for_owner(
    session: Session, *, route_id: int, tourist_id: int
) -> RedemptionCode | None:
    """The completion code of a tourist-route pair (progress payload)."""
    return (
        session.query(RedemptionCode)
        .filter(
            RedemptionCode.route_id == route_id,
            RedemptionCode.tourist_id == tourist_id,
        )
        .one_or_none()
    )


def list_in_progress_enrollments_of_route(session: Session, route_id: int) -> list[RouteEnrollment]:
    """In-progress enrollments of one route (post-edit re-evaluation,
    Edge Cases 1 — the route-removal rule keeps these rows alive)."""
    return list(
        session.query(RouteEnrollment)
        .filter(RouteEnrollment.route_id == route_id, RouteEnrollment.status == STATUS_IN_PROGRESS)
        .all()
    )
