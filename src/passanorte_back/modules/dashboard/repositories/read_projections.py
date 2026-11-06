"""Read-only projections of other domains' tables (feature 014 — data-model.md §2).

``dashboard`` only READS across domains (spec FR-021, constitution rules
3–4): instead of importing owner-module ORM internals (which the AST
boundary gate forbids), these lightweight, NON-registered
``sa.table()``/``sa.column()`` constructs mirror only the columns the
aggregates need. They carry no FKs, no metadata registration and no write
path — SELECT-only by construction.

Schema parity guards:
- every new aggregate is exercised against real seeded data in
  ``tests/integration/test_dashboard_metrics_flow.py`` — any drift breaks
  the tests;
- the owner modules are the single source of truth for the tables
  (``tourists``/``tourist_interests`` — spec 003; ``tourist_spots`` — spec
  007; ``visitations`` — spec 011).

Sensitive columns (``*_encrypted``, ``*_lookup``, ``password_hash``) are
NEVER declared here — the dashboard cannot even select them (LGPD,
constitution II — data-model.md §2).
"""

import sqlalchemy as sa

# §2 — source-of-truth table: ``tourist_spots`` (visitation + discovery use it identically).
VISITATIONS = sa.table(
    "visitations",
    sa.column("id", sa.Integer),
    sa.column("tourist_id", sa.Integer),
    sa.column("tourist_spot_id", sa.Integer),
    sa.column("visited_at", sa.DateTime),
)

TOURIST_SPOTS = sa.table(
    "tourist_spots",
    sa.column("id", sa.Integer),
    sa.column("name", sa.String),
    sa.column("latitude", sa.Float),
    sa.column("longitude", sa.Float),
)

TOURISTS = sa.table(
    "tourists",
    sa.column("id", sa.Integer),
    sa.column("country_of_origin", sa.String),
)

TOURIST_INTERESTS = sa.table(
    "tourist_interests",
    sa.column("tourist_id", sa.Integer),
    sa.column("category_key", sa.String),
)
