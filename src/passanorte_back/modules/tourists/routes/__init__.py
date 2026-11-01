"""Module HTTP routes (tourists): imported for side effect — decorators on
the canonical router (core/routers.py).

Import order fixes route precedence: fixed paths (``/me``,
``/interest-categories``, ``/me/interests``) are registered before the
``/{tourist_id}`` parameterized route.
"""

from passanorte_back.modules.tourists.routes import (  # noqa: F401
    interests,
    profile,
    tourists,
)
