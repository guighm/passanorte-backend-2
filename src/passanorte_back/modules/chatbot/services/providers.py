"""Injectable LLM provider seam (feature 016 — research R1, FR-017).

The planner talks to a free-tier generative provider exclusively through
the ``LlmProvider`` protocol; the only production implementation,
``HttpLlmProvider``, speaks the OpenAI-compatible chat-completions wire
format over ``httpx`` — enough for any free-tier vendor (Groq, OpenRouter,
AI-studio-compatible endpoints). Settings come from the environment
(``CHATBOT_LLM_API_KEY``/``CHATBOT_LLM_BASE_URL``/``CHATBOT_LLM_MODEL``);
nothing secret is ever written to the repo (RNF15, FR-017).

Failure taxonomy (research R4):

- ``ProviderUnavailable`` — settings absent/misconfigured (app may boot
  degraded; FR-018);
- ``ProviderTimeout`` — the call exceeded ``chatbot_timeout_seconds``;
- ``ProviderError`` — network/HTTP failure;
- ``ProviderMalformedOutput`` — reply did not parse into the constrained
  planner-reply JSON.

All four are caught by the chat service and become a localized
unavailability message — never an opaque 5xx to the tourist.
"""

import json
import re
from dataclasses import dataclass, field
from typing import Final, Protocol

import httpx

from passanorte_back.core.config import Settings, get_settings

_JSON_BLOCK: Final[re.Pattern[str]] = re.compile(r"\{.*\}", re.DOTALL)


class ProviderUnavailable(Exception):
    """Provider settings absent or incomplete (degraded mode — FR-018)."""


class ProviderTimeout(Exception):
    """The provider did not answer inside the configured deadline."""


class ProviderError(Exception):
    """Network or non-2xx failure while calling the provider."""


class ProviderMalformedOutput(Exception):
    """The reply could not be parsed as the constrained planner JSON."""


@dataclass(frozen=True)
class PlannerCandidate:
    """One retrieved catalog item handed to the LLM (FR-007: context only)."""

    kind: str  # "spot" | "event"
    ref_id: int
    name: str
    description: str
    category_keys: list[str]
    ticket_price_cents: int
    opens_at: str | None = None
    closes_at: str | None = None


@dataclass(frozen=True)
class HistoryTurn:
    """One prior exchange of the same session (US3 continuity — FR-013)."""

    role: str  # "user" | "assistant"
    content: str


@dataclass(frozen=True)
class PlannerPrompt:
    """Everything the model may see (city/context from configuration — RNF06)."""

    query: str
    city: str
    language: str
    target_time: str
    interests: list[str]
    candidates: list[PlannerCandidate]
    history: list[HistoryTurn] = field(default_factory=list)


@dataclass(frozen=True)
class PlannerReply:
    """Anchored selection: ids only from the prompt's candidate set (FR-006)."""

    text: str
    spot_ids: list[int]
    event_ids: list[int]


class LlmProvider(Protocol):
    """The only seam through which the chatbot reaches a generative model."""

    def plan_itinerary(self, prompt: PlannerPrompt) -> PlannerReply: ...


_SYSTEM_PROMPT_TEMPLATE: Final[str] = (
    "You are the itinerary planner of the PassaNorte tourist app ({city}). "
    "Reply exclusively in the configured language ({language}). "
    "Choose only from the provided catalog candidates — NEVER invent places "
    "or events outside the list. Answer ONLY with a JSON object of the exact "
    'shape {{"text": <assistant reply>, "spotIds": <chosen spot ids>, '
    '"eventIds": <chosen event ids>}}; ids must belong to the candidate '
    "list."
)


def _render_candidates(prompt: PlannerPrompt) -> str:
    lines = []
    for candidate in prompt.candidates:
        schedule = ""
        if candidate.opens_at and candidate.closes_at:
            schedule = f" opens {candidate.opens_at}-{candidate.closes_at}"
        lines.append(
            f'- type={candidate.kind} id={candidate.ref_id} name="{candidate.name}"'
            f" categories={candidate.category_keys} price_cents={candidate.ticket_price_cents}"
            f"{schedule} | {candidate.description}"
        )
    return "\n".join(lines)


