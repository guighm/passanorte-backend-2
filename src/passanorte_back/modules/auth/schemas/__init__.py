"""Schemas of the ``auth`` module (contracts/auth.md).

The bootstrap input is never a HTTP schema (env-only — FR-002). No schema
exposes a password; the bootstrap summary carries only account state.

All schemas inherit the shared ``ApiModel`` (spec 005 FR-008): JSON keys
are camelCase (`accessToken`, `refreshToken`, `expiresIn`, `isActive`,
`updatedAt`), Python attributes stay snake_case (PEP 8, FR-002).
"""

from datetime import datetime

from pydantic import ConfigDict, Field

from passanorte_back.core.schemas import ApiModel


class LoginRequest(ApiModel):
    """POST /login request body (username + password credentials)."""

    username: str = Field(min_length=1, max_length=100)
    password: str = Field(min_length=1, max_length=200)


class RefreshRequest(ApiModel):
    """POST /refresh request body (the current refresh credential)."""

    refresh_token: str = Field(min_length=10, max_length=255)


class SessionResponse(ApiModel):
    """Credential pair issued by /login or /refresh (clar. Q1) + role."""

    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int
    role: str


class CurrentUserResponse(ApiModel):
    """GET /me response: authenticated identity (US3 / T021)."""

    username: str
    role: str


class AdminAccountStatus(ApiModel):
    """Bootstrap result summary — never a password (RF01/RNF10)."""

    model_config = ConfigDict(from_attributes=True)

    username: str
    role: str = "admin"
    is_active: bool
    created: bool
    updated_at: datetime | None = None
