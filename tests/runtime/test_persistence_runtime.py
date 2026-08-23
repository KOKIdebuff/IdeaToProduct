from __future__ import annotations

import hashlib
import json
from dataclasses import replace
from pathlib import Path

import pytest

from skillgraph_runtime import CreateRunCommand, NodeAddress, RuntimeContractError, RuntimeKernel
from skillgraph_runtime.domain import AttemptStatus, GateDecision, NodeState, NodeStatus, WorkflowStatus
from skillgraph_runtime.error_policy import all_error_codes, validate_structured_error
from skillgraph_runtime.storage import RunStorage


ROOT = Path(__file__).resolve().parents[2]


class FixedIds:
    def __init__(self) -> None:
        self.attempt = 0

    def new_run_id(self) -> str:
        return "run_persisted"

    def new_attempt_id(self) -> str:
        self.attempt += 1
        return f"ATT-PERSIST-{self.attempt}"


class FixedClock:
    def __init__(self) -> None:
        self.index = 0

    def now(self) -> str:
        self.index += 1
        return f"2026-08-19T00:00:{self.index:02d}Z"


def runtime(tmp_path: Path) -> RuntimeKernel:
    return RuntimeKernel(ROOT, storage_root=tmp_path, id_factory=FixedIds(), clock=FixedClock())


def waiting_result(snapshot):
    attempt = snapshot.attempts[0]
    return {
        "executor_result": {
            "schema_version": snapshot.contract_version,
            "run_id": snapshot.run_id,
            "node_id": attempt.address.node_id,
            "attempt_id": attempt.attempt_id,
            "status": "WAITING_FOR_USER",
            "output_artifact_refs": [],
            "source_upserts": [],
            "interaction_request": {
                "method": "clarification",
                "question_id": "IQ-001",
                "round": 1,
                "dimension": "user",
                "prompt": "Which user should be prioritized?",
                "options": [],
                "recommendation": None,
                "allow_freeform_answer": True,
            },
            "interaction_checkpoint": {
                "checkpoint_id": "CP-001",
                "checkpoint_version": 1,
                "round": 1,
                "current_method": "clarification",
                "target_unknown_id": "UNK-USER-001",
                "target_dimension": "user",
                "selection_rationale": "User identity remains unresolved.",
                "completion_status": "IN_PROGRESS",
            },
            "usage": {
                "automated_duration_seconds": 3.5,
                "source_count": 0,
                "input_tokens": 10,
                "output_tokens": 12,
                "estimated_cost": 0.01,
            },
            "error": None,
        }
    }


def test_persisted_interaction_wait_response_resume_and_load(tmp_path: Path):
    kernel = runtime(tmp_path)
    created = kernel.create_persisted_run(CreateRunCommand("A product idea", "developer_tool"))
    scheduled = kernel.schedule_persisted(created.run_id).next_snapshot
    application = kernel.apply_persisted_executor_result(created.run_id, scheduled.attempts[0].attempt_id, waiting_result(scheduled))
    waiting = application.next_snapshot
    address = NodeAddress((), "idea")
    assert waiting.node_states[address].status is NodeStatus.WAITING_FOR_USER
    assert waiting.current_gate is None
    assert waiting.current_interaction["attempt_id"] == scheduled.attempts[0].attempt_id
    assert (tmp_path / "runs" / created.run_id / waiting.current_interaction["checkpoint_ref"]).is_file()

    resumed = kernel.submit_interaction_response(
        created.run_id,
        address,
        "IQ-001",
        freeform_text="Focus on final-year job seekers.",
    )
    assert resumed.node_states[address].status is NodeStatus.RUNNING
    assert resumed.attempts[0].attempt_id == scheduled.attempts[0].attempt_id
    assert resumed.attempts[0].status is AttemptStatus.RUNNING
    assert resumed.node_states[address].attempt_count == 1
    assert resumed.attempts[0].usage.automated_duration_seconds == 3.5
    assert kernel.load_run(created.run_id) == resumed


