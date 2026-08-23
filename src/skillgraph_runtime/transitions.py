"""Central state-transition guards for Runtime domain types."""

from __future__ import annotations

from dataclasses import replace

from .domain import AttemptRecord, AttemptStatus, NodeDefinition, NodeKind, NodeState, NodeStatus, WorkflowStatus
from .errors import RuntimeContractError


_EXECUTABLE_TRANSITIONS = {
    NodeStatus.PENDING: {NodeStatus.READY, NodeStatus.SKIPPED, NodeStatus.BLOCKED, NodeStatus.INVALIDATED},
    NodeStatus.READY: {NodeStatus.RUNNING, NodeStatus.SKIPPED, NodeStatus.BLOCKED, NodeStatus.INVALIDATED},
    NodeStatus.RUNNING: {NodeStatus.COMPLETED, NodeStatus.FAILED, NodeStatus.BLOCKED, NodeStatus.INVALIDATED},
    NodeStatus.COMPLETED: {NodeStatus.VERIFYING, NodeStatus.INVALIDATED},
    NodeStatus.VERIFYING: {NodeStatus.VERIFIED, NodeStatus.FAILED, NodeStatus.BLOCKED, NodeStatus.INVALIDATED},
    NodeStatus.FAILED: {NodeStatus.RETRY_READY, NodeStatus.BLOCKED, NodeStatus.INVALIDATED},
    NodeStatus.RETRY_READY: {NodeStatus.RUNNING, NodeStatus.INVALIDATED},
    NodeStatus.VERIFIED: {NodeStatus.INVALIDATED},
    NodeStatus.INVALIDATED: {NodeStatus.PENDING},
}

_HUMAN_GATE_TRANSITIONS = {
    NodeStatus.PENDING: {NodeStatus.READY, NodeStatus.SKIPPED, NodeStatus.BLOCKED, NodeStatus.INVALIDATED},
    NodeStatus.READY: {NodeStatus.WAITING_FOR_USER, NodeStatus.SKIPPED, NodeStatus.BLOCKED, NodeStatus.INVALIDATED},
    NodeStatus.WAITING_FOR_USER: {NodeStatus.APPROVED, NodeStatus.BLOCKED, NodeStatus.INVALIDATED},
    NodeStatus.APPROVED: {NodeStatus.INVALIDATED},
    NodeStatus.INVALIDATED: {NodeStatus.PENDING},
}

_EXTERNAL_INPUT_TRANSITIONS = {
    NodeStatus.PENDING: {NodeStatus.READY, NodeStatus.SKIPPED, NodeStatus.BLOCKED, NodeStatus.INVALIDATED},
    NodeStatus.READY: {NodeStatus.WAITING_FOR_EXTERNAL, NodeStatus.SKIPPED, NodeStatus.BLOCKED, NodeStatus.INVALIDATED},
    NodeStatus.WAITING_FOR_EXTERNAL: {NodeStatus.COMPLETED, NodeStatus.FAILED, NodeStatus.BLOCKED, NodeStatus.INVALIDATED},
    NodeStatus.COMPLETED: {NodeStatus.VERIFYING, NodeStatus.INVALIDATED},
    NodeStatus.VERIFYING: {NodeStatus.VERIFIED, NodeStatus.FAILED, NodeStatus.BLOCKED, NodeStatus.INVALIDATED},
    NodeStatus.FAILED: {NodeStatus.RETRY_READY, NodeStatus.BLOCKED, NodeStatus.INVALIDATED},
    NodeStatus.RETRY_READY: {NodeStatus.WAITING_FOR_EXTERNAL, NodeStatus.INVALIDATED},
    NodeStatus.VERIFIED: {NodeStatus.INVALIDATED},
    NodeStatus.INVALIDATED: {NodeStatus.PENDING},
}

_WORKFLOW_TRANSITIONS = {
    WorkflowStatus.CREATED: {WorkflowStatus.RUNNING, WorkflowStatus.PAUSED, WorkflowStatus.CANCELLED, WorkflowStatus.FAILED},
    WorkflowStatus.RUNNING: {
        WorkflowStatus.WAITING_FOR_USER,
        WorkflowStatus.WAITING_FOR_EXTERNAL,
        WorkflowStatus.PAUSED,
        WorkflowStatus.COMPLETED,
        WorkflowStatus.CANCELLED,
        WorkflowStatus.FAILED,
    },
    WorkflowStatus.WAITING_FOR_USER: {WorkflowStatus.RUNNING, WorkflowStatus.PAUSED, WorkflowStatus.CANCELLED, WorkflowStatus.FAILED},
    WorkflowStatus.WAITING_FOR_EXTERNAL: {WorkflowStatus.RUNNING, WorkflowStatus.PAUSED, WorkflowStatus.CANCELLED, WorkflowStatus.FAILED},
    WorkflowStatus.PAUSED: {WorkflowStatus.RUNNING, WorkflowStatus.CANCELLED, WorkflowStatus.FAILED},
}

