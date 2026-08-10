from __future__ import annotations

from copy import deepcopy

import pytest

from scripts.validate_contracts import build_repository_catalog, validate_instance, workflow_semantics


def rules(diagnostics):
    return {item.rule for item in diagnostics}


def test_dependency_cycle_is_rejected(contract_env):
    _, _, workflow = contract_env
    mutated = deepcopy(workflow)
    mutated["nodes"]["idea"]["depends_on"] = ["prd"]
    assert "dag_cycle" in rules(workflow_semantics(mutated, "workflow.yaml"))


def test_missing_and_self_dependencies_are_rejected(contract_env):
    _, _, workflow = contract_env
    missing = deepcopy(workflow)
    missing["nodes"]["idea"]["depends_on"] = ["does_not_exist"]
    assert "missing_dependency" in rules(workflow_semantics(missing, "workflow.yaml"))

    self_dependent = deepcopy(workflow)
    self_dependent["nodes"]["idea"]["depends_on"] = ["idea"]
    assert "self_dependency" in rules(workflow_semantics(self_dependent, "workflow.yaml"))


def test_condition_node_must_be_dependency(contract_env):
    _, _, workflow = contract_env
    mutated = deepcopy(workflow)
    mutated["nodes"]["proof"]["depends_on"] = []
    assert "condition_dependency" in rules(workflow_semantics(mutated, "workflow.yaml"))


def test_condition_result_must_match_upstream_kind(contract_env):
    _, _, workflow = contract_env
    mutated = deepcopy(workflow)
    mutated["nodes"]["proof"]["when"] = {"node": "feasibility", "verification_result": "FAIL"}
    assert "condition_type" in rules(workflow_semantics(mutated, "workflow.yaml"))


def test_predicate_with_multiple_result_fields_is_schema_invalid(contract_env):
    schemas, registry, workflow = contract_env
    mutated = deepcopy(workflow)
    mutated["nodes"]["proof"]["when"]["node_status"] = "VERIFIED"
    diagnostics = validate_instance(mutated, "workflow.schema.json", "workflow.yaml", schemas, registry)
    assert "oneOf" in rules(diagnostics)


@pytest.mark.parametrize("illegal_field", ["condition", "activation"])
def test_legacy_condition_fields_are_rejected(contract_env, illegal_field):
    schemas, registry, workflow = contract_env
    mutated = deepcopy(workflow)
    mutated["nodes"]["proof"][illegal_field] = "legacy"
    diagnostics = validate_instance(mutated, "workflow.schema.json", "workflow.yaml", schemas, registry)
    assert "additionalProperties" in rules(diagnostics)


def test_terminal_trigger_has_single_owner(contract_env):
    _, _, workflow = contract_env
    mutated = deepcopy(workflow)
    mutated["nodes"]["idea"]["trigger_on_terminal_events"] = ["CRITICAL_RESEARCH_BLOCKER"]
    assert "terminal_trigger_owner" in rules(workflow_semantics(mutated, "workflow.yaml"))


def test_build_readiness_skill_has_single_owner(contract_env):
    _, _, workflow = contract_env
    mutated = deepcopy(workflow)
    mutated["nodes"]["prd_consistency_verifier"]["skill"] = "build-readiness-verifier"
    assert "readiness_writer" in rules(workflow_semantics(mutated, "workflow.yaml"))


def test_core_nodes_and_kind_contract_are_enforced(contract_env):
    _, _, workflow = contract_env
    missing = deepcopy(workflow)
    del missing["nodes"]["prd"]
    assert "missing_core_nodes" in rules(workflow_semantics(missing, "workflow.yaml"))

    wrong_kind = deepcopy(workflow)
    wrong_kind["nodes"]["idea"]["subgraph"] = "unexpected-subgraph"
    assert "kind_contract" in rules(workflow_semantics(wrong_kind, "workflow.yaml"))


def test_core_node_clean_replacement_is_rejected(contract_env):
    _, _, workflow = contract_env
    replaced = deepcopy(workflow)
    replaced["nodes"]["idea_v2"] = replaced["nodes"].pop("idea")
    replaced["nodes"]["contract"]["depends_on"] = ["idea_v2"]

    diagnostics = workflow_semantics(replaced, "workflow.yaml")
    assert [(item.path, item.rule, item.message) for item in diagnostics] == [
        ("$.nodes", "missing_core_nodes", "Missing core nodes: idea")
    ]


def test_core_node_kind_and_implementation_drift_are_rejected(contract_env):
    _, _, workflow = contract_env
    wrong_kind = deepcopy(workflow)
    wrong_kind["nodes"]["idea"]["kind"] = "subgraph"
    wrong_kind["nodes"]["idea"]["subgraph"] = wrong_kind["nodes"]["idea"].pop("skill")
    kind_diagnostics = workflow_semantics(wrong_kind, "workflow.yaml")
    assert [(item.path, item.rule) for item in kind_diagnostics] == [
        ("$.nodes.idea.kind", "core_node_mapping")
    ]

    wrong_implementation = deepcopy(workflow)
    wrong_implementation["nodes"]["idea"]["skill"] = "idea-intake-v2"
    implementation_diagnostics = workflow_semantics(wrong_implementation, "workflow.yaml")
    assert [(item.path, item.rule) for item in implementation_diagnostics] == [
        ("$.nodes.idea.skill", "core_node_mapping")
    ]


def test_external_input_schema_reference_must_exist(contract_env):
    _, _, workflow = contract_env
    mutated = deepcopy(workflow)
    mutated["nodes"]["proof_result"]["on_submit"]["validate"] = "missing.schema.json"
    assert "missing_schema" in rules(workflow_semantics(mutated, "workflow.yaml"))


def test_workflow_skill_and_subgraph_references_must_exist(contract_env):
    _, _, workflow = contract_env
    catalog = build_repository_catalog()

    missing_skill = deepcopy(workflow)
    missing_skill["nodes"]["idea"]["skill"] = "missing-skill"
    assert "missing_skill_reference" in rules(workflow_semantics(missing_skill, "workflow.yaml", catalog))

    missing_subgraph = deepcopy(workflow)
    missing_subgraph["nodes"]["competitor"]["subgraph"] = "missing-subgraph"
    assert "missing_subgraph_reference" in rules(workflow_semantics(missing_subgraph, "workflow.yaml", catalog))
