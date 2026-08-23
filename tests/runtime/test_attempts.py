from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

from skillgraph_runtime.attempts import input_fingerprint, plan_attempt, resume_interactive_attempt
from skillgraph_runtime.domain import (
    AttemptMode,
    AttemptStatus,
    BudgetLimits,
    CreateRunCommand,
    NodeAddress,
    NodeState,
    NodeStatus,
    PermissionSet,
)
from skillgraph_runtime.kernel import RuntimeKernel
from skillgraph_runtime.errors import RuntimeContractError


ROOT = Path(__file__).resolve().parents[2]


class SequentialIds:
    def __init__(self) -> None:
        self.run = 0
        self.attempt = 0

    def new_run_id(self) -> str:
        self.run += 1
        return f"run_attempt_{self.run}"

    def new_attempt_id(self) -> str:
        self.attempt += 1
        return f"ATT-PLAN-{self.attempt}"


class FixedClock:
    def now(self) -> str:
        return "2026-08-14T01:02:03Z"


def runtime() -> RuntimeKernel:
    return RuntimeKernel(ROOT, id_factory=SequentialIds(), clock=FixedClock())


def test_fingerprint_is_stable_for_set_fields_but_preserves_business_array_order():
    permissions_a = PermissionSet("read_only", ("b/path", "a/path"))
    permissions_b = PermissionSet("read_only", ("a/path", "b/path"))
    budget = BudgetLimits(20, 10, 100, 1.5)
    arguments = dict(
        skill_ref="test-skill@0.2.0",
        input_artifact_refs=("ART-B@1", "ART-A@1"),
        profile_ref="developer_tool@0.2.0",
        research_contract_ref="ART-CONTRACT@1",
        relevant_config={"ordered": ["first", "second"], "mapping": {"b": 2, "a": 1}},
        budget=budget,
    )
    first = input_fingerprint(permissions=permissions_a, **arguments)
    second = input_fingerprint(permissions=permissions_b, **{**arguments, "input_artifact_refs": ("ART-A@1", "ART-B@1")})
    changed = input_fingerprint(
        permissions=permissions_b,
        **{**arguments, "relevant_config": {"ordered": ["second", "first"], "mapping": {"a": 1, "b": 2}}},
    )
    assert first == second
    assert first != changed
    assert first.startswith("sha256:") and len(first) == 71


def test_retry_appends_new_attempt_and_increments_count():
    kernel = runtime()
    snapshot = kernel.create_run(CreateRunCommand("idea", "developer_tool"))
    initial = kernel.schedule(snapshot)
    first_attempt = replace(initial.attempts_to_start[0], status=AttemptStatus.FAILED, finished_at="2026-08-14T01:03:00Z")
    states = dict(initial.next_snapshot.node_states)
    states[NodeAddress((), "idea")] = replace(
        states[NodeAddress((), "idea")],
        status=NodeStatus.RETRY_READY,
        active_attempt_id=None,
    )
    retry_source = replace(initial.next_snapshot, node_states=states, attempts=(first_attempt,))
    retry = kernel.schedule(retry_source)
    assert len(retry.next_snapshot.attempts) == 2
    assert retry.attempts_to_start[0].mode is AttemptMode.RETRY
    assert retry.attempts_to_start[0].attempt_id != first_attempt.attempt_id
    assert retry.next_snapshot.node_states[NodeAddress((), "idea")].attempt_count == 2


def test_verified_fingerprint_is_only_a_reuse_candidate_and_refresh_forces_new_attempt():
    kernel = runtime()
    snapshot = kernel.create_run(CreateRunCommand("idea", "developer_tool"))
    initial = kernel.schedule(snapshot)
    verified_attempt = replace(
        initial.attempts_to_start[0],
        status=AttemptStatus.COMPLETED,
        finished_at="2026-08-14T01:03:00Z",
        verified=True,
    )
    states = dict(initial.next_snapshot.node_states)
    states[NodeAddress((), "idea")] = NodeState()
    source = replace(initial.next_snapshot, node_states=states, attempts=(verified_attempt,))
    reuse = kernel.schedule(source)
    assert reuse.reuse_candidates == (verified_attempt.attempt_id,)
    assert not reuse.attempts_to_start
    assert reuse.next_snapshot.node_states[NodeAddress((), "idea")].status is NodeStatus.READY

    bundle = kernel.compiled_bundle_for(source)
    refreshed, _, candidate = plan_attempt(
        source,
        bundle.definition(NodeAddress((), "idea")),
        bundle,
        input_artifact_refs=(),
        id_factory=kernel.id_factory,
        now=kernel.clock.now,
        mode=AttemptMode.REFRESH,
    )
    assert candidate is None
    assert refreshed is not None and refreshed.attempt_id != verified_attempt.attempt_id


def test_interaction_resume_reuses_attempt_identity_and_count():
    kernel = runtime()
    snapshot = kernel.create_run(CreateRunCommand("idea", "developer_tool"))
    initial = kernel.schedule(snapshot)
    attempt = replace(initial.attempts_to_start[0], status=AttemptStatus.WAITING_FOR_USER)
    states = dict(initial.next_snapshot.node_states)
    states[NodeAddress((), "idea")] = replace(
        states[NodeAddress((), "idea")],
        status=NodeStatus.WAITING_FOR_USER,
        interaction_checkpoint_ref="runtime/attempts/ATT-PLAN-1/checkpoints/CP-1.json",
    )
    waiting = replace(initial.next_snapshot, node_states=states, attempts=(attempt,))
    resumed = resume_interactive_attempt(waiting, NodeAddress((), "idea"), kernel.compiled_bundle_for(waiting))
    assert len(resumed.attempts) == 1
    assert resumed.attempts[0].attempt_id == attempt.attempt_id
    assert resumed.attempts[0].status is AttemptStatus.RUNNING
    assert resumed.node_states[NodeAddress((), "idea")].attempt_count == 1


def test_attempt_ids_are_append_only_and_unique():
    kernel = runtime()
    snapshot = kernel.create_run(CreateRunCommand("idea", "developer_tool"))
    initial = kernel.schedule(snapshot)
    source = replace(
        initial.next_snapshot,
        attempts=(replace(initial.attempts_to_start[0], status=AttemptStatus.FAILED, finished_at="2026-08-14T01:03:00Z"),),
    )

    class DuplicateId:
        def new_attempt_id(self) -> str:
            return source.attempts[0].attempt_id

    bundle = kernel.compiled_bundle_for(source)
    with pytest.raises(RuntimeContractError) as caught:
        plan_attempt(
            source,
            bundle.definition(NodeAddress((), "idea")),
            bundle,
            input_artifact_refs=(),
            id_factory=DuplicateId(),
            now=kernel.clock.now,
            mode=AttemptMode.REFRESH,
        )
    assert caught.value.rule == "attempt_id_duplicate"
