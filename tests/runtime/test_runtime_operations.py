from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

from skillgraph_runtime import CreateRunCommand, NodeAddress, RuntimeKernel, RuntimeOperations
from skillgraph_runtime.adapters import AdapterRegistry, FixtureAdapter, HostAgentAdapter, ManualAdapter
from skillgraph_runtime.cli import main
from skillgraph_runtime.domain import NodeState, NodeStatus, WorkflowStatus
from skillgraph_runtime.errors import RuntimeContractError
from skillgraph_runtime.invalidation import invalidate_downstream, resume_invalidated
from skillgraph_runtime.storage import RunStorage


ROOT = Path(__file__).resolve().parents[2]


class FixedIds:
    def __init__(self) -> None:
        self.attempt = 0

    def new_run_id(self) -> str:
        return "run_operations"

    def new_attempt_id(self) -> str:
        self.attempt += 1
        return f"ATT-OPERATIONS-{self.attempt}"


class FixedClock:
    def __init__(self) -> None:
        self.value = 0

    def now(self) -> str:
        self.value += 1
        return f"2026-08-19T00:00:{self.value:02d}Z"


def service(tmp_path: Path) -> RuntimeOperations:
    return RuntimeOperations(RuntimeKernel(ROOT, storage_root=tmp_path, id_factory=FixedIds(), clock=FixedClock()))


def create_envelope() -> dict:
    return {
        "api_version": "0.2.0",
        "run_id": None,
        "idempotency_key": "create-001",
        "payload": {"idea": "A testable idea", "profile_id": "developer_tool", "contract_version": "0.3.0"},
    }


def test_create_replay_and_mutation_version_guards_are_durable(tmp_path: Path):
    operations = service(tmp_path)
    first = operations.dispatch("create_run", create_envelope())
    replay = operations.dispatch("create_run", create_envelope())
    assert first == replay and first["ok"]
    run_id = first["data"]["run_id"]
    assert run_id.startswith("run_")
    assert service(tmp_path).dispatch("create_run", create_envelope()) == first
    conflicting_create = create_envelope()
    conflicting_create["payload"] = {**conflicting_create["payload"], "idea": "A different idea"}
    assert operations.dispatch("create_run", conflicting_create)["error"]["code"] == "IDEMPOTENCY_CONFLICT"

    pause = {
        "api_version": "0.2.0",
        "run_id": run_id,
        "idempotency_key": "pause-001",
        "expected_state_version": 0,
        "payload": {},
    }
    paused = operations.dispatch("pause_run", pause)
    assert paused["ok"] and paused["state_version"] == 1
    assert operations.dispatch("pause_run", pause) == paused
    events = RunStorage(tmp_path, run_id).event_records()
    assert [record["event"] for record in events] == ["RUN_CREATED", "RUN_PAUSED", "OPERATION_COMPLETED"]

    paused_run = operations.dispatch(
        "run_ready_nodes",
        {
            "api_version": "0.2.0",
            "run_id": run_id,
            "idempotency_key": "run-while-paused",
            "expected_state_version": 1,
            "payload": {},
        },
    )
    assert paused_run["error"]["code"] == "STATE_VERSION_CONFLICT"
    assert paused_run["error"]["rule"] == "workflow_paused"

    stale = dict(pause, idempotency_key="pause-002")
    conflict = operations.dispatch("pause_run", stale)
    assert conflict["error"]["code"] == "STATE_VERSION_CONFLICT"
    assert conflict["error"]["details"]["actual_state_version"] == 1


def test_operations_reject_later_stage_calls_without_writing(tmp_path: Path):
    operations = service(tmp_path)
    created = operations.dispatch("create_run", create_envelope())
    run_id = created["data"]["run_id"]
    rejected = operations.dispatch("export_prd", {"api_version": "0.2.0", "run_id": run_id, "payload": {}})
    assert rejected["error"]["code"] == "INPUT_INVALID"
    assert rejected["error"]["rule"] == "operation_not_implemented"
    assert RunStorage(tmp_path, run_id).event_records()[0]["event"] == "RUN_CREATED"


