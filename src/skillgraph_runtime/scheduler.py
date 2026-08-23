"""Deterministic, side-effect-free DAG and hierarchical scheduling decisions."""

from __future__ import annotations

from dataclasses import replace
from typing import Callable, Iterable, Mapping, Sequence

from .attempts import AttemptIdFactory, plan_attempt
from .domain import (
    AttemptMode,
    AttemptRecord,
    AttemptStatus,
    DeferredNode,
    ExecutionPlan,
    FanOutExpansion,
    InvocationRequirements,
    NodeAddress,
    NodeDefinition,
    NodeKind,
    NodeState,
    NodeStatus,
    SchedulingDecision,
    SkipReason,
    StateTransition,
    TerminalEvent,
    WorkflowStatus,
)
from .errors import RuntimeContractError
from .graph import CompiledBundle
from .transitions import transition_node


_SUCCESS_TERMINAL = {NodeStatus.VERIFIED, NodeStatus.APPROVED}
_RESOLVED_TERMINAL = _SUCCESS_TERMINAL | {NodeStatus.SKIPPED, NodeStatus.FAILED, NodeStatus.BLOCKED}
_EXECUTABLE_KINDS = {NodeKind.SKILL, NodeKind.VERIFIER, NodeKind.ROUTER}


def _definition_for(bundle: CompiledBundle, address: NodeAddress) -> NodeDefinition:
    return bundle.definition(address)


def _dependency_address(definition: NodeDefinition, node_id: str) -> NodeAddress:
    return NodeAddress(definition.address.graph_path, node_id)


def _dependency_members(
    dependency: NodeAddress,
    states: Mapping[NodeAddress, NodeState],
    fanouts: Mapping[NodeAddress, tuple[str, ...]],
    bundle: CompiledBundle,
) -> tuple[tuple[NodeAddress, NodeState, NodeDefinition], ...] | None:
    graph = bundle.top_level if not dependency.graph_path else bundle.subgraphs[dependency.graph_path[0]]
    if dependency in graph.dynamic_fanout_templates:
        keys = fanouts.get(dependency)
        if not keys:
            return None
        return tuple(
            (
                NodeAddress(dependency.graph_path, dependency.node_id, key),
                states[NodeAddress(dependency.graph_path, dependency.node_id, key)],
                bundle.definition(NodeAddress(dependency.graph_path, dependency.node_id, key)),
            )
            for key in keys
        )
    state = states.get(dependency)
    if state is None:
        return None
    return ((dependency, state, bundle.definition(dependency)),)


def _dependencies_state(
    definition: NodeDefinition,
    states: Mapping[NodeAddress, NodeState],
    fanouts: Mapping[NodeAddress, tuple[str, ...]],
    bundle: CompiledBundle,
) -> tuple[bool, bool]:
    """Return (all satisfied, all resolved)."""

    all_satisfied = True
    all_resolved = True
    for node_id in definition.depends_on:
        members = _dependency_members(_dependency_address(definition, node_id), states, fanouts, bundle)
        if members is None:
            return False, False
        for _, state, dependency_definition in members:
            satisfied = state.status in _SUCCESS_TERMINAL or (
                state.status is NodeStatus.SKIPPED and not dependency_definition.required
            )
            resolved = state.status in _RESOLVED_TERMINAL
            all_satisfied = all_satisfied and satisfied
            all_resolved = all_resolved and resolved
    return all_satisfied, all_resolved


def _condition_state(
    definition: NodeDefinition,
    states: Mapping[NodeAddress, NodeState],
) -> bool | None:
    if definition.condition is None:
        return True
    values: list[bool | None] = []
    for predicate in definition.condition.predicates:
        address = NodeAddress(definition.address.graph_path, predicate.node_id)
        state = states.get(address)
        if state is None:
            values.append(None)
            continue
        raw_value = state.status.value if predicate.result_field == "node_status" else getattr(state, predicate.result_field)
        if raw_value is not None:
            value = raw_value if isinstance(raw_value, str) else raw_value.value
            values.append(value in predicate.expected_values)
        elif state.status in _RESOLVED_TERMINAL:
            values.append(False)
        else:
            values.append(None)
    if definition.condition.any_of:
        if any(value is True for value in values):
            return True
        return False if all(value is False for value in values) else None
    if any(value is False for value in values):
        return False
    return True if all(value is True for value in values) else None


