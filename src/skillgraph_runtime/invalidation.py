"""Precise, append-only downstream invalidation for the Runtime Core."""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Mapping

from .domain import AttemptStatus, NodeAddress, NodeState, NodeStatus, RunSnapshot, WorkflowStatus
from .errors import RuntimeContractError
from .graph import CompiledBundle


@dataclass(frozen=True)
class InvalidationResult:
    next_snapshot: RunSnapshot
    invalidated: tuple[NodeAddress, ...]
    removed_artifact_types: tuple[str, ...]


def _definition_dependencies(bundle: CompiledBundle, address: NodeAddress) -> tuple[NodeAddress, ...]:
    definition = bundle.definition(address)
    return tuple(NodeAddress(address.graph_path, node_id) for node_id in definition.depends_on)


def _reverse_dependencies(snapshot: RunSnapshot, bundle: CompiledBundle) -> Mapping[NodeAddress, tuple[NodeAddress, ...]]:
    reverse: dict[NodeAddress, list[NodeAddress]] = {}
    for address in snapshot.node_states:
        template = NodeAddress(address.graph_path, address.node_id)
        for dependency in _definition_dependencies(bundle, template):
            # A template dependency can fan out.  Attach each concrete child
            # to its template source and preserve deterministic ordering.
            for candidate in snapshot.node_states:
                if candidate == dependency or (
                    candidate.graph_path == dependency.graph_path
                    and candidate.node_id == dependency.node_id
                    and dependency.instance_key is None
                ):
                    reverse.setdefault(candidate, []).append(address)
    return {key: tuple(sorted(set(value))) for key, value in reverse.items()}


def _artifact_types_for_addresses(snapshot: RunSnapshot, bundle: CompiledBundle, addresses: set[NodeAddress]) -> tuple[str, ...]:
    types: set[str] = set()
    for attempt in snapshot.attempts:
        if attempt.address not in addresses:
            continue
        definition = bundle.definition(attempt.address)
        skill = bundle.skills.get(definition.implementation_ref or "", {})
        for output in skill.get("output_contracts", ()):  # Contract-owned metadata
            artifact_type = output.get("artifact_type")
            if isinstance(artifact_type, str):
                types.add(artifact_type)
    return tuple(sorted(types))


def invalidate_downstream(snapshot: RunSnapshot, bundle: CompiledBundle, changed_address: NodeAddress) -> InvalidationResult:
    """Invalidate only transitive dependents of a changed, verified producer."""

    if changed_address not in snapshot.node_states:
        raise RuntimeContractError("Changed node does not exist in the Run", rule="invalidation_node")
    reverse = _reverse_dependencies(snapshot, bundle)
    pending = list(reverse.get(changed_address, ()))
    targets: set[NodeAddress] = set()
    while pending:
        address = pending.pop()
        if address in targets:
            continue
        targets.add(address)
        pending.extend(reverse.get(address, ()))
    if not targets:
        return InvalidationResult(snapshot, (), ())

    running = [
        attempt.attempt_id
        for attempt in snapshot.attempts
        if attempt.address in targets and attempt.status is AttemptStatus.RUNNING
    ]
    if running:
        raise RuntimeContractError(
            "Cannot invalidate a Run while an affected Attempt is running",
            code="STATE_VERSION_CONFLICT",
            rule="invalidation_running_attempt",
            details={"attempt_ids": tuple(sorted(running))},
        )

    states = dict(snapshot.node_states)
    for address in targets:
        state = states[address]
        states[address] = NodeState(status=NodeStatus.INVALIDATED, attempt_count=state.attempt_count)
    attempts = tuple(
        replace(attempt, status=AttemptStatus.INVALIDATED, finished_at=attempt.finished_at or "invalidated")
        if attempt.address in targets and attempt.status in {AttemptStatus.WAITING_FOR_USER, AttemptStatus.WAITING_FOR_EXTERNAL}
        else attempt
        for attempt in snapshot.attempts
    )
    current_gate = snapshot.current_gate
    if current_gate and NodeAddress((), current_gate) in targets:
        current_gate = None
    current_interaction = snapshot.current_interaction
    if current_interaction and NodeAddress((), str(current_interaction.get("node_id", ""))) in targets:
        current_interaction = None
    next_snapshot = replace(
        snapshot,
        state_version=snapshot.state_version + 1,
        workflow_status=WorkflowStatus.RUNNING if snapshot.workflow_status in {WorkflowStatus.WAITING_FOR_USER, WorkflowStatus.WAITING_FOR_EXTERNAL} else snapshot.workflow_status,
        node_states=states,
        attempts=attempts,
        current_gate=current_gate,
        current_interaction=current_interaction,
        current_gate_request_ref=None if current_gate is None else snapshot.current_gate_request_ref,
        current_gate_modification_ref=None if current_gate is None else snapshot.current_gate_modification_ref,
    )
    return InvalidationResult(next_snapshot, tuple(sorted(targets)), _artifact_types_for_addresses(snapshot, bundle, targets))


def resume_invalidated(snapshot: RunSnapshot) -> RunSnapshot:
    """Return invalidated nodes to PENDING without erasing their history."""

    addresses = [address for address, state in snapshot.node_states.items() if state.status is NodeStatus.INVALIDATED]
    if not addresses:
        return snapshot
    states = dict(snapshot.node_states)
    for address in addresses:
        previous = states[address]
        states[address] = NodeState(status=NodeStatus.PENDING, attempt_count=previous.attempt_count)
    return replace(snapshot, state_version=snapshot.state_version + 1, node_states=states)
