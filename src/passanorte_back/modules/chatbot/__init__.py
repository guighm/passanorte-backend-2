"""Domain module: chatbot (feature 016 — RF38/RF39).

AI itinerary planner for authenticated tourists: persisted chat sessions
and messages (``chat_sessions``/``chat_messages`` are owned exclusively by
this domain), natural-language conversation, and RAG-style retrieval over
the registered catalog. The catalog (tourist spots, events, tourist
interests) is READ-ONLY for this module — via ``sa.table()``
read-projections (feature 014 precedent), never other modules' models or
tables (constitution preamble rule 3). Itinerary structure (anchoring,
operating-hour checks, geographic ordering, cost sums) is computed
deterministically in code (research R3); the LLM only selects among
retrieved candidates and narrates.

Degraded behavior (research R4): absent/malformed provider settings,
network failure, timeout (~30s default) or non-conforming LLM output all
produce a localized unavailability assistant message with NO itinerary —
never an opaque error (FR-017/FR-018).
"""