def _sort_key(bundle: CompiledBundle, address: NodeAddress, fanouts: Mapping[NodeAddress, tuple[str, ...]]) -> tuple:
    definition = bundle.definition(address)
    if address.graph_path:
        parent = NodeAddress((), address.graph_path[0])
        parent_order = bundle.top_level.definitions[parent].declaration_order
        graph_order = definition.declaration_order
    else:
        parent_order = definition.declaration_order
        graph_order = -1
    template = NodeAddress(address.graph_path, address.node_id)
    item_order = fanouts.get(template, ()).index(address.instance_key) if address.instance_key is not None else -1
    return (
        definition.priority.rank,
        parent_order,
        graph_order,
        item_order,
        address.graph_path,
        address.node_id,
        address.instance_key or "",
    )


def _input_refs(
    definition: NodeDefinition,
    states: Mapping[NodeAddress, NodeState],
    fanouts: Mapping[NodeAddress, tuple[str, ...]],
    bundle: CompiledBundle,
) -> tuple[str, ...]:
    refs: set[str] = set()
    for dependency_id in definition.depends_on:
        members = _dependency_members(_dependency_address(definition, dependency_id), states, fanouts, bundle) or ()
        for _, state, _ in members:
            refs.update(state.artifact_refs)
    if definition.address.graph_path and not definition.depends_on:
        # Subgraph entry nodes consume the verified run inputs declared by the Subgraph contract.
        for address, state in states.items():
            if address.is_top_level and state.status in _SUCCESS_TERMINAL:
                refs.update(state.artifact_refs)
    return tuple(sorted(refs))


def _apply_fanout_expansions(
    expansions: Sequence[FanOutExpansion],
    states: dict[NodeAddress, NodeState],
    fanouts: dict[NodeAddress, tuple[str, ...]],
    bundle: CompiledBundle,
) -> bool:
    changed = False
    seen_templates: set[NodeAddress] = set()
    for expansion in expansions:
        if not isinstance(expansion, FanOutExpansion):
            raise RuntimeContractError("fanout_expansions must contain FanOutExpansion values", rule="fanout_expansion")
        if expansion.template in seen_templates:
            raise RuntimeContractError("Fan-out template supplied more than once", rule="fanout_duplicate")
        seen_templates.add(expansion.template)
        graph = bundle.subgraphs.get(expansion.template.graph_path[0]) if expansion.template.graph_path else None
        if graph is None or expansion.template not in graph.dynamic_fanout_templates:
            raise RuntimeContractError("Fan-out expansion does not target a dynamic template", rule="fanout_template")
        definition = bundle.definition(expansion.template)
        if not definition.depends_on:
            raise RuntimeContractError("Dynamic fan-out has no source dependency", rule="fanout_source")
        upstream = NodeAddress(expansion.template.graph_path, definition.depends_on[0])
        upstream_state = states.get(upstream)
        if (
            upstream_state is None
            or upstream_state.status is not NodeStatus.VERIFIED
            or expansion.source_artifact_ref not in upstream_state.artifact_refs
        ):
            raise RuntimeContractError(
                "Fan-out source must be an Artifact of the verified upstream node",
                rule="fanout_source",
                details={"source_artifact_ref": expansion.source_artifact_ref},
            )
        existing = fanouts.get(expansion.template)
        if existing is not None and existing != expansion.item_keys:
            raise RuntimeContractError("Fan-out expansion conflicts with existing item keys", rule="fanout_conflict")
        if existing == expansion.item_keys:
            if any(
                NodeAddress(expansion.template.graph_path, expansion.template.node_id, key) not in states
                for key in expansion.item_keys
            ):
                raise RuntimeContractError("Existing fan-out instances are incomplete", rule="fanout_state")
            continue
        fanouts[expansion.template] = expansion.item_keys
        for key in expansion.item_keys:
            address = NodeAddress(expansion.template.graph_path, expansion.template.node_id, key)
            if address in states:
                raise RuntimeContractError("Fan-out instance collides with existing state", rule="fanout_collision")
            states[address] = NodeState()
        changed = True
    return changed