def test_gate_and_external_waits_are_kind_specific_and_defer_invalidation(tmp_path: Path):
    kernel = runtime(tmp_path)
    snapshot = kernel.create_persisted_run(CreateRunCommand("A product idea", "developer_tool"))
    gate_address = NodeAddress((), "gate_research")
    states = dict(snapshot.node_states)
    states[gate_address] = NodeState(status=NodeStatus.READY)
    kernel._persist(replace(snapshot, state_version=1, workflow_status=WorkflowStatus.RUNNING, node_states=states))
    waiting_gate = kernel.schedule_persisted(snapshot.run_id).next_snapshot
    assert waiting_gate.node_states[gate_address].status is NodeStatus.WAITING_FOR_USER

    gate = {
        "gate": {"id": "gate_research", "status": "WAITING_FOR_USER", "gate_type": "research_scope"},
        "question": "Approve research scope?",
        "options": [{"id": "approve", "label": "Approve"}],
        "recommendation": {"option": "approve"},
        "input_artifact_refs": [],
        "risks": [],
        "proposed_structured_diff_ref": None,
        "allowed_actions": ["APPROVE", "MODIFY", "CANCEL"],
    }
    opened = kernel.open_human_gate(snapshot.run_id, gate_address, gate)
    assert opened.current_gate_request_ref is not None
    approved = kernel.submit_persisted_gate_decision(snapshot.run_id, gate_address, GateDecision.APPROVE)
    assert approved.next_snapshot.node_states[gate_address].status is NodeStatus.APPROVED

    proof_address = NodeAddress((), "proof_result")
    states = dict(approved.next_snapshot.node_states)
    states[proof_address] = NodeState(status=NodeStatus.READY)
    kernel._persist(replace(approved.next_snapshot, state_version=approved.next_snapshot.state_version + 1, node_states=states))
    waiting_proof = kernel.schedule_persisted(snapshot.run_id).next_snapshot
    assert waiting_proof.node_states[proof_address].status is NodeStatus.WAITING_FOR_EXTERNAL
    proof = {
        "proof_result": {
            "proof_id": "PROOF-001",
            "submitted_at": "2026-08-19T00:01:00Z",
            "submitted_by": "external_agent",
            "outcome": "PASS",
            "artifact_refs": ["ART-PROOF-001@1"],
            "evidence_ids": ["EV-001"],
            "observed_results": ["Observed expected behavior."],
            "limitations": ["Local-only execution."],
            "executor_notes": None,
        }
    }
    submitted = kernel.submit_external_proof(snapshot.run_id, proof_address, proof)
    assert submitted.next_snapshot.node_states[proof_address].status is NodeStatus.VERIFIED
    assert submitted.deferred_effects == ("invalidate:feasibility", "return_to:feasibility")


def test_full_error_taxonomy_and_metadata_are_deterministic():
    expected = {
        "INPUT_INVALID", "ARTIFACT_MISSING", "SCHEMA_INVALID", "SOURCE_UNAVAILABLE", "INSUFFICIENT_EVIDENCE",
        "RESEARCH_LIMIT_REACHED", "DEPENDENCY_NOT_READY", "GATE_NOT_APPROVED", "VISUALIZATION_DATA_INSUFFICIENT",
        "EXECUTOR_FAILED", "PROOF_RESULT_INVALID", "PROOF_REQUIRED_FAILED", "BUDGET_EXCEEDED",
        "SECURITY_POLICY_VIOLATION", "STATE_VERSION_CONFLICT", "IDEMPOTENCY_CONFLICT",
        "PRD_INCONSISTENT_WITH_APPROVED_DISCOVERY", "INSUFFICIENT_PRODUCT_CONTEXT", "SCHEMA_VERSION_UNSUPPORTED",
    }
    assert all_error_codes() == expected
    outcome = validate_structured_error({"code": "EXECUTOR_FAILED", "recoverable": True, "details": {}})
    assert outcome.action.value == "RETRY_NODE"
    with pytest.raises(RuntimeContractError, match="contradicts"):
        validate_structured_error({"code": "EXECUTOR_FAILED", "recoverable": False, "details": {}})


def test_cumulative_usage_and_run_budget_exclude_wait_time(tmp_path: Path):
    kernel = runtime(tmp_path)
    snapshot = kernel.create_run(CreateRunCommand("A product idea", "developer_tool"))
    scheduled = kernel.schedule(snapshot).next_snapshot
    waiting = kernel.apply_executor_result(scheduled, scheduled.attempts[0].attempt_id, waiting_result(scheduled)).next_snapshot
    resumed = kernel.resume_interaction(waiting, NodeAddress((), "idea"))
    completed = waiting_result(resumed)
    payload = completed["executor_result"]
    payload.update({"status": "COMPLETED", "output_artifact_refs": ["ART-IDEA@1"]})
    payload.pop("interaction_request")
    payload.pop("interaction_checkpoint")
    payload["usage"] = {"automated_duration_seconds": 4.0, "source_count": 0, "input_tokens": 3, "output_tokens": 5, "estimated_cost": 0.01}
    done = kernel.apply_executor_result(resumed, resumed.attempts[0].attempt_id, completed).next_snapshot
    assert done.attempts[0].usage.automated_duration_seconds == 7.5

    exhausted = replace(done, attempts=(replace(done.attempts[0], usage=replace(done.attempts[0].usage, automated_duration_seconds=120 * 60)),))
    assert kernel.schedule(exhausted).next_snapshot.workflow_status is WorkflowStatus.PAUSED


