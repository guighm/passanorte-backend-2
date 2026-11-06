"""FR-021 constraint validator (feature 016 — data-model rules summary).

Validates an itinerary plan against the candidate set it was built from:
only anchorable items, inside operating hours at the suggested instant,
event items only on the target day, and the cost total equal to the sum of
the item prices. Shared by the chat flow (item filtering) and by the US2
constraint tests.
"""

from dataclasses import dataclass

from passanorte_back.modules.chatbot.services.planning import ItineraryPlan
from passanorte_back.modules.chatbot.services.retrieval import Candidate


@dataclass(frozen=True)
class ValidationIssue:
    """One broken constraint, with its reason (testable — FR-021)."""

    ref_id: int
    reason: str


@dataclass(frozen=True)
class ValidationResult:
    """Pass/fail plus the reasons; ``valid_items`` is the filtered subset."""

    issues: list[ValidationIssue]
    valid_items: list  # list[ItineraryItem]

    @property
    def ok(self) -> bool:
        return not self.issues


def validate_plan(
    plan: ItineraryPlan, candidates: list[Candidate], *, target_day: str
) -> ValidationResult:
    """Check every constraint of FR-021; collect one issue per broken item."""
    by_ref = {(candidate.kind, candidate.ref_id): candidate for candidate in candidates}
    issues: list[ValidationIssue] = []
    valid_items: list = []
    cost_sum = 0
    for item in plan.items:
        candidate = by_ref.get((item.kind, item.ref_id))
        if candidate is None:
            issues.append(ValidationIssue(item.ref_id, "not anchored to a registered candidate"))
            continue
        if (
            item.kind == "spot"
            and candidate.opens_at is not None
            and candidate.closes_at is not None
            and not (candidate.opens_at <= item.suggested_at.time() < candidate.closes_at)
        ):
            issues.append(ValidationIssue(item.ref_id, "closed at the suggested time"))
            continue  # FR-009
        if item.kind == "event" and item.suggested_at.date().isoformat() != target_day:
            issues.append(ValidationIssue(item.ref_id, "event not on the target day"))
            continue  # FR-024
        if item.ticket_cost_cents != candidate.ticket_price_cents:
            issues.append(ValidationIssue(item.ref_id, "cost does not match the registered price"))
            continue
        cost_sum += item.ticket_cost_cents
        valid_items.append(item)
    if plan.total_cost_cents != cost_sum:
        issues.append(ValidationIssue(0, "total cost differs from the sum of item prices"))
        # Cost mismatch is a plan-level defect: rebuild-free route is to
        # recompute in the caller (planning guarantees the sum), so this
        # issue should never fire for plans built by ``build_itinerary``.
    return ValidationResult(issues=issues, valid_items=valid_items)