def test_event_log_recovery_keeps_a_complete_prefix_and_rejects_unbounded_fields(tmp_path: Path):
    created = service(tmp_path).dispatch("create_run", create_envelope())
    storage = RunStorage(tmp_path, created["data"]["run_id"])
    storage.append_event({"event": "TEST_TAIL", "ts": "2026-08-19T00:09:00Z", "state_version": 0})
    assert storage.recover().uncommitted_event_offsets == (2,)
    try:
        storage.append_event({"event": "BAD", "ts": "2026-08-19T00:09:01Z", "payload": "secret"})
    except RuntimeContractError as exc:
        assert exc.code == "SECURITY_POLICY_VIOLATION"
    else:
        raise AssertionError("an unbounded Event field must be rejected")
    event_path = storage.run_root / "runtime" / "event-log.jsonl"
    with event_path.open("a", encoding="utf-8") as stream:
        stream.write('{"offset":3')
    report = storage.recover()
    assert report.uncommitted_event_offsets == (2,)
    assert event_path.exists()


def test_invalidation_is_precise_and_preserves_the_last_verified_predecessor(tmp_path: Path):
    kernel = RuntimeKernel(ROOT, storage_root=tmp_path, id_factory=FixedIds(), clock=FixedClock())
    snapshot = kernel.create_run(CreateRunCommand("A testable idea", "developer_tool"))
    idea, contract = NodeAddress((), "idea"), NodeAddress((), "contract")
    states = dict(snapshot.node_states)
    states[idea] = NodeState(status=NodeStatus.VERIFIED, artifact_refs=("ART-IDEA@1",))
    states[contract] = NodeState(status=NodeStatus.VERIFIED, artifact_refs=("ART-CONTRACT@1",))
    prepared = replace(snapshot, state_version=1, workflow_status=WorkflowStatus.RUNNING, node_states=states)
    result = invalidate_downstream(prepared, kernel.compiled_bundle_for(prepared), idea)
    assert idea not in result.invalidated
    assert contract in result.invalidated
    assert result.next_snapshot.node_states[contract].status is NodeStatus.INVALIDATED
    resumed = resume_invalidated(result.next_snapshot)
    assert resumed.node_states[idea].status is NodeStatus.VERIFIED
    assert resumed.node_states[contract].status is NodeStatus.PENDING


def test_adapters_are_explicit_and_never_receive_runtime_write_authority():
    request = type("Request", (), {"payload": {"executor_request": {"attempt_id": "ATT-1", "skill_ref": "idea-intake@0.3.0", "input_artifact_refs": [], "permissions": {"secrets": "forbidden"}, "budget": {}}}})()
    fixture = FixtureAdapter({"idea-intake@0.3.0": {"executor_result": {"status": "COMPLETED"}}})
    assert fixture.execute(request)["executor_result"]["status"] == "COMPLETED"
    assert ManualAdapter().execute(request)["manual_instruction"].attempt_id == "ATT-1"
    host = HostAgentAdapter(lambda _: {"executor_result": {"status": "COMPLETED"}})
    assert host.execute(request)["executor_result"]["status"] == "COMPLETED"
    assert AdapterRegistry((fixture, ManualAdapter(), host)).get("manual").adapter_type == "manual"


def test_adapter_execution_revalidates_fixture_results_and_manual_waits(tmp_path: Path):
    kernel = RuntimeKernel(ROOT, storage_root=tmp_path, id_factory=FixedIds(), clock=FixedClock())
    preliminary = RuntimeOperations(kernel)
    created = preliminary.dispatch("create_run", create_envelope())
    run_id = created["data"]["run_id"]
    scheduled = preliminary.dispatch(
        "run_ready_nodes",
        {"api_version": "0.2.0", "run_id": run_id, "expected_state_version": 0, "idempotency_key": "schedule-001", "payload": {}},
    )
    attempt_id = scheduled["data"]["attempt_ids"][0]
    snapshot = kernel.load_run(run_id)
    result = {
        "executor_result": {
                "schema_version": "0.3.0", "run_id": run_id, "node_id": "idea", "attempt_id": attempt_id,
            "status": "COMPLETED", "output_artifact_refs": [], "source_upserts": [],
            "usage": {"automated_duration_seconds": 0, "source_count": 0, "input_tokens": 0, "output_tokens": 0, "estimated_cost": 0},
            "error": None,
        }
    }
    fixture_ops = RuntimeOperations(kernel, adapters=AdapterRegistry((FixtureAdapter({"idea-intake@0.3.0": result}),)))
    completed = fixture_ops.execute_adapter_attempt(run_id, attempt_id, "fixture")
    assert completed["state"]["nodes"]["idea"]["status"] == "COMPLETED"
    assert any(
        record.get("event") == "ADAPTER_EXECUTED" and record.get("adapter_type") == "fixture"
        for record in RunStorage(tmp_path, run_id).event_records()
    )

    second_kernel = RuntimeKernel(ROOT, storage_root=tmp_path / "manual", id_factory=FixedIds(), clock=FixedClock())
    manual_ops = RuntimeOperations(second_kernel, adapters=AdapterRegistry((ManualAdapter(),)))
    manual_created = manual_ops.dispatch("create_run", create_envelope())
    manual_run = manual_created["data"]["run_id"]
    manual_plan = manual_ops.dispatch(
        "run_ready_nodes",
        {"api_version": "0.2.0", "run_id": manual_run, "expected_state_version": 0, "idempotency_key": "manual-schedule", "payload": {}},
    )
    instruction = manual_ops.execute_adapter_attempt(manual_run, manual_plan["data"]["attempt_ids"][0], "manual")
    assert instruction["state"]["workflow_status"] == "WAITING_FOR_EXTERNAL"


