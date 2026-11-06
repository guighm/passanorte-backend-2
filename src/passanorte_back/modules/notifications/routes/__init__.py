"""Module HTTP routes (notifications): imported for side effect — decorators
on the canonical router (core/routers.py)."""

from passanorte_back.modules.notifications.routes import (  # noqa: F401
    notifications,
    subscriptions,
)
