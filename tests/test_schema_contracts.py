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


BUSINESS_FIXTURES = [
    ("idea-definition.yaml", "idea.schema.json"),
    ("competitor-dataset.yaml", "competitor.schema.json"),
    ("research-contract.yaml", "research.schema.json"),
    ("chart-bundle.yaml", "chart.schema.json"),
]


@pytest.mark.parametrize(("fixture_name", "schema_name"), BUSINESS_FIXTURES)
def test_business_artifact_fixture_is_schema_valid(contract_env, fixture_name, schema_name):
    schemas, registry, _ = contract_env
    document = load_document(ROOT / "fixtures" / "contracts" / "valid" / fixture_name)
    assert validate_instance(document, schema_name, fixture_name, schemas, registry) == []


@pytest.mark.parametrize(
    ("fixture_name", "schema_name"),
    [
        ("idea-definition-missing-problem.yaml", "idea.schema.json"),
        ("competitor-temporal-metric.yaml", "competitor.schema.json"),
        ("research-contract-missing-source-types.yaml", "research.schema.json"),
        ("chart-bundle-missing-data.yaml", "chart.schema.json"),
    ],
)
def test_business_artifact_negative_fixture_is_rejected(contract_env, fixture_name, schema_name):
    schemas, registry, _ = contract_env
    document = load_document(ROOT / "fixtures" / "contracts" / "invalid" / fixture_name)
    assert "required" in rules(validate_instance(document, schema_name, fixture_name, schemas, registry))


def test_business_contract_specific_invariants(contract_env):
    schemas, registry, _ = contract_env

    idea = load_document(ROOT / "fixtures" / "contracts" / "valid" / "idea-definition.yaml")
    idea["assumptions"][0]["status"] = "validated"
    assert "const" in rules(validate_instance(idea, "idea.schema.json", "idea.yaml", schemas, registry))

    research = load_document(ROOT / "fixtures" / "contracts" / "valid" / "research-contract.yaml")
    research["effective_research"]["users"] = "enabled"
    assert "enum" in rules(validate_instance(research, "research.schema.json", "research.yaml", schemas, registry))

    chart = load_document(ROOT / "fixtures" / "contracts" / "valid" / "chart-bundle.yaml")
    del chart["png_ref"]
    assert "required" in rules(validate_instance(chart, "chart.schema.json", "chart.yaml", schemas, registry))


def test_business_schema_named_definitions_are_stable(contract_env):
    schemas, _, _ = contract_env
    assert set(schemas["idea.schema.json"]["$defs"]) >= {"idea_definition"}
    assert set(schemas["competitor.schema.json"]["$defs"]) >= {
        "competitor_candidates",
        "competitor_ranking",
        "competitor_deep_dive",
        "competitor_dataset",
        "competitor_analysis",
        "scoring_methodology",
    }
    assert set(schemas["research.schema.json"]["$defs"]) >= {
        "research_contract",
        "user_evidence",
        "market_landscape",
        "technology_landscape",
        "research_gap",
        "opportunity_map",
        "opportunity_methodology",
        "proof_plan",
        "mvp_scope",
    }
    assert set(schemas["chart.schema.json"]["$defs"]) >= {"chart_bundle"}
    assert set(schemas["verification.schema.json"]["$defs"]) >= {
        "research_verification",
        "competitor_verification",
        "prd_consistency_verification",
    }
    assert set(schemas["readiness-result.schema.json"]["$defs"]) >= {"readiness_result"}


def test_skill_requires_machine_readable_output_contracts(contract_env):
    schemas, registry, _ = contract_env
    skill = load_document(ROOT / "fixtures" / "contracts" / "valid" / "skill.yaml")
    assert validate_instance(skill, "skill.schema.json", "skill.yaml", schemas, registry) == []

    missing = deepcopy(skill)
    del missing["output_contracts"]
    assert "required" in rules(validate_instance(missing, "skill.schema.json", "skill.yaml", schemas, registry))

    malformed = deepcopy(skill)
    malformed["output_contracts"][0]["schema_ref"] = "../schemas/competitor.schema.json"
    assert "pattern" in rules(validate_instance(malformed, "skill.schema.json", "skill.yaml", schemas, registry))


def test_subgraph_schema_reuses_workflow_node_contract(contract_env):
    schemas, registry, _ = contract_env
    subgraph = {
        "subgraph": {"id": "competitor-research", "version": "0.1.0", "schema_version": "0.1.0"},
        "inputs": ["idea_definition", "research_contract", "product_profile", "source_index"],
        "output_contracts": [{"artifact_type": "competitor_candidates", "producer": "discovery"}],
        "nodes": {"discovery": {"kind": "skill", "skill": "competitor-discovery", "required": True}},
    }
    assert validate_instance(subgraph, "subgraph.schema.json", "subgraph.yaml", schemas, registry) == []

    duplicate_output = deepcopy(subgraph)
    duplicate_output["output_contracts"].append(deepcopy(duplicate_output["output_contracts"][0]))
    assert "uniqueItems" in rules(validate_instance(duplicate_output, "subgraph.schema.json", "subgraph.yaml", schemas, registry))

    invalid_node = deepcopy(subgraph)
    invalid_node["nodes"]["discovery"]["unexpected"] = True
    assert "additionalProperties" in rules(validate_instance(invalid_node, "subgraph.schema.json", "subgraph.yaml", schemas, registry))


def test_legacy_verification_and_readiness_top_level_instances_remain_valid(contract_env):
    schemas, registry, _ = contract_env
    verification = load_document(ROOT / "fixtures" / "contracts" / "valid" / "verification.yaml")
    readiness = load_document(ROOT / "fixtures" / "contracts" / "valid" / "readiness.yaml")
    assert validate_instance(verification, "verification.schema.json", "verification.yaml", schemas, registry) == []
    assert validate_instance(readiness, "readiness-result.schema.json", "readiness.yaml", schemas, registry) == []


def test_competitor_non_pass_verification_requires_retry_contract(contract_env):
    schemas, registry, _ = contract_env
    verification = {
        "artifact": {
            "id": "ART-VERIFY-001",
            "type": "competitor_verification",
            "schema_version": "0.1.0",
            "version": 1,
            "produced_by": {"skill": "competitor-verifier", "attempt": "ATT-VERIFY-001"},
            "created_at": "2026-08-08T06:30:00Z",
            "supersedes": None,
            "status": "active",
        },
        "verification": {
            "overall": "FAIL",
            "issues": [
                {
                    "code": "INSUFFICIENT_COMPETITOR_EVIDENCE",
                    "critical": False,
                    "retry_targets": ["deep_dive"],
                    "return_to": "competitor_verifier",
                }
            ],
        },
    }
    assert validate_instance(verification, "verification.schema.json", "verification.yaml", schemas, registry) == []

    missing_retry = deepcopy(verification)
    del missing_retry["verification"]["issues"][0]["retry_targets"]
    assert "oneOf" in rules(validate_instance(missing_retry, "verification.schema.json", "verification.yaml", schemas, registry))
