"""Module HTTP routes (events): imported for side effect — decorators on
the canonical router (core/routers.py).

The admin listing (fixed path ``""``) is decorated before the
parameterized paths; PATCH/DELETE share the ``/{event_id}`` path with
different methods.
"""

from passanorte_back.modules.events.routes import events  # noqa: F401