_ATTEMPT_TRANSITIONS = {
    AttemptStatus.RUNNING: {AttemptStatus.WAITING_FOR_USER, AttemptStatus.WAITING_FOR_EXTERNAL, AttemptStatus.COMPLETED, AttemptStatus.FAILED, AttemptStatus.INVALIDATED},
    AttemptStatus.WAITING_FOR_USER: {AttemptStatus.RUNNING, AttemptStatus.FAILED, AttemptStatus.INVALIDATED},
    AttemptStatus.WAITING_FOR_EXTERNAL: {AttemptStatus.RUNNING, AttemptStatus.FAILED, AttemptStatus.INVALIDATED},
}


def _allowed_node_transitions(definition: NodeDefinition) -> dict[NodeStatus, set[NodeStatus]]:
    if definition.kind is NodeKind.HUMAN_GATE:
        return _HUMAN_GATE_TRANSITIONS
    if definition.kind is NodeKind.EXTERNAL_INPUT:
        return _EXTERNAL_INPUT_TRANSITIONS
    transitions = {source: set(targets) for source, targets in _EXECUTABLE_TRANSITIONS.items()}
    if definition.interactive:
        transitions[NodeStatus.RUNNING].add(NodeStatus.WAITING_FOR_USER)
        transitions[NodeStatus.WAITING_FOR_USER] = {NodeStatus.RUNNING, NodeStatus.FAILED, NodeStatus.BLOCKED}
    transitions[NodeStatus.RUNNING].add(NodeStatus.WAITING_FOR_EXTERNAL)
    transitions[NodeStatus.WAITING_FOR_EXTERNAL] = {NodeStatus.RUNNING, NodeStatus.FAILED, NodeStatus.BLOCKED, NodeStatus.INVALIDATED}
    return transitions


def transition_node(definition: NodeDefinition, state: NodeState, target: NodeStatus) -> NodeState:
    allowed = _allowed_node_transitions(definition).get(state.status, set())
    if target not in allowed:
        raise RuntimeContractError(
            f"Illegal {definition.kind.value} node transition: {state.status.value} -> {target.value}",
            rule="node_transition",
            details={"node_id": definition.address.node_id, "from": state.status.value, "to": target.value},
        )
    updates: dict[str, object] = {"status": target}
    if target not in {NodeStatus.RUNNING, NodeStatus.WAITING_FOR_USER, NodeStatus.WAITING_FOR_EXTERNAL}:
        updates["active_attempt_id"] = None
    if target not in {NodeStatus.RUNNING, NodeStatus.WAITING_FOR_USER}:
        updates["interaction_checkpoint_ref"] = None
    return replace(state, **updates)


def transition_workflow(status: WorkflowStatus, target: WorkflowStatus) -> WorkflowStatus:
    if target not in _WORKFLOW_TRANSITIONS.get(status, set()):
        raise RuntimeContractError(
            f"Illegal workflow transition: {status.value} -> {target.value}",
            rule="workflow_transition",
            details={"from": status.value, "to": target.value},
        )
    return target


def transition_attempt(attempt: AttemptRecord, target: AttemptStatus, *, finished_at: str | None = None) -> AttemptRecord:
    if target not in _ATTEMPT_TRANSITIONS.get(attempt.status, set()):
        raise RuntimeContractError(
            f"Illegal attempt transition: {attempt.status.value} -> {target.value}",
            rule="attempt_transition",
            details={"attempt_id": attempt.attempt_id, "from": attempt.status.value, "to": target.value},
        )
    if target in {AttemptStatus.COMPLETED, AttemptStatus.FAILED, AttemptStatus.INVALIDATED} and not finished_at:
        raise RuntimeContractError("Terminal Attempt transition requires finished_at", rule="attempt_finished_at")
    if target in {AttemptStatus.WAITING_FOR_USER, AttemptStatus.WAITING_FOR_EXTERNAL} and finished_at is not None:
        raise RuntimeContractError("Waiting Attempt cannot have finished_at", rule="attempt_finished_at")
    return replace(attempt, status=target, finished_at=finished_at)
