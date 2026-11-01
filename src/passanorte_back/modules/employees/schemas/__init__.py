"""Schemas of the ``employees`` module (contracts/employees.md).

``initial_password`` appears EXCLUSIVELY in EmployeeCreatedResponse (one
time view — clar. Q3-s4); EmployeeView (list/detail/updates) carries no
credential field at all.

All schemas inherit the shared ``ApiModel`` (spec 005 FR-008): JSON keys
are camelCase (`initialPassword`, `createdAt`, `updatedAt`), Python
attributes stay snake_case (PEP 8, FR-002).
"""

from typing import Literal

from pydantic import ConfigDict, Field

from passanorte_back.core.schemas import ApiModel


class EmployeeCreateRequest(ApiModel):
    """POST /employees — no password field by design (system-generated)."""

    name: str = Field(min_length=1, max_length=200)
    username: str = Field(min_length=3, max_length=100)


class EmployeeView(ApiModel):
    """Listing/detail/update view — no credentials (contracts/employees.md).

    ``populate_by_name`` is enabled for this RESPONSE-ONLY DTO so ORM
    attribute extraction (``from_attributes``) matches the snake_case
    column names; HTTP request strictness is unaffected (no request body
    ever validates against this model).
    """

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    id: int
    name: str
    username: str
    status: str
    created_at: object  # datetime ISO (Pydantic serializes)
    updated_at: object


class EmployeeCreatedResponse(EmployeeView):
    """CREATE response: adds the one-time initial password (Q3-s4)."""

    initial_password: str


class EmployeeListResponse(ApiModel):
    items: list[EmployeeView]
    total: int


class EmployeeUpdateRequest(ApiModel):
    """PATCH /employees/{id} — reactivation only via status=active."""

    name: str | None = Field(default=None, min_length=1, max_length=200)
    username: str | None = Field(default=None, min_length=3, max_length=100)
    status: Literal["active"] | None = None
