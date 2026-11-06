"""Configurable fake LLM provider for tests (feature 016 — FR-023, T008).

No real network call anywhere in the suite: every test injects one of
these doubles where the real ``HttpLlmProvider`` would be used. Each fake
records the prompts it receives (last one wins) so tests can assert on
what context the service actually sent (US3 continuity).
"""

from typing import Final

from passanorte_back.modules.chatbot.services.providers import (
    LlmProvider,
    PlannerPrompt,
    PlannerReply,
)


class FakeLlmProvider:
    """Returns a canned, valid planner reply; records prompts."""

    def __init__(self, *, text: str | None = None) -> None:
        self.text = text if text is not None else "Sugestão de roteiro gerada."
        self.spot_ids: list[int] = []
        self.event_ids: list[int] = []
        self.prompts: list[PlannerPrompt] = []
        self.last_prompt: PlannerPrompt | None = None

    def plan_itinerary(self, prompt: PlannerPrompt) -> PlannerReply:
        self.prompts.append(prompt)
        self.last_prompt = prompt
        return PlannerReply(
            text=self.text, spot_ids=list(self.spot_ids), event_ids=list(self.event_ids)
        )

    def set_selection(self, *, spot_ids: list[int], event_ids: list[int] | None = None) -> None:
        self.spot_ids = list(spot_ids)
        self.event_ids = list(event_ids or [])


class NeverCalledProvider(LlmProvider):
    """Guard fake: raises if a test reaches the provider unexpectedly.
    Recording attributes exist so wrappers (e.g. ``TimeoutFake``) can use
    it as a base without touching it."""

    def __init__(self) -> None:
        self.prompts: list[PlannerPrompt] = []
        self.last_prompt: PlannerPrompt | None = None

    def plan_itinerary(self, prompt: PlannerPrompt) -> PlannerReply:
        raise AssertionError("provider was reached but the test expected no call")


class ProviderErrorFake(LlmProvider):
    """Simulates a provider failure (network/HTTP — US4 scenario 2)."""

    def plan_itinerary(self, prompt: PlannerPrompt) -> PlannerReply:
        from passanorte_back.modules.chatbot.services.providers import ProviderError

        raise ProviderError("simulated provider failure")


class TimeoutFake(LlmProvider):
    """Simulates a provider exceeding the deadline (US4 scenario 3)."""

    def __init__(self, *, base: LlmProvider) -> None:
        self._base = base
        self.calls = 0

    def plan_itinerary(self, prompt: PlannerPrompt) -> PlannerReply:
        self.calls += 1
        self._base.prompts.append(prompt)
        self._base.last_prompt = prompt
        from passanorte_back.modules.chatbot.services.providers import ProviderTimeout

        raise ProviderTimeout("simulated provider timeout")


class MalformedOutputFake(LlmProvider):
    """Simulates LLM output that cannot be anchored (US4 scenario 4):
    unparseable reply (``ProviderMalformedOutput``), or JSON with ids
    unknown to the candidate set / empty selection."""

    def __init__(self, *, mode: str = "not-json") -> None:
        modes: Final = ("not-json", "unknown-ids", "empty")
        if mode not in modes:
            raise ValueError(f"mode must be one of {modes}")
        self.mode = mode
        self.prompts: list[PlannerPrompt] = []

    def plan_itinerary(self, prompt: PlannerPrompt) -> PlannerReply:
        from passanorte_back.modules.chatbot.services.providers import ProviderMalformedOutput

        self.prompts.append(prompt)
        if self.mode == "not-json":
            raise ProviderMalformedOutput("reply is not a JSON object")
        if self.mode == "unknown-ids":
            return PlannerReply(text="x", spot_ids=[999_999], event_ids=[])
        return PlannerReply(text="x", spot_ids=[], event_ids=[])
