from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
from pathlib import Path

import pytest

from skillgraph_runtime import CreateRunCommand, NodeAddress, RuntimeContractError, RuntimeKernel
from skillgraph_runtime.domain import AdapterType, AttemptStatus, NodeStatus


ROOT = Path(__file__).resolve().parents[2]


class FixedIds:
    def new_run_id(self) -> str:
        return "run_executor"

    def new_attempt_id(self) -> str:
        return "ATT-EXEC-001"


class FixedClock:
    def now(self) -> str:
        return "2026-08-14T02:00:00Z"


@pytest.fixture(scope="module")
def prepared():
    kernel = RuntimeKernel(
        ROOT,
        host_token_limit=300,
        host_cost_limit=1.0,
        id_factory=FixedIds(),
        clock=FixedClock(),
    )
    snapshot = kernel.create_run(CreateRunCommand("executor validation", "developer_tool"))
    snapshot = kernel.schedule(snapshot).next_snapshot
    return kernel, snapshot


def request_for(snapshot, *, adapter: str = "host_agent"):
    attempt = snapshot.attempts[0]
    return {
        "executor_request": {
            "schema_version": snapshot.contract_version,
            "run_id": snapshot.run_id,
            "node_id": attempt.address.node_id,
            "attempt_id": attempt.attempt_id,
            "adapter_type": adapter,
            "skill_ref": attempt.skill_ref,
            "input_artifact_refs": list(attempt.input_artifact_refs),
            "profile_ref": attempt.profile_ref,
            "research_contract_ref": attempt.research_contract_ref,
            "permissions": {
                "external_access": attempt.permissions.external_access,
                "workspace_write_paths": list(attempt.permissions.workspace_write_paths),
                "secrets": attempt.permissions.secrets,
            },
            "budget": {
                "timeout_minutes": attempt.budget.timeout_minutes,
                "max_sources": attempt.budget.max_sources,
                "token_limit": attempt.budget.token_limit,
                "cost_limit": attempt.budget.cost_limit,
            },
        }
    }


def result_for(snapshot, *, status: str = "COMPLETED"):
    attempt = snapshot.attempts[0]
    return {
        "executor_result": {
            "schema_version": snapshot.contract_version,
            "run_id": snapshot.run_id,
            "node_id": attempt.address.node_id,
            "attempt_id": attempt.attempt_id,
            "status": status,
            "output_artifact_refs": ["ART-IDEA@1"] if status == "COMPLETED" else [],
            "source_upserts": [],
            "usage": {
                "automated_duration_seconds": 12.5,
                "source_count": 0,
                "input_tokens": 100,
                "output_tokens": 120,
                "estimated_cost": 0.2,
            },
            "error": None,
        }
    }


def waiting_result(snapshot):
    result = result_for(snapshot, status="WAITING_FOR_USER")
    payload = result["executor_result"]
    payload["interaction_request"] = {
        "method": "clarification",
        "question_id": "IQ-001",
        "round": 1,
        "dimension": "user",
        "prompt": "Which primary user should be prioritized?",
        "options": [],
        "recommendation": None,
        "allow_freeform_answer": True,
    }
    payload["interaction_checkpoint"] = {
        "checkpoint_id": "CP-001",
        "checkpoint_version": 1,
        "round": 1,
        "current_method": "clarification",
        "target_unknown_id": "UNK-USER-001",
        "target_dimension": "user",
        "selection_rationale": "The target user is still unknown.",
        "completion_status": "IN_PROGRESS",
    }
    return result


def assert_rejected(kernel, snapshot, document, method: str, *, rule: str | None = None):
    with pytest.raises(RuntimeContractError) as caught:
        getattr(kernel, method)(snapshot, snapshot.attempts[0].attempt_id, document)
    if rule is not None:
        assert caught.value.rule == rule
    return caught.value


def test_valid_request_and_all_result_status_shapes_return_immutable_proposals(prepared):
    kernel, snapshot = prepared
    request = kernel.validate_executor_request(snapshot, "ATT-EXEC-001", request_for(snapshot))
    assert request.proposal_type == "request"
    with pytest.raises(TypeError):
        request.payload["executor_request"]["run_id"] = "changed"

    success = kernel.validate_executor_result(snapshot, "ATT-EXEC-001", result_for(snapshot))
    waiting = kernel.validate_executor_result(snapshot, "ATT-EXEC-001", waiting_result(snapshot))
    failed = result_for(snapshot, status="FAILED")
    failed["executor_result"]["error"] = {
        "code": "EXECUTOR_FAILED",
        "message": "intentional",
        "recoverable": True,
        "retry_target": "idea",
        "consumes_node_attempt": True,
        "consumes_global_research_cycle": False,
        "next_action": "RETRY_NODE",
        "details": {},
    }
    failure = kernel.validate_executor_result(snapshot, "ATT-EXEC-001", failed)
    assert {success.proposal_type, waiting.proposal_type, failure.proposal_type} == {"result"}


@pytest.mark.parametrize("field", ["schema_version", "run_id", "node_id", "attempt_id", "skill_ref", "profile_ref"])
def test_request_identity_and_version_must_match_exactly(prepared, field):
    kernel, snapshot = prepared
    request = request_for(snapshot)
    request["executor_request"][field] = "wrong"
    assert_rejected(kernel, snapshot, request, "validate_executor_request")


