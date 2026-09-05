from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from skillgraph_runtime import (
    CreateRunCommand,
    FixtureResearchGapPlannerProvider,
    NodeAddress,
    RuntimeContractError,
    RuntimeKernel,
    RuntimeOperations,
    ResearchGapPlanner,
)
from skillgraph_runtime.domain import GateDecision, NodeState, NodeStatus, VerificationResult, WorkflowStatus
from skillgraph_runtime.storage import RunStorage


ROOT = Path(__file__).resolve().parents[2]


class FixedIds:
    def __init__(self) -> None:
        self.attempt = 0

    def new_run_id(self) -> str:
        return "run_gap"

    def new_attempt_id(self) -> str:
        self.attempt += 1
        return f"ATT-GAP-{self.attempt}"


class FixedClock:
    def __init__(self) -> None:
        self.index = 0

    def now(self) -> str:
        self.index += 1
        return (datetime(2026, 9, 3, tzinfo=timezone.utc) + timedelta(seconds=self.index)).strftime("%Y-%m-%dT%H:%M:%SZ")


def verification_document(
    kernel: RuntimeKernel,
    attempt_id: str,
    *,
    overall: str,
    issue_codes: tuple[str, ...] = ("USER_COVERAGE",),
) -> dict:
    issues = [
        {"code": code, "critical": overall == "FAIL", "message": "Research coverage is incomplete.", "evidence_ids": [], "details": {}}
        for code in issue_codes
    ]
    document = {
        "artifact": {
            "id": "ART-RESEARCH-VERIFICATION-GAP",
            "type": "research_verification",
            "schema_version": "0.3.0",
            "version": 1,
            "produced_by": {"skill": "research-verifier", "attempt": attempt_id},
            "created_at": "2026-09-03T00:00:00Z",
            "supersedes": None,
            "status": "active",
        },
        "verification": {
            "overall": overall,
            "critical_issues": issues if overall == "FAIL" else [],
            "non_critical_issues": issues if overall != "FAIL" else [],
        },
        "sections": {
            "competitor": {"result": "PASS", "issues": []},
            "users": {"result": overall, "issues": issues},
            "market": {"result": "PASS", "issues": []},
            "technology": {"result": "PASS", "issues": []},
        },
    }
    document["artifact"]["content_hash"] = kernel._artifact_content_hash(document)
    return document


def gap_proposal(*, target: str = "users", issue_code: str = "USER_COVERAGE", reuse_artifacts: list[str] | None = None) -> dict:
    skills = {
        "competitor": "competitor-discovery",
        "users": "user-evidence",
        "market": "market-landscape",
        "technology": "oss-tech-landscape",
    }
    return {
        "gaps": [
            {
                "id": f"GAP-{target.upper()}-001",
                "issue_code": issue_code,
                "target_skill": skills[target],
                "required_action": ["Collect the missing evidence for this branch."],
                "reuse_artifacts": reuse_artifacts or [],
                "invalidate": ["research_verifier", "evidence_waiver", "research_synthesis"],
                "retry_targets": [target],
                "return_to": "research_verifier",
            }
        ]
    }