def build_plan_messages(prompt: PlannerPrompt) -> list[dict[str, str]]:
    """The chat-completions payload messages (pure, unit-testable)."""
    system = _SYSTEM_PROMPT_TEMPLATE.format(city=prompt.city, language=prompt.language)
    history = [
        {"role": turn.role if turn.role == "user" else "assistant", "content": turn.content}
        for turn in prompt.history
    ]
    user = (
        f"Target local time: {prompt.target_time}\n"
        f"Tourist interests: {prompt.interests or []}\n"
        f"Candidates:\n{_render_candidates(prompt)}\n\n"
        f'Tourist message: "{prompt.query}"'
    )
    return [{"role": "system", "content": system}, *history, {"role": "user", "content": user}]


def parse_planner_reply(content: str) -> PlannerReply:
    """Extract the constrained JSON reply; ``ProviderMalformedOutput`` otherwise."""
    match = _JSON_BLOCK.search(content)
    parsed: object = None
    if match is not None:
        try:
            parsed = json.loads(match.group(0))
        except json.JSONDecodeError:
            parsed = None
    if not isinstance(parsed, dict):
        raise ProviderMalformedOutput("reply is not a JSON object")
    text = parsed.get("text")
    spot_ids = parsed.get("spotIds", [])
    event_ids = parsed.get("eventIds", [])
    if (
        not isinstance(text, str)
        or not isinstance(spot_ids, list)
        or not isinstance(event_ids, list)
    ):
        raise ProviderMalformedOutput("reply fields have unexpected types")
    return PlannerReply(text=text, spot_ids=spot_ids, event_ids=event_ids)


class HttpLlmProvider:
    """OpenAI-compatible chat-completions client (research R1)."""

    def __init__(self, *, base_url: str, model: str, api_key: str, timeout_seconds: int) -> None:
        self._base_url = base_url.rstrip("/")
        self._model = model
        self._api_key = api_key
        self._timeout_seconds = timeout_seconds

    @classmethod
    def from_settings(cls, settings: Settings | None = None) -> "HttpLlmProvider":
        """Build from environment settings; missing pieces → degraded (FR-018)."""
        settings = settings or get_settings()
        configured = (
            settings.chatbot_llm_api_key,
            settings.chatbot_llm_base_url,
            settings.chatbot_llm_model,
        )
        if not all(configured):
            raise ProviderUnavailable("chatbot LLM settings are incomplete (CHATBOT_LLM_*)")
        return cls(
            base_url=settings.chatbot_llm_base_url,
            model=settings.chatbot_llm_model,
            api_key=settings.chatbot_llm_api_key,
            timeout_seconds=settings.chatbot_timeout_seconds,
        )

    def plan_itinerary(self, prompt: PlannerPrompt) -> PlannerReply:
        messages = build_plan_messages(prompt)
        try:
            response = httpx.post(
                f"{self._base_url}/chat/completions",
                headers={
                    "Authorization": f"Bearer {self._api_key}",
                    "Content-Type": "application/json",
                },
                json={"model": self._model, "messages": messages, "temperature": 0.2},
                timeout=self._timeout_seconds,
            )
        except httpx.TimeoutException as error:
            raise ProviderTimeout(str(error)) from error
        except httpx.HTTPError as error:
            raise ProviderError(str(error)) from error
        if response.status_code >= 300:
            raise ProviderError(f"provider returned HTTP {response.status_code}")
        try:
            body = response.json()
            content = body["choices"][0]["message"]["content"]
        except (json.JSONDecodeError, KeyError, IndexError, TypeError) as error:
            raise ProviderMalformedOutput(f"unexpected provider payload ({error})") from error
        return parse_planner_reply(content)