def test_gate_decision_is_schema_valid_and_event_linked(tmp_path: Path):
    operations = service(tmp_path)
    created = operations.dispatch("create_run", create_envelope())
    run_id = created["data"]["run_id"]
    kernel = operations.kernel
    snapshot = kernel.load_run(run_id)
    address = NodeAddress((), "gate_research")
    states = dict(snapshot.node_states)
    states[address] = NodeState(status=NodeStatus.READY)
    kernel._persist(replace(snapshot, state_version=1, workflow_status=WorkflowStatus.RUNNING, node_states=states))
    kernel.schedule_persisted(run_id)
    gate = {
        "gate": {"id": "gate_research", "status": "WAITING_FOR_USER", "gate_type": "research_scope"},
        "question": "Approve research scope?",
        "options": [{"id": "approve", "label": "Approve"}],
        "recommendation": {"option": "approve"},
        "input_artifact_refs": [],
        "risks": [],
        "proposed_structured_diff_ref": None,
        "allowed_actions": ["APPROVE"],
    }
    opened = kernel.open_human_gate(run_id, address, gate)
    document = {
        "decision": {
            "id": "DEC-GATE-001",
            "date": "2026-08-19T00:03:00Z",
            "gate_id": "gate_research",
            "question": "Approve research scope?",
            "decision": "APPROVE",
            "rationale": ["Scope is appropriate."],
            "evidence_ids": [],
            "artifact_refs": [],
            "alternatives": ["Cancel"],
            "accepted_risks": [],
            "structured_diff_ref": None,
            "reversible": True,
            "approved_by": {"type": "user", "id": "user-1"},
        }
    }
    response = operations.dispatch(
        "submit_gate_decision",
        {"api_version": "0.2.0", "run_id": run_id, "expected_state_version": opened.state_version, "idempotency_key": "gate-001", "payload": {"gate_id": "gate_research", "decision": "APPROVE", "decision_document": document}},
    )
    assert response["ok"]
    records = RunStorage(tmp_path, run_id).decision_records()
    assert records[0]["decision"]["id"] == "DEC-GATE-001"
    events = RunStorage(tmp_path, run_id).event_records()
    assert events[records[0]["event_offset"] - 1]["event"] == "GATE_DECISION_RECORDED"
    assert events[-1]["event"] == "OPERATION_COMPLETED"


def test_cli_emits_one_json_envelope(tmp_path: Path, capsys):
    exit_code = main([
        "--repository-root", str(ROOT), "--storage-root", str(tmp_path), "init",
        "--idea", "CLI idea", "--profile", "developer_tool", "--idempotency-key", "cli-create-001",
    ])
    captured = capsys.readouterr()
    assert exit_code == 0
    created = json.loads(captured.out)
    assert created["ok"] is True
    assert created["data"]["contract_version"] == "0.3.0"

    invalid_exit = main(["--storage-root", str(tmp_path), "init"])
    invalid = capsys.readouterr()
    assert invalid_exit == 2
    assert len(invalid.out.splitlines()) == 1
    assert json.loads(invalid.out)["ok"] is False
    assert invalid.err.strip() == "cli_input"
