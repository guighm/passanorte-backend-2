"""Shared HTTP contract schemas (spec 005, FR-005/FR-008).

Every HTTP-bound Pydantic schema in every module MUST inherit ``ApiModel``
(FR-008 — inherited by construction, no opt-out). The conversion to and
from JSON happens only at the HTTP border: Python attributes stay snake_case
(PEP 8, FR-002) while JSON keys are camelCase with full-lowercase acronym
folding (`user_cpf` -> ``userCpf``, clarification Q2).

Strictness (FR-003): ``extra="forbid"`` rejects unknown keys and — because
``populate_by_name`` is left disabled — snake_case input keys are *not*
accepted; both surface as 422 through the unified error handlers in
``core.error_handlers``.

``ApiError`` is the single unified error payload for every failure path
(clarification Q1 / FR-005): PascalCase DTO names, camelCase properties,
documented in the OpenAPI document exactly as delivered.
"""

from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel


class ApiModel(BaseModel):
    """Base for all HTTP-bound schemas: camelCase JSON, strict input.

    The HTTP border validates parsed JSON bodies strictly: ``populate_by_name``
    is NOT enabled (research.md R1), so snake_case keys are rejected with
    ``extra_forbidden``/``missing`` and surface as 422 through the unified
    error handlers in ``core.error_handlers``.

    Python code constructs instances with PEP 8 snake_case keywords via
    ``from_internal`` (FR-002) — an ``__init__`` override would leak into
    ``model_validate`` in Pydantic 2.x and break border strictness.
    """

    model_config = ConfigDict(
        alias_generator=to_camel,
        # strict border: unknown keys AND snake_case keys are rejected
        # (populate_by_name intentionally NOT enabled — research.md R1).
        extra="forbid",
    )

    @classmethod
    def from_internal(cls, **fields) -> "ApiModel":
        """Construct from internal snake_case keywords (FR-002).

        Maps each keyword ``name`` to its camelCase alias before real
        validation; values are never touched, only key spellings move.
        """
        return cls(**{to_camel(name): value for name, value in fields.items()})


class ApiErrorKeyDetails(ApiModel):
    """One offending key of a rejected (or failed) request.

    ``key`` carries the key as received (a JSON string value — exempt from
    casing checks, spec assumption); ``message`` says why it was rejected.
    """

    key: str
    message: str


class ApiError(ApiModel):
    """Unified error payload for all endpoints (FR-005).

    ``errorCode`` ↔ status mapping lives in ``contracts/camelcase-json.md``
    §2 (single source of truth); ``details`` is empty when not applicable
    (e.g. plain 401, 500 — which never leaks internals, constitution II).
    """

    errorCode: str
    message: str
    details: list[ApiErrorKeyDetails] = []
