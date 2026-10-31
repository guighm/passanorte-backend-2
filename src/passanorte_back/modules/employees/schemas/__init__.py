"""Schemas of the ``employees`` module (contracts/employees.md).

``initial_password`` appears EXCLUSIVELY in EmployeeCreatedResponse (one
time view — clar. Q3-s4); EmployeeView (list/detail/updates) carries no
credential field at all.
"""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class EmployeeCreateRequest(BaseModel):
    """POST /employees — no password field by design (system-generated)."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=200)
    username: str = Field(min_length=3, max_length=100)


class EmployeeView(BaseModel):
    """Listing/detail/update view — no credentials (contracts/employees.md)."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    username: str
    status: str
    created_at: object  # datetime ISO (Pydantic serializes)
    updated_at: object


class EmployeeCreatedResponse(EmployeeView):
    """CREATE response: adds the one-time initial password (Q3-s4)."""

    initial_password: str


class EmployeeListResponse(BaseModel):
    items: list[EmployeeView]
    total: int


class EmployeeUpdateRequest(BaseModel):
    """PATCH /employees/{id} — reactivation only via status=active."""

    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, min_length=1, max_length=200)
    username: str | None = Field(default=None, min_length=3, max_length=100)
    status: Literal["active"] | None = None
