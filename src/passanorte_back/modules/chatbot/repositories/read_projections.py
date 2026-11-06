"""Read-only projections of other domains' tables (feature 016 — research R5).

The ``chatbot`` module only READS across domains (FR-007, constitution
rules 3–4): the retrieval pipeline selects candidates from the registered
catalog — ``tourist_spots``/schedules/categories (spec 007),
``events`` (spec 008) and the tourist's ``tourist_interests`` (spec 003) —
without importing owner-module ORM internals (forbidden by the AST
boundary gate). These lightweight, NON-registered ``sa.table()``/
``sa.column()`` constructs mirror only the columns the retrieval needs;
they carry no FKs, no metadata registration and no write path — SELECT-only
by construction (feature 014 precedent).

Schema parity guards:
- every retrieval query is exercised against real seeded data in
  ``tests/unit/chatbot/test_retrieval.py`` and
  ``tests/integration/test_chatbot_flow.py`` — any drift breaks the tests;
- the owner modules are the single source of truth for the tables.
"""

import sqlalchemy as sa

TOURIST_SPOTS = sa.table(
    "tourist_spots",
    sa.column("id", sa.Integer),
    sa.column("name", sa.String),
    sa.column("description", sa.String),
    sa.column("latitude", sa.Float),
    sa.column("longitude", sa.Float),
    sa.column("status", sa.String),
    sa.column("removed_at", sa.DateTime),
)

TOURIST_SPOT_SCHEDULE_ENTRIES = sa.table(
    "tourist_spot_schedule_entries",
    sa.column("id", sa.Integer),
    sa.column("spot_id", sa.Integer),
    sa.column("weekday", sa.SmallInteger),
    sa.column("opens_at", sa.Time),
    sa.column("closes_at", sa.Time),
)

TOURIST_SPOT_CATEGORIES = sa.table(
    "tourist_spot_categories",
    sa.column("id", sa.Integer),
    sa.column("spot_id", sa.Integer),
    sa.column("category_key", sa.String),
)

EVENTS = sa.table(
    "events",
    sa.column("id", sa.Integer),
    sa.column("spot_id", sa.Integer),
    sa.column("occurrence_date", sa.Date),
    sa.column("description", sa.String),
    sa.column("ticket_price_cents", sa.Integer),
)

TOURIST_INTERESTS = sa.table(
    "tourist_interests",
    sa.column("tourist_id", sa.Integer),
    sa.column("category_key", sa.String),
)