def prepare_gap_attempt(
    tmp_path: Path,
    *,
    overall: str = "FAIL",
    waiver: GateDecision | None = None,
    proposal: dict | None = None,
    issue_codes: tuple[str, ...] = ("USER_COVERAGE",),
) -> tuple[RuntimeKernel, RuntimeOperations, str, str]:
    kernel = RuntimeKernel(ROOT, storage_root=tmp_path, id_factory=FixedIds(), clock=FixedClock())
    created = kernel.create_persisted_run(CreateRunCommand("Plan a traceable research retry", "developer_tool"))
    run_id = created.run_id
    snapshot = kernel.load_run(run_id)
    states = dict(snapshot.node_states)
    states[NodeAddress((), "gate_research")] = NodeState(status=NodeStatus.APPROVED, gate_decision=GateDecision.APPROVE)
    for node_id in ("competitor", "users", "market", "technology"):
        states[NodeAddress((), node_id)] = NodeState(status=NodeStatus.VERIFIED)
    states[NodeAddress((), "evidence_waiver")] = NodeState(status=NodeStatus.SKIPPED)
    prepared = replace(snapshot, state_version=snapshot.state_version + 1, workflow_status=WorkflowStatus.RUNNING, node_states=states)
    kernel._persist(prepared, events=({"event": "TEST_RESEARCH_READY"},))

    verifier_plan = kernel.schedule_persisted(run_id, requested_nodes=(NodeAddress((), "research_verifier"),))
    verifier_attempt = verifier_plan.attempts_to_start[0].attempt_id
    kernel.complete_persisted_business_attempt(
        run_id,
        verifier_attempt,
        [
            (
                "artifacts/03-analysis/research-verification.yaml",
                verification_document(kernel, verifier_attempt, overall=overall, issue_codes=issue_codes),
            )
        ],
    )
    verified = kernel.load_run(run_id)
    states = dict(verified.node_states)
    states[NodeAddress((), "research_verifier")] = replace(
        states[NodeAddress((), "research_verifier")],
        verification_result=VerificationResult(overall),
    )
    if waiver is not None:
        states[NodeAddress((), "evidence_waiver")] = NodeState(status=NodeStatus.APPROVED, gate_decision=waiver)
    prepared_gap = replace(verified, state_version=verified.state_version + 1, node_states=states)
    kernel._persist(prepared_gap, events=({"event": "TEST_VERIFICATION_CLASSIFIED"},))

    gap_plan = kernel.schedule_persisted(run_id, requested_nodes=(NodeAddress((), "research_gap"),))
    gap_attempt = gap_plan.attempts_to_start[0].attempt_id
    planner = ResearchGapPlanner(kernel, FixtureResearchGapPlannerProvider(proposal or gap_proposal()))
    return kernel, RuntimeOperations(kernel, research_gap_planner=planner), run_id, gap_attempt


def test_fail_verification_plans_users_retry_and_preserves_unaffected_branches(tmp_path: Path):
    kernel, operations, run_id, gap_attempt = prepare_gap_attempt(tmp_path)

    result = operations.execute_p0_05_attempt(run_id, gap_attempt)
    snapshot = kernel.load_run(run_id)
    storage = RunStorage(tmp_path, run_id)
    manifest = storage._manifest()

    assert result["outcome"] == "RESEARCH_GAP_PLANNED"
    assert result["retry_targets"] == ["users"]
    assert result["scheduled_attempt_ids"]
    assert snapshot.global_research_cycle == 1
    assert snapshot.node_states[NodeAddress((), "users")].status is NodeStatus.RUNNING
    assert snapshot.node_states[NodeAddress((), "market")].status is NodeStatus.VERIFIED
    assert snapshot.node_states[NodeAddress((), "technology")].status is NodeStatus.VERIFIED
    assert snapshot.node_states[NodeAddress((), "research_verifier")].status is NodeStatus.PENDING
    assert manifest["current_artifacts"]["research_gap"]["artifact_ref"] == result["artifact_ref"]
    gap = storage.read_artifact(result["artifact_ref"])
    assert gap["artifact"]["produced_by"]["attempt"] == gap_attempt
    assert gap["gaps"][0]["retry_targets"] == ["users"]

    restored = RuntimeKernel(ROOT, storage_root=tmp_path, id_factory=FixedIds(), clock=FixedClock())
    assert restored.load_run(run_id).global_research_cycle == 1


def test_request_more_research_waiver_can_trigger_gap(tmp_path: Path):
    kernel, operations, run_id, gap_attempt = prepare_gap_attempt(
        tmp_path,
        overall="PARTIAL",
        waiver=GateDecision.REQUEST_MORE_RESEARCH,
    )

    result = operations.execute_p0_05_attempt(run_id, gap_attempt)

    assert result["outcome"] == "RESEARCH_GAP_PLANNED"
    assert kernel.load_run(run_id).global_research_cycle == 1


def test_competitor_root_retry_restarts_the_subgraph_discovery_entry(tmp_path: Path):
    kernel, operations, run_id, gap_attempt = prepare_gap_attempt(
        tmp_path,
        proposal=gap_proposal(target="competitor"),
    )

    before = kernel.load_run(run_id)
    stale_template = NodeAddress(("competitor",), "deep_dive")
    stale_instance = NodeAddress(("competitor",), "deep_dive", "cmp_old")
    states = dict(before.node_states)
    states[stale_instance] = NodeState(status=NodeStatus.VERIFIED)
    with_stale_fanout = replace(
        before,
        state_version=before.state_version + 1,
        node_states=states,
        fanout_instances={**before.fanout_instances, stale_template: ("cmp_old",)},
    )
    kernel._persist(with_stale_fanout, events=({"event": "TEST_STALE_COMPETITOR_FANOUT"},))

    result = operations.execute_p0_05_attempt(run_id, gap_attempt)
    snapshot = kernel.load_run(run_id)

    assert result["retry_targets"] == ["competitor"]
    assert result["scheduled_attempt_ids"]
    assert snapshot.node_states[NodeAddress((), "competitor")].status is NodeStatus.RUNNING
    assert snapshot.node_states[NodeAddress(("competitor",), "discovery")].status is NodeStatus.RUNNING
    assert stale_instance not in snapshot.node_states
    assert stale_template not in snapshot.fanout_instances


