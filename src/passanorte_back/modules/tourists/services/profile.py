"""Profile flows (view/edit) of the ``tourists`` module (US3 — RF24).

- ``get_tourist_profile``: controlled decryption (services only — SC-005);
  ``interests`` filtered by the currently configured categories.
- ``update_tourist_profile``: PATCH semantics — every present field is
  revalidated/normalized (schema already applied the per-field rules); a
  document field sent with a value REPLACES the document pair (swap);
  removing the last document → 422; uniqueness revalidated among tourists →
  409; audit ``tourist.profile.update`` (FR-008, contract PATCH rules).

Permission (self-or-admin) is enforced before calling the service routes:
a tourist touching a third party gets ``ProfileForbiddenError`` (→ 403
without leaking existence — SC-004).
"""

from sqlalchemy.orm import Session

from passanorte_back.core.audit import record_action
from passanorte_back.modules.tourists.repositories.tourist_interests import (
    list_for_tourist,
)
from passanorte_back.modules.tourists.repositories.tourists import (
    Tourist,
    find_by_id,
    find_other_lookup_holder,
)
from passanorte_back.modules.tourists.schemas.tourists import (
    TouristProfileResponse,
    TouristUpdateRequest,
)
from passanorte_back.modules.tourists.services.tourists import (
    TouristMissingError,
    _encrypt,
    _lookup,
    decrypt_stored,
)


class ProfileForbiddenError(Exception):
    """Authenticated tourist is not the target and not admin (→ 403)."""


class ProfileValidationError(Exception):
    """Edit would leave the tourist without a document (→ 422)."""


class ProfileConflictError(Exception):
    """Uniqueness collision in the edit (→ 409)."""


def tourist_or_forbid(session: Session, *, requester, tourist_id: int) -> Tourist:
    """Self-or-admin permission surface shared by the profile routes (T021).

    ``requester`` is the auth ``AuthenticatedUser`` view. A tourist touching
    a foreign target → 403 BEFORE the existence check (SC-004 — no leak);
    admin/self with a missing target → 404.
    """
    from passanorte_back.modules.auth.services.security import AuthenticatedUser

    assert isinstance(requester, AuthenticatedUser)
    if requester.account_type not in ("tourist", "admin"):
        raise ProfileForbiddenError("insufficient permissions")
    if requester.account_type == "tourist" and requester.account_id != tourist_id:
        raise ProfileForbiddenError("insufficient permissions")
    tourist = find_by_id(session, tourist_id)
    if tourist is None:
        raise TouristMissingError("tourist not found")
    return tourist


def configured_keys() -> list[str]:
    """Currently configured interest keys (RNF06 — location data)."""
    from passanorte_back.core.config import get_settings

    return [item["key"] for item in get_settings().resolved_interest_categories()]


def get_tourist_profile(session: Session, tourist: Tourist) -> TouristProfileResponse:
    """Full profile view with controlled decryption (self/admin only).

    ``interests`` only lists currently configured categories (orphans
    omitted — edge case of the spec); repositories never decrypt (SC-005).
    """
    configured = set(configured_keys())
    interests = [key for key in list_for_tourist(session, tourist.id) if key in configured]
    return TouristProfileResponse(
        id=tourist.id,
        first_name=tourist.first_name,
        last_name=tourist.last_name,
        country_of_origin=tourist.country_of_origin,
        email=decrypt_stored(tourist.email_encrypted) or "",
        phone=decrypt_stored(tourist.phone_encrypted) or "",
        cpf=decrypt_stored(tourist.cpf_encrypted),
        passport_number=decrypt_stored(tourist.passport_encrypted),
        interests=interests,
    )


def update_tourist_profile(
    session: Session, *, tourist: Tourist, payload: TouristUpdateRequest, actor: str
) -> None:
    """Partial edit (RF24; contract PATCH rules).

    The schema layer already validated/normalized the fields present.
    Document fields: any mutation replaces the pair — a value sent takes
    the place of BOTH documents (XOR must survive the edit — FR-001).
    """
    sent = payload.model_fields_set
    touched_cpf = "cpf" in sent
    touched_passport = "passport_number" in sent

    sent_cpf = payload.cpf if touched_cpf else None
    sent_passport = payload.passport_number if touched_passport else None

    if touched_cpf and touched_passport:
        # Explicit two-key document edit: XOR applies to the SENT VALUES.
        if sent_cpf is not None and sent_passport is not None:
            raise ProfileValidationError("exactly one document must be provided")
        if sent_cpf is None and sent_passport is None:
            raise ProfileValidationError(
                "the profile must keep exactly one document (cpf or passport_number)"
            )

    if sent_cpf is not None:  # sent value REPLACES the pair (swap)
        cpf_l = _lookup(sent_cpf, context="cpf")
        if (
            find_other_lookup_holder(
                session, column_lookup="cpf_lookup", value=cpf_l, except_id=tourist.id
            )
            is not None
        ):
            raise ProfileConflictError("tourist already registered")
        tourist.cpf_encrypted = _encrypt(sent_cpf)
        tourist.cpf_lookup = cpf_l
        tourist.passport_encrypted = None
        tourist.passport_lookup = None
    elif touched_passport and sent_passport is not None:
        passport_l = _lookup(sent_passport, context="passport")
        if (
            find_other_lookup_holder(
                session,
                column_lookup="passport_lookup",
                value=passport_l,
                except_id=tourist.id,
            )
            is not None
        ):
            raise ProfileConflictError("tourist already registered")
        tourist.passport_encrypted = _encrypt(sent_passport)
        tourist.passport_lookup = passport_l
        tourist.cpf_encrypted = None
        tourist.cpf_lookup = None
    elif touched_cpf or touched_passport:
        # Explicit removal of one document: the other must survive the edit.
        removing_cpf = touched_cpf
        other_held = tourist.passport_lookup if removing_cpf else tourist.cpf_lookup
        if other_held is None:
            raise ProfileValidationError(
                "the profile must keep exactly one document (cpf or passport_number)"
            )
        if removing_cpf:
            tourist.cpf_encrypted = None
            tourist.cpf_lookup = None
        else:
            tourist.passport_encrypted = None
            tourist.passport_lookup = None

    if payload.email is not None:
        email_l = _lookup(payload.email, context="email")
        if (
            find_other_lookup_holder(
                session, column_lookup="email_lookup", value=email_l, except_id=tourist.id
            )
            is not None
        ):
            raise ProfileConflictError("tourist already registered")
        tourist.email_encrypted = _encrypt(payload.email)
        tourist.email_lookup = email_l

    if payload.first_name is not None:
        tourist.first_name = payload.first_name
    if payload.last_name is not None:
        tourist.last_name = payload.last_name
    if payload.country_of_origin is not None:
        tourist.country_of_origin = payload.country_of_origin
    if payload.phone is not None:
        tourist.phone_encrypted = _encrypt(payload.phone)

    record_action(
        actor=actor,
        action="tourist.profile.update",
        target=f"tourist:{tourist.id}",
        result="success",
        detail={
            "first_name": tourist.first_name,
            "last_name": tourist.last_name,
        },
    )
