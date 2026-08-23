from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

from skillgraph_runtime.domain import (
    AttemptStatus,
    CreateRunCommand,
    FanOutExpansion,
    FeasibilityResult,
    GateDecision,
    NodeAddress,
    NodeState,
    NodeStatus,
    TerminalEvent,
    VerificationResult,
    WorkflowStatus,
)
from skillgraph_runtime.errors import RuntimeContractError
from skillgraph_runtime.kernel import RuntimeKernel


ROOT = Path(__file__).resolve().parents[2]


class SequentialIds:
    def __init__(self) -> None:
        self.attempt = 0

    def new_run_id(self) -> str:
        return "run_scheduler"

    def new_attempt_id(self) -> str:
        self.attempt += 1
        return f"ATT-SCHED-{self.attempt:03d}"


class FixedClock:
    def now(self) -> str:
        return "2026-08-14T00:00:00Z"


def kernel(*, host_max_parallel: int = 4) -> RuntimeKernel:
    return RuntimeKernel(ROOT, host_max_parallel=host_max_parallel, id_factory=SequentialIds(), clock=FixedClock())


def new_snapshot(runtime: RuntimeKernel):
    return runtime.create_run(CreateRunCommand("deterministic product idea", "developer_tool"))


def with_states(snapshot, **states: NodeState):
    updated = dict(snapshot.node_states)
    updated.update({NodeAddress((), node_id): state for node_id, state in states.items()})
    return replace(snapshot, node_states=updated)


def settle_attempts(snapshot):
    return replace(
        snapshot,
        attempts=tuple(replace(attempt, status=AttemptStatus.COMPLETED, finished_at="2026-08-14T00:01:00Z") for attempt in snapshot.attempts),
    )


def test_dependency_requires_verified_not_completed_and_noop_keeps_version():
    runtime = kernel()
    snapshot = with_states(new_snapshot(runtime), idea=NodeState(status=NodeStatus.COMPLETED))
    plan = runtime.schedule(snapshot)
    assert not plan.attempts_to_start
    assert plan.next_snapshot is snapshot

    snapshot = with_states(snapshot, idea=NodeState(status=NodeStatus.VERIFIED, artifact_refs=("ART-IDEA@1",)))
    plan = runtime.schedule(snapshot, requested_nodes=(NodeAddress((), "contract"),))
    assert [attempt.address.node_id for attempt in plan.attempts_to_start] == ["contract"]


def test_scalar_list_any_of_and_condition_skip_are_deterministic():
    runtime = kernel()
    base = new_snapshot(runtime)

    proof_source = with_states(
        base,
        feasibility=NodeState(status=NodeStatus.VERIFIED, feasibility_result=FeasibilityResult.BLOCKED),
    )
    proof = runtime.schedule(proof_source, requested_nodes=(NodeAddress((), "proof"),))
    assert proof.decision.selected_nodes == (NodeAddress((), "proof"),)

    scope_source = with_states(
        base,
        feasibility=NodeState(status=NodeStatus.VERIFIED, feasibility_result=FeasibilityResult.FEASIBLE),
    )
    scope = runtime.schedule(scope_source, requested_nodes=(NodeAddress((), "scope"),))
    assert scope.decision.selected_nodes == (NodeAddress((), "scope"),)

    synthesis_source = with_states(
        base,
        research_verifier=NodeState(status=NodeStatus.VERIFIED, verification_result=VerificationResult.PASS),
        evidence_waiver=NodeState(status=NodeStatus.SKIPPED),
    )
    synthesis = runtime.schedule(synthesis_source, requested_nodes=(NodeAddress((), "research_synthesis"),))
    assert synthesis.decision.selected_nodes == (NodeAddress((), "research_synthesis"),)

    skipped = runtime.schedule(
        with_states(base, feasibility=NodeState(status=NodeStatus.VERIFIED, feasibility_result=FeasibilityResult.BLOCKED)),
        requested_nodes=(NodeAddress((), "scope"),),
    )
    scope_state = skipped.next_snapshot.node_states[NodeAddress((), "scope")]
    assert scope_state.status is NodeStatus.SKIPPED
    assert scope_state.skip_reason is not None


def test_terminal_event_is_an_alternative_activation_path():
    runtime = kernel()
    plan = runtime.schedule(
        new_snapshot(runtime),
        requested_nodes=(NodeAddress((), "build_readiness_verifier"),),
        terminal_events=(TerminalEvent.PRD_CONSISTENCY_FAILED,),
    )
    assert plan.decision.selected_nodes == (NodeAddress((), "build_readiness_verifier"),)


def test_subgraph_container_uses_no_slot_and_children_share_global_quota():
    runtime = kernel(host_max_parallel=3)
    snapshot = with_states(
        new_snapshot(runtime),
        idea=NodeState(status=NodeStatus.VERIFIED, artifact_refs=("ART-IDEA@1",)),
        contract=NodeState(status=NodeStatus.VERIFIED, artifact_refs=("ART-CONTRACT@1",)),
        gate_research=NodeState(status=NodeStatus.APPROVED, gate_decision=GateDecision.APPROVE),
    )
    plan = runtime.schedule(snapshot)
    assert NodeAddress((), "competitor") not in plan.decision.selected_nodes
    assert NodeAddress(("competitor",), "discovery") in plan.decision.selected_nodes
    assert len(plan.attempts_to_start) == 3
    assert [address.node_id for address in plan.decision.selected_nodes] == ["discovery", "users", "technology"]
    assert plan.decision.effective_max_parallel == 3