def test_completion_preserves_an_unrelated_waiting_gate(tmp_path: Path):
    kernel = runtime(tmp_path)
    snapshot = kernel.create_run(CreateRunCommand("A product idea", "developer_tool"))
    scheduled = kernel.schedule(snapshot).next_snapshot
    gate_address = NodeAddress((), "gate_research")
    states = dict(scheduled.node_states)
    states[gate_address] = NodeState(status=NodeStatus.WAITING_FOR_USER)
    concurrent = replace(scheduled, node_states=states, current_gate="gate_research")
    result = waiting_result(concurrent)
    result["executor_result"].update({"status": "COMPLETED", "output_artifact_refs": []})
    result["executor_result"].pop("interaction_request")
    result["executor_result"].pop("interaction_checkpoint")

    applied = kernel.apply_executor_result(concurrent, concurrent.attempts[0].attempt_id, result).next_snapshot
    assert applied.workflow_status is WorkflowStatus.WAITING_FOR_USER
    assert applied.current_gate == "gate_research"


def test_artifact_versions_and_manifest_recovery_are_append_only(tmp_path: Path):
    kernel = runtime(tmp_path)
    created = kernel.create_persisted_run(CreateRunCommand("A product idea", "developer_tool"))
    scheduled = kernel.schedule_persisted(created.run_id).next_snapshot
    body = {
        "artifact": {
            "id": "ART-IDEA-001",
            "type": "idea_definition",
            "schema_version": "0.2.0",
            "version": 1,
            "produced_by": {"skill": "idea-intake", "attempt": scheduled.attempts[0].attempt_id},
            "created_at": "2026-08-19T00:00:00Z",
            "supersedes": None,
            "status": "active",
            "content_hash": "",
        },
        "content": {"problem": "A testable problem"},
    }
    hash_body = json.loads(json.dumps(body))
    hash_body["artifact"].pop("content_hash")
    body["artifact"]["content_hash"] = "sha256:" + hashlib.sha256(
        json.dumps(hash_body, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    stored = kernel.write_artifact(created.run_id, scheduled.attempts[0].attempt_id, "artifacts/00-intake/idea-definition.yaml", body)
    assert stored.artifact_ref == "ART-IDEA-001@1"
    with pytest.raises(RuntimeContractError, match="Append-only"):
        kernel.write_artifact(created.run_id, scheduled.attempts[0].attempt_id, "artifacts/00-intake/idea-definition.yaml", body)

    next_body = json.loads(json.dumps(body))
    next_body["artifact"].update({"version": 2, "supersedes": stored.artifact_ref, "content_hash": ""})
    next_hash_body = json.loads(json.dumps(next_body))
    next_hash_body["artifact"].pop("content_hash")
    next_body["artifact"]["content_hash"] = "sha256:" + hashlib.sha256(
        json.dumps(next_hash_body, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    stored_next = kernel.write_artifact(
        created.run_id,
        scheduled.attempts[0].attempt_id,
        "artifacts/00-intake/idea-definition.yaml",
        next_body,
    )
    assert stored_next.artifact_ref == "ART-IDEA-001@2"

    storage = RunStorage(tmp_path, created.run_id)
    current = kernel.load_run(created.run_id)
    newer = replace(current, state_version=current.state_version + 1)
    with pytest.raises(RuntimeError, match="injected crash"):
        storage.commit_snapshot(newer, updated_at="2026-08-19T00:00:10Z", fault="manifest_before_replace")
    report = kernel.recover_run(created.run_id)
    assert report.repaired_state_file is True
    assert not hasattr(report, "unreferenced_snapshots")
    assert not hasattr(report, "unreferenced_artifacts")
    assert str(newer.state_version) + ".json" in report.non_current_snapshot_files
    assert (tmp_path / "runs" / created.run_id / "runtime" / "snapshots" / f"{newer.state_version}.json").is_file()
    assert stored.artifact_ref in report.artifact_versions_not_in_current_manifest
    assert (tmp_path / "runs" / created.run_id / "artifacts" / "by-ref" / f"{stored.artifact_ref}.json").is_file()
    assert kernel.load_run(created.run_id).state_version == current.state_version