def _subgraph_is_complete(
    graph_id: str,
    states: Mapping[NodeAddress, NodeState],
    fanouts: Mapping[NodeAddress, tuple[str, ...]],
    bundle: CompiledBundle,
) -> bool:
    graph = bundle.subgraphs[graph_id]
    for template in graph.declaration_order:
        members = _dependency_members(template, states, fanouts, bundle)
        if members is None:
            return False
        for _, state, definition in members:
            if state.status in _SUCCESS_TERMINAL:
                continue
            if state.status is NodeStatus.SKIPPED and not definition.required:
                continue
            return False
    return True


def schedule_snapshot(
    snapshot,
    bundle: CompiledBundle,
    *,
    id_factory: AttemptIdFactory,
    now: Callable[[], str],
    host_max_parallel: int | None,
    host_token_limit: int | None,
    host_cost_limit: float | None,
    requested_nodes: Iterable[NodeAddress] | None = None,
    terminal_events: Iterable[TerminalEvent | str] = (),
    fanout_expansions: Sequence[FanOutExpansion] = (),
) -> ExecutionPlan:
    if snapshot.contract_version != bundle.context.bundle.contract_version:
        raise RuntimeContractError("Snapshot Contract Version does not match the selected Bundle", rule="snapshot_contract_version")
    if snapshot.workflow_id != bundle.workflow_id or snapshot.workflow_version != bundle.workflow_version:
        raise RuntimeContractError("Snapshot Workflow identity does not match the selected Bundle", rule="snapshot_workflow")
    if snapshot.profile_ref != bundle.profile_ref:
        raise RuntimeContractError("Snapshot Profile does not match the selected Bundle", rule="snapshot_profile")
    if snapshot.workflow_status in {WorkflowStatus.COMPLETED, WorkflowStatus.CANCELLED, WorkflowStatus.FAILED}:
        raise RuntimeContractError("A terminal Workflow cannot be scheduled", rule="workflow_terminal")
    if snapshot.workflow_status is WorkflowStatus.PAUSED:
        raise RuntimeContractError(
            "A paused Workflow must be resumed before scheduling",
            code="STATE_VERSION_CONFLICT",
            rule="workflow_paused",
        )
    automated_seconds = sum(attempt.usage.automated_duration_seconds for attempt in snapshot.attempts)
    if automated_seconds >= snapshot.run_policy.automated_run_timeout_minutes * 60:
        paused = snapshot if snapshot.workflow_status is WorkflowStatus.PAUSED else replace(
            snapshot,
            state_version=snapshot.state_version + 1,
            workflow_status=WorkflowStatus.PAUSED,
        )
        return ExecutionPlan(
            SchedulingDecision((), (), (), (), min(snapshot.run_policy.max_parallel, host_max_parallel or snapshot.run_policy.max_parallel), 0),
            (),
            (),
            (),
            paused,
        )
    states = dict(snapshot.node_states)
    fanouts = dict(snapshot.fanout_instances)
    transitions: list[StateTransition] = []
    deferred: list[DeferredNode] = []
    changed = _apply_fanout_expansions(fanout_expansions, states, fanouts, bundle)
    events: set[TerminalEvent] = set()
    for event in terminal_events:
        try:
            events.add(event if isinstance(event, TerminalEvent) else TerminalEvent(event))
        except ValueError as exc:
            raise RuntimeContractError("Unknown terminal event", rule="terminal_event", details={"event": str(event)}) from exc

    requested_values = None if requested_nodes is None else tuple(requested_nodes)
    if requested_values is not None:
        if any(not isinstance(address, NodeAddress) for address in requested_values):
            raise RuntimeContractError("requested_nodes must contain NodeAddress values", rule="requested_node")
        requested = frozenset(requested_values)
        unknown: list[NodeAddress] = []
        for address in requested:
            try:
                definition = bundle.definition(address)
                graph = bundle.top_level if not address.graph_path else bundle.subgraphs[address.graph_path[0]]
                template = NodeAddress(address.graph_path, address.node_id)
                if address.instance_key is not None and template not in graph.dynamic_fanout_templates:
                    unknown.append(address)
                elif address.instance_key is not None and address.instance_key not in fanouts.get(template, ()):
                    unknown.append(address)
                elif definition.address.node_id != address.node_id:
                    unknown.append(address)
            except RuntimeContractError:
                unknown.append(address)
        if unknown:
            raise RuntimeContractError("requested_nodes contains an unknown address", rule="requested_node")
    else:
        requested = None

    def move(address: NodeAddress, target: NodeStatus, reason: str) -> None:
        nonlocal changed
        before = states[address]
        states[address] = transition_node(bundle.definition(address), before, target)
        if target is NodeStatus.SKIPPED:
            try:
                states[address] = replace(states[address], skip_reason=SkipReason(reason))
            except ValueError as exc:
                raise RuntimeContractError("Skip transition requires a declared reason", rule="skip_reason") from exc
        transitions.append(StateTransition(address, before.status, target, reason))
        changed = True

    made_progress = True
    while made_progress:
        made_progress = False
        addresses = sorted(tuple(states), key=lambda item: _sort_key(bundle, item, fanouts))
        for address in addresses:
            state = states[address]
            definition = bundle.definition(address)
            if state.status is NodeStatus.PENDING:
                if not definition.enabled:
                    move(address, NodeStatus.SKIPPED, SkipReason.PROFILE_DISABLED.value)
                    made_progress = True
                    continue
                dependencies_satisfied, dependencies_resolved = _dependencies_state(definition, states, fanouts, bundle)
                triggered = bool(set(definition.trigger_on_terminal_events) & events)
                if not dependencies_satisfied and not triggered:
                    continue
                condition = _condition_state(definition, states)
                if condition is False and dependencies_resolved:
                    move(address, NodeStatus.SKIPPED, SkipReason.CONDITION_NOT_MATCHED.value)
                    made_progress = True
                    continue
                if condition is not True:
                    continue
                move(address, NodeStatus.READY, "dependencies_satisfied" if not triggered else "terminal_event")
                made_progress = True
                state = states[address]

            if state.status is NodeStatus.READY and definition.kind is NodeKind.SUBGRAPH:
                move(address, NodeStatus.RUNNING, "subgraph_activated")
                graph = bundle.subgraphs[address.node_id]
                for child in graph.declaration_order:
                    if child not in graph.dynamic_fanout_templates and child not in states:
                        states[child] = NodeState()
                        changed = True
                made_progress = True
            elif state.status is NodeStatus.READY and definition.kind is NodeKind.HUMAN_GATE:
                move(address, NodeStatus.WAITING_FOR_USER, "gate_waiting")
                made_progress = True
            elif state.status is NodeStatus.READY and definition.kind is NodeKind.EXTERNAL_INPUT:
                move(address, NodeStatus.WAITING_FOR_EXTERNAL, "external_waiting")
                made_progress = True
        for address in bundle.top_level.declaration_order:
            definition = bundle.top_level.definitions[address]
            if definition.kind is not NodeKind.SUBGRAPH or states[address].status is not NodeStatus.RUNNING:
                continue
            if _subgraph_is_complete(address.node_id, states, fanouts, bundle):
                for target, reason in (
                    (NodeStatus.COMPLETED, "subgraph_children_terminal"),
                    (NodeStatus.VERIFYING, "subgraph_aggregate_verification"),
                    (NodeStatus.VERIFIED, "subgraph_verified"),
                ):
                    move(address, target, reason)
                made_progress = True

    ready = tuple(
        sorted(
            (
                address
                for address, state in states.items()
                if state.status in {NodeStatus.READY, NodeStatus.RETRY_READY}
                and bundle.definition(address).kind in _EXECUTABLE_KINDS
            ),
            key=lambda item: _sort_key(bundle, item, fanouts),
        )
    )
    active = sum(attempt.status is AttemptStatus.RUNNING for attempt in snapshot.attempts)
    effective = min(snapshot.run_policy.max_parallel, host_max_parallel or snapshot.run_policy.max_parallel)
    available = max(0, effective - active)
    attempts: list[AttemptRecord] = []
    invocations: list[InvocationRequirements] = []
    reuse: list[str] = []
    selected: list[NodeAddress] = []
    for address in ready:
        if requested is not None and address not in requested:
            deferred.append(DeferredNode(address, "not_requested"))
            continue
        if len(attempts) >= available:
            deferred.append(DeferredNode(address, "global_concurrency_quota"))
            continue
        definition = bundle.definition(address)
        mode = AttemptMode.RETRY if states[address].status is NodeStatus.RETRY_READY else AttemptMode.INITIAL
        candidate, invocation, reuse_attempt_id = plan_attempt(
            replace(snapshot, node_states=states, fanout_instances=fanouts),
            definition,
            bundle,
            input_artifact_refs=_input_refs(definition, states, fanouts, bundle),
            id_factory=id_factory,
            now=now,
            mode=mode,
            host_token_limit=host_token_limit,
            host_cost_limit=host_cost_limit,
        )
        if reuse_attempt_id is not None:
            reuse.append(reuse_attempt_id)
            deferred.append(DeferredNode(address, "verified_reuse_candidate"))
            continue
        assert candidate is not None and invocation is not None
        move(address, NodeStatus.RUNNING, "attempt_planned")
        states[address] = replace(
            states[address],
            active_attempt_id=candidate.attempt_id,
            attempt_count=states[address].attempt_count + 1,
        )
        attempts.append(candidate)
        invocations.append(invocation)
        selected.append(address)

    all_attempts = snapshot.attempts + tuple(attempts)
    running = any(attempt.status is AttemptStatus.RUNNING for attempt in all_attempts)
    if running:
        workflow_status = WorkflowStatus.RUNNING
    elif any(state.status is NodeStatus.WAITING_FOR_USER for state in states.values()):
        workflow_status = WorkflowStatus.WAITING_FOR_USER
    elif any(state.status is NodeStatus.WAITING_FOR_EXTERNAL for state in states.values()):
        workflow_status = WorkflowStatus.WAITING_FOR_EXTERNAL
    else:
        workflow_status = snapshot.workflow_status
    if workflow_status != snapshot.workflow_status:
        changed = True

    next_snapshot = snapshot if not changed else replace(
        snapshot,
        state_version=snapshot.state_version + 1,
        workflow_status=workflow_status,
        node_states=states,
        attempts=all_attempts,
        fanout_instances=fanouts,
        current_gate=next(
            (
                address.node_id
                for address, state in states.items()
                if address.is_top_level and state.status is NodeStatus.WAITING_FOR_USER and bundle.definition(address).kind is NodeKind.HUMAN_GATE
            ),
            None,
        ),
    )
    decision = SchedulingDecision(
        transitions=tuple(transitions),
        ready_nodes=ready,
        selected_nodes=tuple(selected),
        deferred=tuple(deferred),
        effective_max_parallel=effective,
        available_slots=available,
    )
    return ExecutionPlan(decision, tuple(attempts), tuple(invocations), tuple(reuse), next_snapshot)
