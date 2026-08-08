from __future__ import annotations

from copy import deepcopy

import pytest

from scripts.validate_contracts import ROOT, load_document, path_semantics, reference_diagnostics, reference_integrity, resolve_repo_path, validate_instance


def rules(diagnostics):
    return {item.rule for item in diagnostics}


@pytest.mark.parametrize("unsafe", ["../outside.json", "/outside.json", "C:\\outside\\file.json", "\\\\server\\share\\file.json"])
def test_executor_write_path_cannot_escape_workspace(contract_env, unsafe):
    schemas, registry, _ = contract_env
    request = load_document(ROOT / "fixtures" / "contracts" / "valid" / "executor-request.yaml")
    mutated = deepcopy(request)
    mutated["executor_request"]["permissions"]["workspace_write_paths"] = [unsafe]
    schema_errors = validate_instance(mutated, "executor-request.schema.json", "request.yaml", schemas, registry)
    semantic_errors = path_semantics(mutated, "request.yaml")
    assert schema_errors or semantic_errors
    assert "pattern" in rules(schema_errors) or "unsafe_path" in rules(semantic_errors)


def test_failed_executor_requires_structured_error(contract_env):
    schemas, registry, _ = contract_env
    result = load_document(ROOT / "fixtures" / "contracts" / "valid" / "executor-result-failure.yaml")
    mutated = deepcopy(result)
    mutated["executor_result"]["error"] = None
    assert validate_instance(mutated, "executor-result.schema.json", "result.yaml", schemas, registry)


def test_completed_executor_rejects_error(contract_env):
    schemas, registry, _ = contract_env
    result = load_document(ROOT / "fixtures" / "contracts" / "valid" / "executor-result-success.yaml")
    mutated = deepcopy(result)
    mutated["executor_result"]["error"] = {
        "code": "EXECUTOR_FAILED",
        "recoverable": False,
        "details": {},
    }
    assert validate_instance(mutated, "executor-result.schema.json", "result.yaml", schemas, registry)


def test_state_rejects_negative_version_and_enum_mixing(contract_env):
    schemas, registry, _ = contract_env
    state = load_document(ROOT / "fixtures" / "contracts" / "valid" / "workflow-state.yaml")
    negative = deepcopy(state)
    negative["state_version"] = -1
    assert validate_instance(negative, "workflow-state.schema.json", "state.yaml", schemas, registry)

    mixed = deepcopy(state)
    mixed["readiness_status"] = "PARTIAL"
    assert validate_instance(mixed, "workflow-state.schema.json", "state.yaml", schemas, registry)


def test_unknown_core_property_is_rejected(contract_env):
    schemas, registry, _ = contract_env
    source = load_document(ROOT / "fixtures" / "contracts" / "valid" / "source.yaml")
    mutated = deepcopy(source)
    mutated["source"]["unexpected"] = True
    diagnostics = validate_instance(mutated, "source.schema.json", "source.yaml", schemas, registry)
    assert "additionalProperties" in rules(diagnostics)


def test_gate_action_domains_do_not_mix(contract_env):
    schemas, registry, _ = contract_env
    gate = load_document(ROOT / "fixtures" / "contracts" / "valid" / "gate.yaml")
    mutated = deepcopy(gate)
    mutated["gate"]["gate_type"] = "mvp_scope"
    mutated["allowed_actions"] = ["APPROVE", "MODIFY", "CANCEL", "PARTIAL_ACCEPTED"]
    diagnostics = validate_instance(mutated, "gate.schema.json", "gate.yaml", schemas, registry)
    assert "enum" in rules(diagnostics)


def test_source_and_evidence_reference_integrity(contract_env):
    evidence = load_document(ROOT / "fixtures" / "contracts" / "valid" / "evidence.yaml")
    mutated = deepcopy(evidence)
    mutated["evidence"]["source_id"] = "SRC-NOT-INDEXED"
    diagnostics = reference_integrity(mutated, "evidence.yaml", {"SRC-001"}, {"CL-001"}, {"EV-001"}, {"DEC-001"})
    assert "unresolved_source" in rules(diagnostics)


def test_schema_reference_cannot_use_parent_traversal(contract_env):
    schemas, _, _ = contract_env
    mutated = deepcopy(schemas)
    mutated["artifact.schema.json"]["properties"]["artifact"] = {"$ref": "../common.schema.json#/$defs/machine_id"}
    assert "unsafe_ref" in rules(reference_diagnostics(mutated))


@pytest.mark.parametrize("unsafe", ["../outside.yaml", "C:\\outside\\file.yaml", "\\\\server\\share\\file.yaml"])
def test_fixture_path_must_remain_in_repository(unsafe):
    with pytest.raises(ValueError):
        resolve_repo_path(unsafe)