def test_top_level_research_fanout_and_static_analysis_fanout_are_stable():
    runtime = kernel(host_max_parallel=4)
    snapshot = with_states(
        new_snapshot(runtime),
        idea=NodeState(status=NodeStatus.VERIFIED, artifact_refs=("ART-IDEA@1",)),
        contract=NodeState(status=NodeStatus.VERIFIED, artifact_refs=("ART-CONTRACT@1",)),
        gate_research=NodeState(status=NodeStatus.APPROVED, gate_decision=GateDecision.APPROVE),
    )
    top = runtime.schedule(snapshot)
    assert [address.node_id for address in top.decision.selected_nodes] == [
        "discovery", "users", "technology", "market"
    ]

    compiled = runtime.compiled_bundle_for(snapshot)
    states = dict(snapshot.node_states)
    states[NodeAddress((), "competitor")] = NodeState(status=NodeStatus.RUNNING)
    analysis_ids = ("feature_analysis", "traction_analysis", "review_analysis", "pricing_analysis")
    for address in compiled.subgraphs["competitor"].declaration_order:
        if address.node_id == "deep_dive":
            continue
        states[address] = NodeState(
            status=NodeStatus.PENDING if address.node_id in analysis_ids else NodeStatus.VERIFIED,
            artifact_refs=("ART-NORMALIZED@1",) if address.node_id == "normalizer" else (),
        )
    static_source = replace(snapshot, node_states=states)
    static = runtime.schedule(
        static_source,
        requested_nodes=tuple(NodeAddress(("competitor",), node_id) for node_id in analysis_ids),
    )
    assert [address.node_id for address in static.decision.selected_nodes] == list(analysis_ids)


def test_required_skip_blocks_but_profile_optional_skip_satisfies_dependency():
    verified = NodeState(status=NodeStatus.VERIFIED)
    skipped = NodeState(status=NodeStatus.SKIPPED)

    required_runtime = kernel()
    required = with_states(
        new_snapshot(required_runtime),
        competitor=verified,
        users=verified,
        market=verified,
        technology=skipped,
    )
    blocked = required_runtime.schedule(required, requested_nodes=(NodeAddress((), "research_verifier"),))
    assert not blocked.attempts_to_start

    optional_runtime = RuntimeKernel(ROOT, id_factory=SequentialIds(), clock=FixedClock())
    optional = optional_runtime.create_run(CreateRunCommand("idea", "consumer_app"))
    optional = with_states(optional, competitor=verified, users=verified, market=verified, technology=skipped)
    allowed = optional_runtime.schedule(optional, requested_nodes=(NodeAddress((), "research_verifier"),))
    assert allowed.decision.selected_nodes == (NodeAddress((), "research_verifier"),)


def test_terminal_workflow_and_snapshot_identity_fail_closed():
    runtime = kernel()
    snapshot = new_snapshot(runtime)
    with pytest.raises(RuntimeContractError) as terminal:
        runtime.schedule(replace(snapshot, workflow_status=WorkflowStatus.COMPLETED))
    assert terminal.value.rule == "workflow_terminal"

    with pytest.raises(RuntimeContractError) as identity:
        runtime.schedule(replace(snapshot, workflow_version="9.9.9"))
    assert identity.value.rule == "snapshot_workflow"

    with pytest.raises(RuntimeContractError) as requested:
        runtime.schedule(snapshot, requested_nodes=("idea",))
    assert requested.value.rule == "requested_node"



def test_dynamic_fanout_has_hierarchical_identity_stable_order_and_fanin():
    runtime = kernel(host_max_parallel=2)
    snapshot = with_states(
        new_snapshot(runtime),
        gate_research=NodeState(status=NodeStatus.APPROVED, gate_decision=GateDecision.APPROVE),
    )
    first = runtime.schedule(snapshot, requested_nodes=(NodeAddress(("competitor",), "discovery"),))
    states = dict(first.next_snapshot.node_states)
    states[NodeAddress(("competitor",), "discovery")] = NodeState(
        status=NodeStatus.VERIFIED,
        artifact_refs=("ART-CANDIDATES@1",),
    )
    second_source = settle_attempts(replace(first.next_snapshot, node_states=states))
    second = runtime.schedule(second_source, requested_nodes=(NodeAddress(("competitor",), "candidate_ranking"),))
    states = dict(second.next_snapshot.node_states)
    states[NodeAddress(("competitor",), "candidate_ranking")] = NodeState(
        status=NodeStatus.VERIFIED,
        artifact_refs=("ART-RANKING@1",),
    )
    expansion_source = settle_attempts(replace(second.next_snapshot, node_states=states))
    keys = ("cmp_alpha", "cmp_beta", "cmp_gamma")
    instances = tuple(NodeAddress(("competitor",), "deep_dive", key) for key in keys)
    expanded = runtime.schedule(
        expansion_source,
        requested_nodes=instances,
        fanout_expansions=(
            FanOutExpansion(NodeAddress(("competitor",), "deep_dive"), "ART-RANKING@1", keys),
        ),
    )
    assert expanded.decision.selected_nodes == instances[:2]
    assert any(item.address == instances[2] and item.reason == "global_concurrency_quota" for item in expanded.decision.deferred)
    assert len(set(instances)) == 3
    assert expanded.next_snapshot.node_states[NodeAddress(("competitor",), "normalizer")].status is NodeStatus.PENDING

    completed_states = dict(expanded.next_snapshot.node_states)
    for address in instances:
        completed_states[address] = NodeState(status=NodeStatus.VERIFIED, artifact_refs=(f"ART-{address.instance_key}@1",))
    fanin_source = settle_attempts(replace(expanded.next_snapshot, node_states=completed_states))
    fanin = runtime.schedule(fanin_source, requested_nodes=(NodeAddress(("competitor",), "normalizer"),))
    assert fanin.decision.selected_nodes == (NodeAddress(("competitor",), "normalizer"),)
