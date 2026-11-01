"""Tourist interests persistence (data-model.md §2; module tourists).

One row per selected category; unique ``(tourist_id, category_key)``;
FK → ``tourists.id`` with ON DELETE CASCADE. Writes replace the selection
wholesale (delete+insert in one transaction — FR-010); reads filter by the
currently configured categories (orphan categories omitted, edge case of
the spec).
"""

from sqlalchemy import ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, Session, mapped_column

from passanorte_back.core.db import Base
from passanorte_back.modules.tourists.repositories.tourists import (  # noqa: F401
    Tourist,
)

CATEGORY_KEY_LENGTH = 100


class TouristInterest(Base):
    """One category of the tourist's interest selection (RF25)."""

    __tablename__ = "tourist_interests"
    __table_args__ = (UniqueConstraint("tourist_id", "category_key", name="uq_tourist_interests"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    tourist_id: Mapped[int] = mapped_column(
        ForeignKey("tourists.id", ondelete="CASCADE"), index=True
    )
    category_key: Mapped[str] = mapped_column(String(CATEGORY_KEY_LENGTH))


def list_for_tourist(session: Session, tourist_id: int) -> list[str]:
    """All selected keys of a tourist, in insert order."""
    rows = (
        session.query(TouristInterest)
        .filter(TouristInterest.tourist_id == tourist_id)
        .order_by(TouristInterest.id)
        .all()
    )
    return [row.category_key for row in rows]


def replace_selection(session: Session, tourist_id: int, category_keys: list[str]) -> None:
    """Replace the whole selection (delete+insert in the SAME transaction —
    FR-010/s3-Q1). Keys must be validated (against configuration) by the
    service BEFORE calling."""
    session.query(TouristInterest).filter(TouristInterest.tourist_id == tourist_id).delete()
    for key in category_keys:
        session.add(TouristInterest(tourist_id=tourist_id, category_key=key))
