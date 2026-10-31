"""Schemas of the ``auth`` module (contracts/auth.md).

The bootstrap input is never a HTTP schema (env-only — FR-002). No schema
exposes a password; the bootstrap summary carries only account state.
"""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class LoginRequest(BaseModel):
    """POST /login request body (username + password credentials)."""

    model_config = ConfigDict(extra="forbid")

    username: str = Field(min_length=1, max_length=100)
    password: str = Field(min_length=1, max_length=200)


class RefreshRequest(BaseModel):
    """POST /refresh request body (the current refresh credential)."""

    model_config = ConfigDict(extra="forbid")

    refresh_token: str = Field(min_length=10, max_length=255)


class SessionResponse(BaseModel):
    """Credential pair issued by /login or /refresh (clar. Q1) + role."""

    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int
    role: str


class CurrentUserResponse(BaseModel):
    """GET /me response: authenticated identity (US3 / T021)."""

    username: str
    role: str


class AdminAccountStatus(BaseModel):
    """Bootstrap result summary — never a password (RF01/RNF10)."""

    model_config = ConfigDict(from_attributes=True)

    username: str
    role: str = "admin"
    is_active: bool
    created: bool
    updated_at: datetime | None = None
