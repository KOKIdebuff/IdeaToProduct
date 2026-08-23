from __future__ import annotations

from dataclasses import replace

import pytest

from skillgraph_runtime.domain import (
    AdapterType,
    AttemptMode,
    AttemptRecord,
    AttemptStatus,
    BudgetLimits,
    FeasibilityResult,
    GateDecision,
    NodeAddress,
    NodeDefinition,
    NodeKind,
    NodeState,
    NodeStatus,
    PermissionSet,
    ReadinessStatus,
    VerificationResult,
    WorkflowStatus,
    ProofOutcome,
    SkipReason,
)
from skillgraph_runtime.errors import RuntimeContractError
from skillgraph_runtime.transitions import transition_attempt, transition_node, transition_workflow


def definition(kind: NodeKind = NodeKind.SKILL, *, interactive: bool = False) -> NodeDefinition:
    return NodeDefinition(
        address=NodeAddress((), "idea"),
        kind=kind,
        implementation_ref="idea-intake" if kind in {NodeKind.SKILL, NodeKind.VERIFIER} else None,
        interactive=interactive,
    )


def attempt(status: AttemptStatus = AttemptStatus.RUNNING) -> AttemptRecord:
    return AttemptRecord(
        attempt_id="ATT-001",
        run_id="run_001",
        address=NodeAddress((), "idea"),
        skill_ref="idea-intake@0.2.0",
        status=status,
        mode=AttemptMode.INITIAL,
        input_fingerprint="sha256:" + "0" * 64,
        input_artifact_refs=(),
        profile_ref="developer_tool@0.2.0",
        research_contract_ref=None,
        permissions=PermissionSet("none", ("artifacts/00-intake/idea-definition.yaml",)),
        budget=BudgetLimits(20, 0, None, None),
        allowed_adapter_types=(AdapterType.HOST_AGENT,),
        started_at="2026-08-14T00:00:00Z",
    )


def test_domain_enums_are_strictly_separate_types():
    assert NodeStatus.BLOCKED != FeasibilityResult.BLOCKED
    assert NodeStatus.VERIFIED != VerificationResult.PASS
    assert GateDecision.APPROVE != ReadinessStatus.READY_FOR_BUILD
    assert NodeStatus.BLOCKED.value == FeasibilityResult.BLOCKED.value


def test_runtime_enum_values_match_the_frozen_v02_wire_sets():
    assert {item.value for item in NodeKind} == {
        "skill", "subgraph", "human_gate", "verifier", "router", "external_input"
    }
    assert {item.value for item in NodeStatus} == {
        "PENDING", "READY", "RUNNING", "COMPLETED", "VERIFYING", "VERIFIED",
        "WAITING_FOR_USER", "WAITING_FOR_EXTERNAL", "APPROVED", "BLOCKED",
        "FAILED", "RETRY_READY", "SKIPPED", "INVALIDATED",
    }
    assert {item.value for item in VerificationResult} == {"PASS", "PARTIAL", "FAIL"}
    assert {item.value for item in GateDecision} == {
        "APPROVE", "MODIFY", "CANCEL", "SELECT_OTHER", "REQUEST_MORE_RESEARCH", "PARTIAL_ACCEPTED"
    }
    assert {item.value for item in FeasibilityResult} == {
        "FEASIBLE", "CONDITIONALLY_FEASIBLE", "BLOCKED", "NOT_FEASIBLE"
    }
    assert {item.value for item in ProofOutcome} == {"PASS", "FAIL", "INCONCLUSIVE"}
    assert {item.value for item in AdapterType} == {"fixture", "manual", "host_agent"}
    assert {item.value for item in SkipReason} == {
        "PROFILE_DISABLED", "CONDITION_NOT_MATCHED", "APPROVED_OPTIONAL_SKIP", "TERMINAL_BRANCH_NOT_SELECTED"
    }


def test_skill_and_verifier_happy_path_is_guarded():
    node = definition()
    state = NodeState()
    for target in (
        NodeStatus.READY,
        NodeStatus.RUNNING,
        NodeStatus.COMPLETED,
        NodeStatus.VERIFYING,
        NodeStatus.VERIFIED,
        NodeStatus.INVALIDATED,
        NodeStatus.PENDING,
    ):
        state = transition_node(node, state, target)
    assert state.status is NodeStatus.PENDING


def test_retry_and_interactive_resume_paths_are_distinct():
    plain = definition()
    failed = transition_node(plain, NodeState(status=NodeStatus.RUNNING), NodeStatus.FAILED)
    retry_ready = transition_node(plain, failed, NodeStatus.RETRY_READY)
    assert transition_node(plain, retry_ready, NodeStatus.RUNNING).status is NodeStatus.RUNNING

    interactive = definition(interactive=True)
    waiting = transition_node(interactive, NodeState(status=NodeStatus.RUNNING), NodeStatus.WAITING_FOR_USER)
    assert transition_node(interactive, waiting, NodeStatus.RUNNING).status is NodeStatus.RUNNING
    with pytest.raises(RuntimeContractError, match="Illegal skill node transition"):
        transition_node(plain, NodeState(status=NodeStatus.RUNNING), NodeStatus.WAITING_FOR_USER)


def test_gate_and_external_waiting_paths_are_kind_specific():
    gate = definition(NodeKind.HUMAN_GATE)
    gate_waiting = transition_node(gate, NodeState(status=NodeStatus.READY), NodeStatus.WAITING_FOR_USER)
    assert transition_node(gate, gate_waiting, NodeStatus.APPROVED).status is NodeStatus.APPROVED

    external = definition(NodeKind.EXTERNAL_INPUT)
    external_waiting = transition_node(external, NodeState(status=NodeStatus.READY), NodeStatus.WAITING_FOR_EXTERNAL)
    assert transition_node(external, external_waiting, NodeStatus.COMPLETED).status is NodeStatus.COMPLETED


def test_illegal_transition_raises_without_mutating_original_state():
    state = NodeState(status=NodeStatus.PENDING)
    with pytest.raises(RuntimeContractError) as caught:
        transition_node(definition(), state, NodeStatus.VERIFIED)
    assert caught.value.code == "INPUT_INVALID"
    assert caught.value.rule == "node_transition"
    assert state == NodeState(status=NodeStatus.PENDING)


def test_workflow_and_attempt_transition_guards():
    assert transition_workflow(WorkflowStatus.CREATED, WorkflowStatus.RUNNING) is WorkflowStatus.RUNNING
    with pytest.raises(RuntimeContractError):
        transition_workflow(WorkflowStatus.COMPLETED, WorkflowStatus.RUNNING)

    waiting = transition_attempt(attempt(), AttemptStatus.WAITING_FOR_USER)
    assert waiting.finished_at is None
    resumed = transition_attempt(waiting, AttemptStatus.RUNNING)
    completed = transition_attempt(resumed, AttemptStatus.COMPLETED, finished_at="2026-08-14T00:01:00Z")
    assert completed.finished_at is not None
    with pytest.raises(RuntimeContractError):
        transition_attempt(replace(completed, status=AttemptStatus.COMPLETED), AttemptStatus.RUNNING)
