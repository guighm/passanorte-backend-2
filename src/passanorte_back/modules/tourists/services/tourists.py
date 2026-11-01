"""Registration and login flows of the ``tourists`` module (US1/US2).

- ``register_tourist``: encrypts the sensitive values via ``core.crypto``
  (Fernet ciphertext + keyed lookup hashes, context per field), checks
  uniqueness among tourists ONLY (clar. s1-Q1), persists the bcrypt password
  hash and audits ``tourist.register`` (RNF19).
- ``tourist_login``: normalizes the email, resolves by ``email_lookup``,
  verifies the bcrypt hash and issues the credential pair through the PUBLIC
  ``auth.services.issue_session`` (constitution rule 5) — FR-014 audit with
  a generic failure message (research R3).

No sensitive value is ever persisted in plaintext (RNF08/SC-005): the
repository receives ciphertext/lookup columns only.
"""

from typing import NamedTuple

from sqlalchemy.orm import Session

from passanorte_back.core.audit import record_action
from passanorte_back.core.crypto import decrypt_value, encrypt_value, lookup_hash
from passanorte_back.core.security import hash_password, verify_password
from passanorte_back.modules.auth.services.authentication import (
    InvalidCredentialsError,
    SessionTokens,
    issue_session,
)
from passanorte_back.modules.tourists.repositories.tourists import (
    Tourist,
    add_tourist,
    find_by_cpf_lookup,
    find_by_email_lookup,
    find_by_id,
    find_by_passport_lookup,
)

ROLE_TOURIST = "tourist"


class TouristAlreadyRegisteredError(Exception):
    """Email/cpf/passport already taken among tourists (route → 409)."""


class TouristMissingError(Exception):
    """Target tourist id does not exist (route → 404)."""


class TouristAccount(NamedTuple):
    """Account view consumed by the auth identity/session resolution
    (lazy-imported by ``auth`` — same pattern as ``employees.services``)."""

    account_id: int
    email: str  # normalized, decrypted here (controlled — SC-005)
    active: bool
    role: str


def _sensitive_key() -> bytes:
    from passanorte_back.core.config import get_settings

    return get_settings().sensitive_data_key.encode("utf-8")


def _lookup(value: str, *, context: str) -> str:
    """Keyed equality hash for a normalized value (research R1)."""
    return lookup_hash(value, context=context, key=_sensitive_key())


def _encrypt(value: str) -> str:
    return encrypt_value(value, _sensitive_key())


def decrypt_stored(ciphertext: str | None) -> str | None:
    """Controlled decryption of one stored value (services only — SC-005)."""
    if ciphertext is None:
        return None
    return decrypt_value(ciphertext, _sensitive_key())


def register_tourist(
    session: Session,
    *,
    first_name: str,
    last_name: str,
    country_of_origin: str,
    normalized_email: str,
    phone: str,
    password: str,
    cpf: str | None = None,
    passport_number: str | None = None,
) -> Tourist:
    """Create the tourist account (RF22).

    All inputs are ALREADY validated/normalized by the schema layer (cpf 11
    digits, passport format, phone ``+DDI``, email trim+lower). Raises
    ``TouristAlreadyRegisteredError`` when the email, cpf or passport
    lookup is already taken among tourists (FR-003/SC-002 → 409).
    """
    email_l = _lookup(normalized_email, context="email")
    cpf_l = _lookup(cpf, context="cpf") if cpf is not None else None
    passport_l = _lookup(passport_number, context="passport") if passport_number else None

    taken = (
        find_by_email_lookup(session, email_l) is not None
        or (cpf_l is not None and find_by_cpf_lookup(session, cpf_l) is not None)
        or (passport_l is not None and find_by_passport_lookup(session, passport_l) is not None)
    )
    if taken:
        record_action(
            actor=normalized_email,
            action="tourist.register",
            target="tourist",
            result="failure",
            detail={"reason": "duplicate"},
        )
        raise TouristAlreadyRegisteredError("tourist already registered")

    tourist = add_tourist(
        session,
        first_name=first_name,
        last_name=last_name,
        country_of_origin=country_of_origin,
        email_encrypted=_encrypt(normalized_email),
        email_lookup=email_l,
        phone_encrypted=_encrypt(phone),
        cpf_encrypted=_encrypt(cpf) if cpf is not None else None,
        cpf_lookup=cpf_l,
        passport_encrypted=_encrypt(passport_number) if passport_number else None,
        passport_lookup=passport_l,
        password_hash=hash_password(password),
    )
    record_action(
        actor=normalized_email,
        action="tourist.register",
        target=f"tourist:{tourist.id}",
        result="success",
    )
    return tourist


def tourist_login(session: Session, *, email: str, password: str) -> SessionTokens:
    """Authenticate a tourist by email+password (RF23 — T015).

    ``email`` arrives at least schema-valid; normalized here again
    (trim+casefold — FR-013). Failure is audited with a GENERIC message
    that never distinguishes cause (FR-014/research R3); success issues
    the pair through the public auth ``issue_session`` (rule 5).
    """
    normalized = email.strip().casefold()
    tourist = find_by_email_lookup(session, _lookup(normalized, context="email"))
    if tourist is None or not verify_password(password, tourist.password_hash):
        record_action(
            actor=normalized,
            action="tourist.login.failure",
            target="tourist",
            result="failure",
            detail={"reason": "invalid credentials"},
        )
        raise InvalidCredentialsError("invalid credentials")

    tokens = issue_session(
        session,
        account_type="tourist",
        account_id=tourist.id,
        role=ROLE_TOURIST,
    )
    record_action(
        actor=normalized,
        action="tourist.login.success",
        target=f"tourist:{tourist.id}",
        result="success",
        detail={"role": ROLE_TOURIST, "account_type": "tourist"},
    )
    return tokens


def get_tourist_account(session: Session, tourist_id: int) -> TouristAccount | None:
    """Account-by-id view for the auth identity/refresh resolution (T017)."""
    tourist = find_by_id(session, tourist_id)
    if tourist is None:
        return None
    return TouristAccount(
        account_id=tourist.id,
        email=decrypt_stored(tourist.email_encrypted) or "",
        active=True,  # no deactivation flow in this feature (YAGNI — spec)
        role=ROLE_TOURIST,
    )
