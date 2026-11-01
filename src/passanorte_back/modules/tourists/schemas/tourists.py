"""DTOs of the ``tourists`` module (contracts/tourists.md; T010/T019).

Request schemas carry field validators with the exact rules (research R6);
responses NEVER expose a ``*_encrypted``/``*_lookup`` column or
``password_hash`` (SC-005) — registration returns only the non-sensitive
identity (contract) and the profile returns decrypted values ONLY to
self/admin (controlled decryption — FR-006).
"""

from typing import Annotated

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator, model_validator

from passanorte_back.modules.tourists.schemas import field_rules


class TouristCreateRequest(BaseModel):
    """POST /tourists request (RF22; FR-001 — exactly one document)."""

    model_config = ConfigDict(extra="forbid")

    first_name: Annotated[str, Field(min_length=1, max_length=field_rules.TEXT_MAX_LENGTH)]
    last_name: Annotated[str, Field(min_length=1, max_length=field_rules.TEXT_MAX_LENGTH)]
    country_of_origin: Annotated[str, Field(min_length=1, max_length=field_rules.TEXT_MAX_LENGTH)]
    cpf: str | None = None
    passport_number: str | None = None
    phone: str
    email: EmailStr
    password: Annotated[str, Field(min_length=field_rules.MIN_PASSWORD_LENGTH, max_length=200)]

    @field_validator("first_name", "last_name", "country_of_origin")
    @classmethod
    def _validate_text(cls, value: str, info) -> str:
        return field_rules.validate_text_length(value, field=str(info.field_name).replace("_", " "))

    @field_validator("cpf")
    @classmethod
    def _validate_cpf(cls, value: str | None) -> str | None:
        return None if value is None else field_rules.validate_cpf_value(value)

    @field_validator("passport_number")
    @classmethod
    def _validate_passport(cls, value: str | None) -> str | None:
        return None if value is None else field_rules.validate_passport_value(value)

    @field_validator("phone")
    @classmethod
    def _validate_phone(cls, value: str) -> str:
        return field_rules.validate_phone_value(value)

    @field_validator("email")
    @classmethod
    def _normalize_email(cls, value: str) -> str:
        return field_rules.normalize_email(value)

    @model_validator(mode="after")
    def _exactly_one_document(self) -> "TouristCreateRequest":
        """Exactly one of cpf/passport_number (FR-001)."""
        documents = [self.cpf is not None, self.passport_number is not None]
        if sum(documents) != 1:
            raise ValueError("exactly one document (cpf or passport_number) is required")
        return self


class TouristLoginRequest(BaseModel):
    """POST /tourists/login request (RF23 — email is the credential)."""

    model_config = ConfigDict(extra="forbid")

    email: EmailStr
    password: Annotated[str, Field(min_length=1, max_length=200)]

    @field_validator("email")
    @classmethod
    def _normalize_email(cls, value: str) -> str:
        return field_rules.normalize_email(value)


class TouristSessionResponse(BaseModel):
    """Session pair of the tourist — same shape as the foundation's
    SessionResponse (contract) but owned by this module (no private
    cross-import — constitution rule 3)."""

    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int
    role: str


class TouristRegistered(BaseModel):
    """201 response: registration confirmation without sensitive values."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    first_name: str
    last_name: str
    country_of_origin: str


class TouristProfileResponse(BaseModel):
    """GET profile response (self/admin — controlled decryption, FR-006).

    Decrypted sensitive values appear ONLY here; never ``*_encrypted``/
    ``*_lookup``/``password_hash``. ``interests`` only contains currently
    configured categories (orphan categories omitted — spec edge case).
    """

    id: int
    first_name: str
    last_name: str
    country_of_origin: str
    email: str
    phone: str
    cpf: str | None
    passport_number: str | None
    interests: list[str]


class TouristUpdateRequest(BaseModel):
    """PATCH /tourists/{id} request — partial, no password field (out of
    scope); same field validations as the registration (contract)."""

    model_config = ConfigDict(extra="forbid")

    first_name: (
        Annotated[str, Field(min_length=1, max_length=field_rules.TEXT_MAX_LENGTH)] | None
    ) = None
    last_name: (
        Annotated[str, Field(min_length=1, max_length=field_rules.TEXT_MAX_LENGTH)] | None
    ) = None
    country_of_origin: (
        Annotated[str, Field(min_length=1, max_length=field_rules.TEXT_MAX_LENGTH)] | None
    ) = None
    phone: str | None = None
    email: EmailStr | None = None
    cpf: str | None = None
    passport_number: str | None = None

    @field_validator("first_name", "last_name", "country_of_origin")
    @classmethod
    def _validate_text(cls, value: str | None, info) -> str | None:
        if value is None:
            return None
        return field_rules.validate_text_length(value, field=str(info.field_name).replace("_", " "))

    @field_validator("cpf")
    @classmethod
    def _validate_cpf(cls, value: str | None) -> str | None:
        return None if value is None else field_rules.validate_cpf_value(value)

    @field_validator("passport_number")
    @classmethod
    def _validate_passport(cls, value: str | None) -> str | None:
        return None if value is None else field_rules.validate_passport_value(value)

    @field_validator("phone")
    @classmethod
    def _validate_phone(cls, value: str | None) -> str | None:
        return None if value is None else field_rules.validate_phone_value(value)

    @field_validator("email")
    @classmethod
    def _normalize_email(cls, value: str | None) -> str | None:
        return None if value is None else field_rules.normalize_email(value)


class InterestCategory(BaseModel):
    """One configured category (RNF06 — key/label from location.json)."""

    key: str
    label: str


class InterestCategoriesResponse(BaseModel):
    """GET /interest-categories — exactly the configured categories."""

    categories: list[InterestCategory]


class TouristInterestsResponse(BaseModel):
    """GET/PUT /me/interests — currently configured selection (no orphans,
    no duplicates)."""

    interests: list[str]


class TouristInterestsUpdateRequest(BaseModel):
    """PUT /me/interests — the WHOLE selection (FR-010); keys validated
    against the configuration (422 naming the invalid one — FR-011)."""

    model_config = ConfigDict(extra="forbid")

    interests: Annotated[list[str], Field(min_length=0)]

    @field_validator("interests")
    @classmethod
    def _normalize_keys(cls, value: list[str]) -> list[str]:
        normalized: list[str] = []
        for key in value:
            if not isinstance(key, str) or not key.strip():
                raise ValueError("interests entries must be non-empty strings")
            if key not in normalized:
                normalized.append(key)
        return normalized


__all__ = [
    "InterestCategoriesResponse",
    "InterestCategory",
    "TouristCreateRequest",
    "TouristInterestsResponse",
    "TouristInterestsUpdateRequest",
    "TouristLoginRequest",
    "TouristProfileResponse",
    "TouristRegistered",
    "TouristSessionResponse",
    "TouristUpdateRequest",
]
