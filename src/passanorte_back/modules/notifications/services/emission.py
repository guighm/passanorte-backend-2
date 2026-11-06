"""Interest-notification emission (feature 015 — public service seam).

The notifications module's ONLY cross-module surface (FR-008/FR-016,
constitution rule 5): emitter modules call ``create_interest_notification``
— never write the notifications tables. Best-effort via SAVEPOINT
(``session.begin_nested()``): any failure rolls back ONLY the savepoint and
is logged; the emitter's item creation is never blocked or reverted
(FR-011, research R2). One notification per tourist×item is the DB unique
constraint + ``on_conflict_do_nothing`` (FR-009, research R3).

Text (title/description) is composed CENTRALLY here from the emitter's
item data (Q2): the per-type template map below is the single i18n seam
(RNF16 — a future translation table swaps this data, no code restructuring).
"""

import logging

from fastapi import HTTPException
from sqlalchemy.orm import Session

from passanorte_back.modules.notifications.repositories.notifications import (
    insert_notifications,
)
from passanorte_back.modules.notifications.repositories.subscriptions import (
    subscribed_tourist_ids_for_categories,
)

logger = logging.getLogger("passanorte.notifications")

DESCRIPTION_CAP = 200

# i18n seam (RNF16): per-type display labels — Portuguese-facing content
# stays Portuguese (constitution VII); a localization layer replaces this
# data map later.
_TYPE_LABELS: dict[str, str] = {
    "event": "evento",
    "spot": "ponto turístico",
    "route": "rota turística",
}

_TITLE_TEMPLATES: dict[str, str] = {
    "event": "Novo evento: {name}",
    "spot": "Novo ponto turístico: {name}",
    "route": "Nova rota turística: {name}",
}


def validate_item_type(item_type: str) -> str:
    """Catalog of emittable item types (FR-008; unknown → 422, contract §6)."""
    if item_type not in _TYPE_LABELS:
        raise HTTPException(
            status_code=422,
            detail=(f"Unknown item type '{item_type}' — expected one of {sorted(_TYPE_LABELS)}."),
        )
    return item_type


def compose_title(item_type: str, item_name: str) -> str:
    """Presentable title per item type (Q2; template map = i18n seam)."""
    return _TITLE_TEMPLATES[validate_item_type(item_type)].format(name=item_name)


def compose_description(item_type: str, item_description: str) -> str:
    """Emitter short description, capped to the documented limit (Q2)."""
    validate_item_type(item_type)
    return item_description[:DESCRIPTION_CAP]


def create_interest_notification(
    session: Session,
    *,
    item_type: str,
    item_id: int,
    item_name: str,
    item_description: str,
    category_keys: list[str],
) -> int:
    """Emission seam: notify every tourist subscribed to any category.

    Returns the number of tourists actually notified (0 = no match or the
    emission failed — best-effort, FR-011). Runs inside a SAVEPOINT so
    neither the caller's transaction nor this module's invariant rows are
    left in a broken state; a failure is a structured log line.
    """
    validate_item_type(item_type)  # contract validation escapes (422, T014)
    try:
        if not category_keys:
            return 0  # nothing can match (route without categories, Q3)
        tourist_ids = subscribed_tourist_ids_for_categories(session, category_keys=category_keys)
        if not tourist_ids:
            return 0  # edge case: no interested tourists (US2/AC5)
        with session.begin_nested():  # SAVEPOINT (research R2)
            rows = [
                {
                    "tourist_id": tourist_id,
                    "item_type": item_type,
                    "item_id": item_id,
                    "title": compose_title(item_type, item_name),
                    "description": compose_description(item_type, item_description),
                }
                for tourist_id in tourist_ids
            ]
            notified = insert_notifications(session, rows=rows)
        logger.info(
            "interest notification emitted (itemType=%s itemId=%s notified=%s)",
            item_type,
            item_id,
            notified,
        )
        return notified
    except Exception:  # noqa: BLE001 — emission must never block the emitter (FR-011)
        session.rollback()
        logger.exception(
            "best-effort interest notification FAILED "
            "(itemType=%s itemId=%s) — item creation is unaffected",
            item_type,
            item_id,
        )
        return 0
