"""Schemas of the ``tourists`` module (contracts/tourists.md).

Re-exports the DTO submodules (request/response contracts, field rules).
No schema exposes ``*_encrypted``/``*_lookup`` or ``password_hash``
(SC-005); decrypted sensitive values appear ONLY in the profile response
returned to self/admin (controlled decryption — FR-006).
"""

from passanorte_back.modules.tourists.schemas.tourists import (  # noqa: F401
    InterestCategoriesResponse,
    InterestCategory,
    TouristCreateRequest,
    TouristInterestsResponse,
    TouristInterestsUpdateRequest,
    TouristLoginRequest,
    TouristProfileResponse,
    TouristRegistered,
    TouristSessionResponse,
    TouristUpdateRequest,
)
