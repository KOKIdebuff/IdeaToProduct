from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

from scripts.validate_contracts import load_document
from skillgraph_runtime.domain import CreateRunCommand, NodeStatus, WorkflowStatus
from skillgraph_runtime.errors import RuntimeContractError
from skillgraph_runtime.kernel import RuntimeKernel


ROOT = Path(__file__).resolve().parents[2]


class FixedIds:
    def new_run_id(self) -> str:
        return "run_FIXED_001"

    def new_attempt_id(self) -> str:
        return "ATT-FIXED-001"


@pytest.fixture(scope="module")
def kernel() -> RuntimeKernel:
    return RuntimeKernel(ROOT, id_factory=FixedIds())


@pytest.mark.parametrize("profile_id", ["developer_tool", "ai_agent_product", "consumer_app", "b2b_saas"])
def test_create_run_supports_all_registered_profiles(kernel: RuntimeKernel, profile_id: str):
    snapshot = kernel.create_run(CreateRunCommand(idea="Build a testable product", profile_id=profile_id))
    assert snapshot.contract_version == "0.3.0"
    assert snapshot.profile_ref == f"{profile_id}@0.3.0"
    assert snapshot.workflow_status is WorkflowStatus.CREATED
    assert snapshot.state_version == 0
    assert all(state.status is NodeStatus.PENDING for state in snapshot.node_states.values())


def test_create_run_defaults_and_explicit_v03_are_equivalent(kernel: RuntimeKernel):
    default = kernel.create_run(CreateRunCommand(idea="A", profile_id="developer_tool"))
    explicit = kernel.create_run(CreateRunCommand(idea="A", profile_id="developer_tool", contract_version="0.3.0"))
    assert default.contract_version == explicit.contract_version == "0.3.0"
    assert default.to_wire_state()["nodes"] == explicit.to_wire_state()["nodes"]


@pytest.mark.parametrize("version", ["0.1.0", "0.2.0", "9.9.9"])
def test_create_run_fails_closed_for_unsupported_versions(kernel: RuntimeKernel, version: str):
    with pytest.raises(RuntimeContractError) as caught:
        kernel.create_run(CreateRunCommand(idea="A", profile_id="developer_tool", contract_version=version))
    assert caught.value.code == "SCHEMA_VERSION_UNSUPPORTED"


def test_create_run_rejects_non_string_contract_version(kernel: RuntimeKernel):
    with pytest.raises(RuntimeContractError) as caught:
        kernel.create_run(CreateRunCommand(idea="A", profile_id="developer_tool", contract_version=["0.2.0"]))
    assert caught.value.rule == "contract_version"


@pytest.mark.parametrize("idea,profile", [("", "developer_tool"), ("A", "missing"), ("A", "../developer_tool")])
def test_create_run_rejects_invalid_input(kernel: RuntimeKernel, idea: str, profile: str):
    with pytest.raises(RuntimeContractError):
        kernel.create_run(CreateRunCommand(idea=idea, profile_id=profile))


def test_initial_state_is_v03_schema_valid_and_has_no_runtime_side_effects(kernel: RuntimeKernel):
    snapshot = kernel.create_run(CreateRunCommand(idea="A", profile_id="developer_tool"))
    wire = snapshot.to_wire_state()
    assert wire["schema_version"] == "0.3.0"
    assert wire["current_gate"] is None
    assert wire["current_interaction"] is None
    assert wire["research_contract_ref"] is None
    assert wire["global_research_cycle"] == 0
    assert not (ROOT / "contracts" / "0.3.0" / "runtime").exists()


def test_legacy_input_is_default_deny_and_accepted_reference_stays_read_only(kernel: RuntimeKernel):
    accepted = load_document(ROOT / "contracts" / "0.3.0" / "fixtures" / "legacy" / "accepted-evidence.yaml")
    snapshot = kernel.create_run(
        CreateRunCommand(idea="A", profile_id="developer_tool", legacy_input_refs=(accepted,))
    )
    assert snapshot.legacy_inputs[0].accepted is True
    assert snapshot.legacy_inputs[0].rule_id == "evidence_seed_v1_to_v03"
    assert all(not state.artifact_refs for state in snapshot.node_states.values())

    rejected = dict(accepted)
    rejected["ref_type"] = "prd"
    with pytest.raises(RuntimeContractError) as caught:
        kernel.create_run(CreateRunCommand(idea="A", profile_id="developer_tool", legacy_input_refs=(rejected,)))
    assert caught.value.rule == "legacy_input_ref"


def test_existing_v02_snapshot_loads_and_resumes_only_with_the_v02_bundle(tmp_path: Path):
    legacy_kernel = RuntimeKernel(ROOT, storage_root=tmp_path, id_factory=FixedIds())
    v03_snapshot = legacy_kernel.create_run(CreateRunCommand(idea="A", profile_id="developer_tool"), run_id="run_v02_resume")
    v02_snapshot = replace(
        v03_snapshot,
        contract_version="0.2.0",
        workflow_version="0.2.0",
        profile_ref="developer_tool@0.2.0",
    )
    legacy_kernel._persist(v02_snapshot)  # Test-only fixture for an already persisted frozen Run.

    resumed = RuntimeKernel(ROOT, storage_root=tmp_path, id_factory=FixedIds()).load_run("run_v02_resume")
    compiled = legacy_kernel.compiled_bundle_for(resumed)
    assert resumed.contract_version == "0.2.0"
    assert compiled.context.bundle.contract_version == "0.2.0"
    assert compiled.context.bundle.operation == "resume"
    assert (compiled.context.template_dir / "competitor-report.md").is_file()
    assert not (compiled.context.template_dir / "competitor-report.html").exists()