@pytest.mark.parametrize(
    ("proposal", "rule"),
    [
        (gap_proposal(issue_code="UNKNOWN"), "research_gap_issue_coverage"),
        ({**gap_proposal(), "gaps": [{**gap_proposal()["gaps"][0], "target_skill": "research-verifier"}]}, "research_gap_target_skill"),
        ({**gap_proposal(), "gaps": [{**gap_proposal()["gaps"][0], "retry_targets": ["users", "market"]}]}, "research_gap_retry_targets"),
        ({**gap_proposal(), "gaps": [{**gap_proposal()["gaps"][0], "invalidate": ["research_verifier"]}]}, "research_gap_invalidation"),
        (gap_proposal(reuse_artifacts=["ART-NOT-CURRENT@1"]), "research_gap_reuse_artifacts"),
    ],
)
def test_invalid_gap_proposals_fail_closed_without_state_change(tmp_path: Path, proposal: dict, rule: str):
    kernel, operations, run_id, gap_attempt = prepare_gap_attempt(tmp_path, proposal=proposal)
    before = kernel.load_run(run_id)
    before_manifest = RunStorage(tmp_path, run_id)._manifest()

    with pytest.raises(RuntimeContractError) as captured:
        operations.execute_p0_05_attempt(run_id, gap_attempt)

    assert captured.value.rule == rule
    assert kernel.load_run(run_id).state_version == before.state_version
    assert RunStorage(tmp_path, run_id)._manifest() == before_manifest


def test_rejects_broad_retry_and_exhausted_cycle_without_writing_artifact(tmp_path: Path):
    broad = {
        "gaps": [
            *[
                {**gap_proposal(target=target)["gaps"][0], "id": f"GAP-{target.upper()}-001", "issue_code": f"ISSUE-{target.upper()}"}
                for target in ("competitor", "users", "market", "technology")
            ]
        ]
    }
    kernel, operations, run_id, gap_attempt = prepare_gap_attempt(
        tmp_path,
        proposal=broad,
        issue_codes=("ISSUE-COMPETITOR", "ISSUE-USERS", "ISSUE-MARKET", "ISSUE-TECHNOLOGY"),
    )
    before = kernel.load_run(run_id)

    with pytest.raises(RuntimeContractError) as broad_error:
        operations.execute_p0_05_attempt(run_id, gap_attempt)
    assert broad_error.value.rule == "research_gap_broad_retry"
    assert kernel.load_run(run_id).state_version == before.state_version

    kernel, operations, run_id, gap_attempt = prepare_gap_attempt(tmp_path / "limit")
    snapshot = kernel.load_run(run_id)
    exhausted = replace(snapshot, state_version=snapshot.state_version + 1, global_research_cycle=snapshot.run_policy.max_global_research_cycles)
    kernel._persist(exhausted, events=({"event": "TEST_CYCLE_EXHAUSTED"},))

    with pytest.raises(RuntimeContractError) as limit_error:
        operations.execute_p0_05_attempt(run_id, gap_attempt)
    assert limit_error.value.code == "RESEARCH_LIMIT_REACHED"
    assert limit_error.value.rule == "research_gap_cycle_limit"
    assert "research_gap" not in (RunStorage(tmp_path / "limit", run_id)._manifest() or {}).get("current_artifacts", {})


def test_disabled_branch_cannot_be_selected_after_provider_proposal(tmp_path: Path):
    kernel, operations, run_id, gap_attempt = prepare_gap_attempt(tmp_path)
    snapshot = kernel.load_run(run_id)
    states = dict(snapshot.node_states)
    states[NodeAddress((), "users")] = NodeState(status=NodeStatus.SKIPPED)
    disabled = replace(snapshot, state_version=snapshot.state_version + 1, node_states=states)
    kernel._persist(disabled, events=({"event": "TEST_BRANCH_DISABLED"},))

    with pytest.raises(RuntimeContractError) as captured:
        operations.execute_p0_05_attempt(run_id, gap_attempt)

    assert captured.value.rule == "research_gap_target_skill"
