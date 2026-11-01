"""Tourist account persistence (data-model.md §1; module tourists).

The table and its data access belong exclusively to the ``tourists`` domain.
Columns for sensitive values are the ENCRYPTED forms (``*_encrypted``) plus
keyed-hash lookup sisters (``*_lookup``) for equality/uniqueness —
no repository function decrypts or receives plaintext (SC-005):
decryption is controlled and lives only in ``services``.
"""

from datetime import UTC, datetime

from sqlalchemy import String
from sqlalchemy.orm import Mapped, Session, mapped_column

from passanorte_back.core.db import Base

NAME_LENGTH = 100
LOOKUP_LENGTH = 64


class Tourist(Base):
    """Tourist account of the Passaporte app (data-model.md §1)."""

    __tablename__ = "tourists"

    id: Mapped[int] = mapped_column(primary_key=True)
    first_name: Mapped[str] = mapped_column(String(NAME_LENGTH))
    last_name: Mapped[str] = mapped_column(String(NAME_LENGTH))
    country_of_origin: Mapped[str] = mapped_column(String(NAME_LENGTH))
    email_encrypted: Mapped[str] = mapped_column(String())
    email_lookup: Mapped[str] = mapped_column(String(LOOKUP_LENGTH), unique=True, index=True)
    phone_encrypted: Mapped[str] = mapped_column(String())
    cpf_encrypted: Mapped[str | None] = mapped_column(String(), nullable=True)
    cpf_lookup: Mapped[str | None] = mapped_column(
        String(LOOKUP_LENGTH), nullable=True, unique=True, index=True
    )
    passport_encrypted: Mapped[str | None] = mapped_column(String(), nullable=True)
    passport_lookup: Mapped[str | None] = mapped_column(
        String(LOOKUP_LENGTH), nullable=True, unique=True, index=True
    )
    password_hash: Mapped[str] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(default=lambda: datetime.now(UTC))
    updated_at: Mapped[datetime] = mapped_column(
        default=lambda: datetime.now(UTC), onupdate=lambda: datetime.now(UTC)
    )


def add_tourist(
    session: Session,
    *,
    first_name: str,
    last_name: str,
    country_of_origin: str,
    email_encrypted: str,
    email_lookup: str,
    phone_encrypted: str,
    cpf_encrypted: str | None,
    cpf_lookup: str | None,
    passport_encrypted: str | None,
    passport_lookup: str | None,
    password_hash: str,
) -> Tourist:
    """Persist a new tourist from already-encrypted/normalized columns."""
    tourist = Tourist(
        first_name=first_name,
        last_name=last_name,
        country_of_origin=country_of_origin,
        email_encrypted=email_encrypted,
        email_lookup=email_lookup,
        phone_encrypted=phone_encrypted,
        cpf_encrypted=cpf_encrypted,
        cpf_lookup=cpf_lookup,
        passport_encrypted=passport_encrypted,
        passport_lookup=passport_lookup,
        password_hash=password_hash,
    )
    session.add(tourist)
    session.flush()
    return tourist


def find_by_id(session: Session, tourist_id: int) -> Tourist | None:
    return session.get(Tourist, tourist_id)


def find_by_email_lookup(session: Session, email_lookup: str) -> Tourist | None:
    return session.query(Tourist).filter(Tourist.email_lookup == email_lookup).first()


def find_by_cpf_lookup(session: Session, cpf_lookup: str) -> Tourist | None:
    return session.query(Tourist).filter(Tourist.cpf_lookup == cpf_lookup).first()


def find_by_passport_lookup(session: Session, passport_lookup: str) -> Tourist | None:
    return session.query(Tourist).filter(Tourist.passport_lookup == passport_lookup).first()


def find_other_lookup_holder(
    session: Session,
    *,
    column_lookup: str,
    value: str | None,
    except_id: int,
) -> Tourist | None:
    """Another tourist (id != ``except_id``) already holding the lookup value."""
    if value is None:
        return None
    query = session.query(Tourist).filter(getattr(Tourist, column_lookup) == value)
    return query.filter(Tourist.id != except_id).first()
