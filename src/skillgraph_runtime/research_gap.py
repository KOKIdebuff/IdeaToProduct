"""Kernel-owned, bounded Research Gap planning for P0-05-T9."""

from __future__ import annotations

from typing import Any, Callable, Mapping, Protocol, TYPE_CHECKING

from .domain import NodeAddress, deep_thaw
from .errors import RuntimeContractError

if TYPE_CHECKING:
    from .kernel import RuntimeKernel


class ResearchGapPlannerProvider(Protocol):
    """Return an untrusted Gap proposal without Runtime write authority."""

    def plan(self, request: Mapping[str, Any]) -> Mapping[str, Any]: ...


class CallbackResearchGapPlannerProvider:
    """Adapter for an embedding-supplied planner callback."""

    def __init__(self, callback: Callable[[Mapping[str, Any]], Mapping[str, Any]]) -> None:
        self._callback = callback

    def plan(self, request: Mapping[str, Any]) -> Mapping[str, Any]:
        value = self._callback(deep_thaw(request))
        if not isinstance(value, Mapping):
            raise RuntimeContractError("Research Gap Planner callback must return an object", rule="research_gap_provider")
        return value


class FixtureResearchGapPlannerProvider:
    """Deterministic Provider for local Runtime tests and embedding fixtures."""

    def __init__(self, proposal: Mapping[str, Any]) -> None:
        self._proposal = deep_thaw(proposal)

    def plan(self, request: Mapping[str, Any]) -> Mapping[str, Any]:
        del request
        return deep_thaw(self._proposal)


class ConservativeResearchGapPlannerProvider:
    """Default-safe Provider: never invent a retry plan from incomplete input."""

    def plan(self, request: Mapping[str, Any]) -> Mapping[str, Any]:
        del request
        raise RuntimeContractError(
            "Research Gap Planner has no configured proposal Provider",
            code="INPUT_INVALID",
            rule="research_gap_provider_unconfigured",
        )


class ResearchGapPlanner:
    """Coordinate a constrained Provider with the Kernel single-writer boundary."""

    def __init__(
        self,
        kernel: "RuntimeKernel",
        provider: ResearchGapPlannerProvider | None = None,
    ) -> None:
        self.kernel = kernel
        self.provider = provider or ConservativeResearchGapPlannerProvider()

    def advance(self, run_id: str, attempt_id: str) -> Mapping[str, Any]:
        """Plan, atomically persist, then start only the selected retry roots."""

        request = self.kernel.research_gap_request(run_id, attempt_id)
        proposal = self.provider.plan(request)
        if not isinstance(proposal, Mapping):
            raise RuntimeContractError("Research Gap Planner Provider must return an object", rule="research_gap_provider")
        _completed, artifact, invalidation, retry_roots = self.kernel.complete_persisted_research_gap(
            run_id,
            attempt_id,
            proposal,
        )
        # The immutable Gap Artifact has already been atomically committed with
        # its invalidation.  Resuming and scheduling are separate, recoverable
        # Runtime transitions so a later scheduling failure cannot expose a
        # half-written Artifact/Manifest pair.
        self.kernel.resume_invalidated_persisted(run_id)
        plan = self.kernel.schedule_persisted(run_id, requested_nodes=retry_roots)
        scheduled_attempts = list(plan.attempts_to_start)
        # A requested Subgraph root activates its container but intentionally
        # does not select the child work in the same Scheduler pass.  Advance
        # its declared entry node explicitly so a top-level competitor retry
        # has the same observable effect as the other Research roots.
        if NodeAddress((), "competitor") in retry_roots:
            competitor_entry = NodeAddress(("competitor",), "discovery")
            entry_plan = self.kernel.schedule_persisted(run_id, requested_nodes=(competitor_entry,))
            scheduled_attempts.extend(entry_plan.attempts_to_start)
            plan = entry_plan
        return {
            "outcome": "RESEARCH_GAP_PLANNED",
            "artifact_ref": artifact.artifact_ref,
            "retry_targets": [address.node_id for address in retry_roots],
            "invalidated_nodes": [address.node_id for address in invalidation.invalidated],
            "scheduled_attempt_ids": [attempt.attempt_id for attempt in scheduled_attempts],
            "state": plan.next_snapshot.to_wire_state(),
        }
