"""Subscription services of the notifications module (feature 015, RF37).

The tourist's own notification-channel selection (Q1 — independent of the
profile interests, FR-007): replace-whole-selection with catalog
validation (same pattern as the profile interests of spec 003), idempotent
per key (unique constraint) and idempotent cancel (FR-006). The catalog is
the city configuration (RNF06) — zero city values in code.
"""

from fastapi import HTTPException
from sqlalchemy.orm import Session

from passanorte_back.core.config import get_settings
from passanorte_back.modules.notifications.repositories.subscriptions import (
    add_subscription,
    delete_subscription,
    delete_subscriptions_not_in,
    keys_for_tourist,
)


def _validate_catalog(category_keys: list[str]) -> list[str]:
    """Validated, order-preserving selection (FR-005; 422 names the key)."""
    catalog = {category["key"] for category in get_settings().resolved_interest_categories()}
    ordered: list[str] = []
    for key in category_keys:
        if key not in catalog:
            raise HTTPException(
                status_code=422,
                detail=f"Unknown interest category '{key}'.",
            )
        if key not in ordered:
            ordered.append(key)
    return ordered


def replace_subscriptions(
    session: Session, *, tourist_id: int, category_keys: list[str]
) -> list[str]:
    """Replace the WHOLE selection (FR-004) with validated, deduped keys."""
    valid_keys = _validate_catalog(category_keys)
    delete_subscriptions_not_in(session, tourist_id=tourist_id, keep_keys=valid_keys)
    current = set(keys_for_tourist(session, tourist_id=tourist_id))
    for key in valid_keys:
        if key not in current:  # idempotent by unique constraint (FR-005)
            add_subscription(session, tourist_id=tourist_id, category_key=key)
    return keys_for_tourist(session, tourist_id=tourist_id)


def list_subscriptions(session: Session, *, tourist_id: int) -> list[str]:
    """Current selection (contracts §1)."""
    return keys_for_tourist(session, tourist_id=tourist_id)


def cancel_subscription(session: Session, *, tourist_id: int, category_key: str) -> list[str]:
    """Idempotent cancel of one category (FR-006): a non-subscribed valid
    key is not an error — the state ends 'not subscribed' either way."""
    _validate_catalog([category_key])
    delete_subscription(session, tourist_id=tourist_id, category_key=category_key)
    return keys_for_tourist(session, tourist_id=tourist_id)