def test_request_rejects_path_escape_permission_escalation_adapter_and_budget(prepared):
    kernel, snapshot = prepared

    escaped = request_for(snapshot)
    escaped["executor_request"]["permissions"]["workspace_write_paths"] = ["../outside"]
    assert_rejected(kernel, snapshot, escaped, "validate_executor_request")

    outside = request_for(snapshot)
    outside["executor_request"]["permissions"]["workspace_write_paths"] = ["artifacts/99-other/"]
    assert_rejected(kernel, snapshot, outside, "validate_executor_request", rule="permission_workspace_path")

    escalated = request_for(snapshot)
    escalated["executor_request"]["permissions"]["external_access"] = "read_only"
    assert_rejected(kernel, snapshot, escalated, "validate_executor_request", rule="permission_external_access")

    adapter_source = replace(
        snapshot,
        attempts=(replace(snapshot.attempts[0], allowed_adapter_types=(AdapterType.HOST_AGENT,)),),
    )
    illegal_adapter = request_for(adapter_source, adapter="fixture")
    assert_rejected(kernel, adapter_source, illegal_adapter, "validate_executor_request", rule="executor_adapter")

    exceeded = request_for(snapshot)
    exceeded["executor_request"]["budget"]["timeout_minutes"] += 1
    error = assert_rejected(kernel, snapshot, exceeded, "validate_executor_request", rule="executor_request_budget")
    assert error.code == "BUDGET_EXCEEDED"

    narrowed = request_for(snapshot)
    narrowed["executor_request"]["budget"]["timeout_minutes"] -= 1
    assert_rejected(kernel, snapshot, narrowed, "validate_executor_request", rule="executor_request_budget")


def test_result_rejects_usage_overrun_method_mismatch_and_conditional_fields(prepared):
    kernel, snapshot = prepared
    excessive = result_for(snapshot)
    excessive["executor_result"]["usage"]["input_tokens"] = 250
    excessive["executor_result"]["usage"]["output_tokens"] = 100
    assert_rejected(kernel, snapshot, excessive, "validate_executor_result", rule="executor_result_usage")

    mismatch = waiting_result(snapshot)
    mismatch["executor_result"]["interaction_checkpoint"]["current_method"] = "assumption_challenge"
    assert_rejected(kernel, snapshot, mismatch, "validate_executor_result", rule="interaction_method_mismatch")

    conditional = result_for(snapshot)
    conditional["executor_result"]["interaction_request"] = waiting_result(snapshot)["executor_result"]["interaction_request"]
    assert_rejected(kernel, snapshot, conditional, "validate_executor_result", rule="executor_result_schema")


def test_interaction_resume_must_reuse_same_waiting_attempt_and_checkpoint(prepared):
    kernel, snapshot = prepared
    attempt = replace(snapshot.attempts[0], status=AttemptStatus.WAITING_FOR_USER)
    states = dict(snapshot.node_states)
    checkpoint = "runtime/attempts/ATT-EXEC-001/checkpoints/CP-001.json"
    states[NodeAddress((), "idea")] = replace(
        states[NodeAddress((), "idea")],
        status=NodeStatus.WAITING_FOR_USER,
        interaction_checkpoint_ref=checkpoint,
    )
    waiting = replace(snapshot, node_states=states, attempts=(attempt,))
    request = request_for(waiting)
    request["executor_request"]["interaction_resume"] = {
        "checkpoint_ref": checkpoint,
        "question_id": "IQ-001",
        "freeform_text": "Focus on final-year students.",
    }
    assert kernel.validate_executor_request(waiting, attempt.attempt_id, request).proposal_type == "request"

    mismatched = deepcopy(request)
    mismatched["executor_request"]["interaction_resume"]["checkpoint_ref"] = (
        "runtime/attempts/ATT-EXEC-001/checkpoints/CP-OTHER.json"
    )
    assert_rejected(kernel, waiting, mismatched, "validate_executor_request", rule="interaction_resume")


def test_executor_cannot_submit_runtime_owned_authority(prepared):
    kernel, snapshot = prepared
    request = request_for(snapshot)
    request["executor_request"]["state_version"] = 99
    error = assert_rejected(kernel, snapshot, request, "validate_executor_request", rule="executor_authority")
    assert error.code == "SECURITY_POLICY_VIOLATION"


def test_executor_rejects_inactive_node_identity_and_platform_path_aliases(prepared):
    kernel, snapshot = prepared
    states = dict(snapshot.node_states)
    states[NodeAddress((), "idea")] = replace(
        states[NodeAddress((), "idea")],
        active_attempt_id=None,
    )
    inactive = replace(snapshot, node_states=states)
    assert_rejected(kernel, inactive, request_for(inactive), "validate_executor_request", rule="executor_attempt_status")

    for unsafe in ("artifacts\\00-intake\\idea-definition.yaml", "artifacts/00-intake/NUL.txt"):
        request = request_for(snapshot)
        request["executor_request"]["permissions"]["workspace_write_paths"] = [unsafe]
        assert_rejected(kernel, snapshot, request, "validate_executor_request")
