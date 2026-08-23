"""Pure T7--T10 Runtime state advancement.

No function in this module touches the filesystem or executes an Adapter.  The
Kernel validates proposals, calls these functions, and (when configured) asks
the single-writer repository to persist the resulting immutable Snapshot.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Any, Callable, Mapping

from .domain import (
    AttemptRecord,
    AttemptStatus,
    GateDecision,
    NodeAddress,
    NodeKind,
    NodeState,
    NodeStatus,
    ProofOutcome,
    ReadinessStatus,
    RunSnapshot,
    WorkflowStatus,
)
from .error_policy import ErrorAction, ErrorOutcome, validate_structured_error
from .errors import RuntimeContractError
from .graph import CompiledBundle
from .transitions import transition_attempt, transition_node


@dataclass(frozen=True)
class ResultApplication:
    next_snapshot: RunSnapshot
    checkpoint_ref: str | None = None
    checkpoint: Mapping[str, Any] | None = None
    error_outcome: ErrorOutcome | None = None


@dataclass(frozen=True)
class ExternalSubmission:
    next_snapshot: RunSnapshot
    deferred_effects: tuple[str, ...] = ()


def _attempt(snapshot: RunSnapshot, attempt_id: str) -> tuple[int, AttemptRecord]:
    matches = [(index, attempt) for index, attempt in enumerate(snapshot.attempts) if attempt.attempt_id == attempt_id]
    if len(matches) != 1:
        raise RuntimeContractError("Attempt must identify exactly one active record", rule="runtime_attempt")
    return matches[0]


def _with_usage(attempt: AttemptRecord, payload: Mapping[str, Any]) -> AttemptRecord:
    return replace(attempt, usage=attempt.usage.add(payload["usage"]))


def _checkpoint_ref(attempt_id: str, checkpoint_id: str) -> str:
    return f"runtime/attempts/{attempt_id}/checkpoints/{checkpoint_id}.json"


def _workflow_status_from_runtime(
    states: Mapping[NodeAddress, NodeState],
    attempts: tuple[AttemptRecord, ...],
    fallback: WorkflowStatus,
) -> WorkflowStatus:
    """Derive a public Workflow status without losing an unrelated wait."""

    if any(attempt.status is AttemptStatus.RUNNING for attempt in attempts):
        return WorkflowStatus.RUNNING
    if any(state.status is NodeStatus.WAITING_FOR_USER for state in states.values()):
        return WorkflowStatus.WAITING_FOR_USER
    if any(state.status is NodeStatus.WAITING_FOR_EXTERNAL for state in states.values()):
        return WorkflowStatus.WAITING_FOR_EXTERNAL
    return fallback


def _apply_failure(
    snapshot: RunSnapshot,
    index: int,
    attempt: AttemptRecord,
    payload: Mapping[str, Any],
    bundle: CompiledBundle,
    *,
    now: Callable[[], str],
) -> ResultApplication:
    error = payload["error"]
    outcome = validate_structured_error(error)
    if outcome.action is ErrorAction.REJECT_NO_MUTATION:
        raise RuntimeContractError(
            "This Error Taxonomy action rejects the operation without mutating Runtime State",
            code=outcome.code,
            rule="error_no_mutation",
        )
    definition = bundle.definition(attempt.address)
    state = snapshot.node_states[attempt.address]
    failed_attempt = transition_attempt(_with_usage(attempt, payload), AttemptStatus.FAILED, finished_at=now())
    failed_state = transition_node(definition, state, NodeStatus.FAILED)
    failed_state = replace(failed_state, error=error)
    attempts = list(snapshot.attempts)
    attempts[index] = failed_attempt
    states = dict(snapshot.node_states)
    states[attempt.address] = failed_state
    forced_workflow_status: WorkflowStatus | None = None
    global_cycles = snapshot.global_research_cycle

    if outcome.action is ErrorAction.RETRY_NODE:
        retries_used = max(0, state.attempt_count - 1)
        target = NodeStatus.RETRY_READY if retries_used < snapshot.run_policy.max_retries_per_node else NodeStatus.BLOCKED
        states[attempt.address] = transition_node(definition, failed_state, target)
        states[attempt.address] = replace(states[attempt.address], error=error)
    elif outcome.action is ErrorAction.OPEN_RESEARCH_GAP:
        if global_cycles >= snapshot.run_policy.max_global_research_cycles:
            states[attempt.address] = transition_node(definition, failed_state, NodeStatus.BLOCKED)
            forced_workflow_status = WorkflowStatus.PAUSED
        else:
            global_cycles += 1
            states[attempt.address] = transition_node(definition, failed_state, NodeStatus.BLOCKED)
    elif outcome.action in {ErrorAction.BLOCK_NODE, ErrorAction.REPAIR_INPUT, ErrorAction.OFFER_EVIDENCE_WAIVER}:
        states[attempt.address] = transition_node(definition, failed_state, NodeStatus.BLOCKED)
        if outcome.action is ErrorAction.OFFER_EVIDENCE_WAIVER and bool(error.get("details", {}).get("critical")):
            forced_workflow_status = WorkflowStatus.PAUSED
    elif outcome.action is ErrorAction.MARK_NOT_READY:
        states[attempt.address] = transition_node(definition, failed_state, NodeStatus.BLOCKED)
    elif outcome.action is ErrorAction.PAUSE_AUTOMATION:
        states[attempt.address] = transition_node(definition, failed_state, NodeStatus.BLOCKED)
        forced_workflow_status = WorkflowStatus.PAUSED
    elif outcome.action is ErrorAction.FAIL_WORKFLOW:
        forced_workflow_status = WorkflowStatus.FAILED
    elif outcome.action is ErrorAction.WAIT_FOR_USER:
        # These codes normally arrive through a Gate command rather than an
        # Executor Result.  Preserve a blocked producer and surface the
        # canonical Workflow wait instead of silently retrying it.
        states[attempt.address] = transition_node(definition, failed_state, NodeStatus.BLOCKED)
        forced_workflow_status = WorkflowStatus.WAITING_FOR_USER
    elif outcome.action is ErrorAction.WAIT_FOR_EXTERNAL:
        states[attempt.address] = transition_node(definition, failed_state, NodeStatus.BLOCKED)
        forced_workflow_status = WorkflowStatus.WAITING_FOR_EXTERNAL

    workflow_status = forced_workflow_status or _workflow_status_from_runtime(
        states,
        tuple(attempts),
        WorkflowStatus.RUNNING,
    )

    next_snapshot = replace(
        snapshot,
        state_version=snapshot.state_version + 1,
        workflow_status=workflow_status,
        readiness_status=(ReadinessStatus.NOT_READY if outcome.action is ErrorAction.MARK_NOT_READY else snapshot.readiness_status),
        node_states=states,
        attempts=tuple(attempts),
        global_research_cycle=global_cycles,
    )
    return ResultApplication(next_snapshot=next_snapshot, error_outcome=outcome)


def apply_executor_result(
    snapshot: RunSnapshot,
    attempt_id: str,
    result: Mapping[str, Any],
    bundle: CompiledBundle,
    *,
    now: Callable[[], str],
) -> ResultApplication:
    """Apply a pre-validated Executor Result to one active Attempt."""

    index, attempt = _attempt(snapshot, attempt_id)
    payload = result["executor_result"]
    definition = bundle.definition(attempt.address)
    state = snapshot.node_states.get(attempt.address)
    if (
        state is None
        or attempt.status is not AttemptStatus.RUNNING
        or state.status is not NodeStatus.RUNNING
        or state.active_attempt_id != attempt_id
    ):
        raise RuntimeContractError("Executor Result targets a non-active Attempt", rule="executor_attempt_status")

    if payload["status"] == "FAILED":
        return _apply_failure(snapshot, index, attempt, payload, bundle, now=now)

    attempts = list(snapshot.attempts)
    states = dict(snapshot.node_states)
    updated_attempt = _with_usage(attempt, payload)
    if payload["status"] == "WAITING_FOR_USER":
        if not definition.interactive:
            raise RuntimeContractError("Only an Interactive Skill may wait for the user", rule="interaction_skill")
        checkpoint = payload["interaction_checkpoint"]
        ref = _checkpoint_ref(attempt_id, checkpoint["checkpoint_id"])
        updated_attempt = transition_attempt(updated_attempt, AttemptStatus.WAITING_FOR_USER)
        updated_attempt = replace(updated_attempt, interaction_checkpoint_ref=ref)
        waiting_state = transition_node(definition, state, NodeStatus.WAITING_FOR_USER)
        states[attempt.address] = replace(waiting_state, active_attempt_id=attempt_id, interaction_checkpoint_ref=ref)
        attempts[index] = updated_attempt
        request = payload["interaction_request"]
        interaction = {
            "node_id": attempt.address.node_id,
            "attempt_id": attempt_id,
            "method": request["method"],
            "question_id": request["question_id"],
            "round": request["round"],
            "checkpoint_ref": ref,
        }
        return ResultApplication(
            next_snapshot=replace(
                snapshot,
                state_version=snapshot.state_version + 1,
                workflow_status=WorkflowStatus.WAITING_FOR_USER,
                node_states=states,
                attempts=tuple(attempts),
                current_interaction=interaction,
                current_gate=None,
                current_gate_request_ref=None,
            ),
            checkpoint_ref=ref,
            checkpoint=checkpoint,
        )

    updated_attempt = transition_attempt(updated_attempt, AttemptStatus.COMPLETED, finished_at=now())
    completed_state = transition_node(definition, state, NodeStatus.COMPLETED)
    states[attempt.address] = replace(completed_state, artifact_refs=tuple(payload["output_artifact_refs"]))
    attempts[index] = updated_attempt
    all_attempts = tuple(attempts)
    return ResultApplication(
        next_snapshot=replace(
            snapshot,
            state_version=snapshot.state_version + 1,
            workflow_status=_workflow_status_from_runtime(states, all_attempts, WorkflowStatus.RUNNING),
            node_states=states,
            attempts=all_attempts,
            current_interaction=None if snapshot.current_interaction and snapshot.current_interaction.get("attempt_id") == attempt_id else snapshot.current_interaction,
        )
    )


def resume_interaction(snapshot: RunSnapshot, address: NodeAddress, bundle: CompiledBundle) -> RunSnapshot:
    """Resume the existing interactive Attempt after a persisted response."""

    from .attempts import resume_interactive_attempt

    resumed = resume_interactive_attempt(snapshot, address, bundle)
    return replace(
        resumed,
        workflow_status=WorkflowStatus.RUNNING,
        current_interaction=None,
        current_gate=None,
        current_gate_request_ref=None,
    )


def open_gate(snapshot: RunSnapshot, address: NodeAddress, gate_request_ref: str, bundle: CompiledBundle) -> RunSnapshot:
    definition = bundle.definition(address)
    state = snapshot.node_states.get(address)
    if definition.kind is not NodeKind.HUMAN_GATE or state is None or state.status not in {NodeStatus.READY, NodeStatus.WAITING_FOR_USER}:
        raise RuntimeContractError("Gate can only be opened from a ready or unsupplied waiting Human Gate node", rule="gate_open_state")
    if state.status is NodeStatus.WAITING_FOR_USER and snapshot.current_gate_request_ref is not None:
        raise RuntimeContractError("Gate already has a saved request", rule="gate_open_state")
    waiting = transition_node(definition, state, NodeStatus.WAITING_FOR_USER) if state.status is NodeStatus.READY else state
    states = dict(snapshot.node_states)
    states[address] = waiting
    return replace(
        snapshot,
        state_version=snapshot.state_version + 1,
        workflow_status=WorkflowStatus.WAITING_FOR_USER,
        node_states=states,
        current_gate=address.node_id,
        current_gate_request_ref=gate_request_ref,
        current_interaction=None,
    )


def submit_gate_decision(
    snapshot: RunSnapshot,
    address: NodeAddress,
    decision: GateDecision,
    bundle: CompiledBundle,
) -> ExternalSubmission:
    definition = bundle.definition(address)
    state = snapshot.node_states.get(address)
    if (
        definition.kind is not NodeKind.HUMAN_GATE
        or state is None
        or state.status is not NodeStatus.WAITING_FOR_USER
        or snapshot.current_gate != address.node_id
    ):
        raise RuntimeContractError("Gate Decision targets no current waiting Gate", rule="gate_submit_state")
    if decision is GateDecision.MODIFY:
        return ExternalSubmission(snapshot, ("gate_modification_confirmation",))
    approved = transition_node(definition, state, NodeStatus.APPROVED)
    states = dict(snapshot.node_states)
    states[address] = replace(approved, gate_decision=decision)
    workflow_status = WorkflowStatus.CANCELLED if decision is GateDecision.CANCEL else _workflow_status_from_runtime(
        states,
        snapshot.attempts,
        WorkflowStatus.RUNNING,
    )
    effects: tuple[str, ...] = ()
    if decision is GateDecision.REQUEST_MORE_RESEARCH:
        effects = ("research_gap",)
    return ExternalSubmission(
        replace(
            snapshot,
            state_version=snapshot.state_version + 1,
            workflow_status=workflow_status,
            node_states=states,
            current_gate=None,
            current_gate_request_ref=None,
            current_gate_modification_ref=None,
        ),
        effects,
    )


def submit_external_proof(
    snapshot: RunSnapshot,
    address: NodeAddress,
    proof_result: Mapping[str, Any],
    bundle: CompiledBundle,
) -> ExternalSubmission:
    definition = bundle.definition(address)
    state = snapshot.node_states.get(address)
    if definition.kind is not NodeKind.EXTERNAL_INPUT or state is None or state.status is not NodeStatus.WAITING_FOR_EXTERNAL:
        raise RuntimeContractError("External input targets no waiting External Input node", rule="external_submit_state")
    completed = transition_node(definition, state, NodeStatus.COMPLETED)
    verifying = transition_node(definition, completed, NodeStatus.VERIFYING)
    verified = transition_node(definition, verifying, NodeStatus.VERIFIED)
    states = dict(snapshot.node_states)
    states[address] = replace(
        verified,
        proof_outcome=ProofOutcome(proof_result["proof_result"]["outcome"]),
        artifact_refs=tuple(proof_result["proof_result"]["artifact_refs"]),
    )
    return ExternalSubmission(
        replace(
            snapshot,
            state_version=snapshot.state_version + 1,
            workflow_status=_workflow_status_from_runtime(states, snapshot.attempts, WorkflowStatus.RUNNING),
            node_states=states,
        ),
        ("invalidate:feasibility", "return_to:feasibility"),
    )
