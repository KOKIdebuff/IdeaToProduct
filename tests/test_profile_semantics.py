from __future__ import annotations

from copy import deepcopy

from scripts.validate_contracts import ROOT, build_repository_catalog, load_document, profile_semantics


def rules(diagnostics):
    return {item.rule for item in diagnostics}


def test_consumer_profile_requires_visualization_choice(contract_env):
    _, _, workflow = contract_env
    profile = load_document(ROOT / "profiles" / "consumer-app.yaml")
    mutated = deepcopy(profile)
    del mutated["competitor_visualizations"]["choose_one"]
    assert "profile_choose_one" in rules(profile_semantics(mutated, "consumer-app.yaml", workflow))


def test_non_consumer_profile_cannot_define_consumer_choice(contract_env):
    _, _, workflow = contract_env
    profile = load_document(ROOT / "profiles" / "developer-tool.yaml")
    mutated = deepcopy(profile)
    mutated["competitor_visualizations"]["choose_one"] = {
        "options": ["pricing_comparison", "sentiment_distribution"],
        "selected_by": "research_contract",
    }
    assert "profile_choose_one" in rules(profile_semantics(mutated, "developer-tool.yaml", workflow))


def test_profile_extension_cannot_collide_with_core_node(contract_env):
    _, _, workflow = contract_env
    profile = load_document(ROOT / "profiles" / "developer-tool.yaml")
    mutated = deepcopy(profile)
    mutated["extensions"] = [{
        "id": "idea",
        "node": {"kind": "skill", "skill": "paper-landscape"},
        "insert_after": "gate_research",
        "before": "research_verifier",
        "required": True,
        "config": {},
    }]
    assert "extension_collision" in rules(profile_semantics(mutated, "developer-tool.yaml", workflow))


def test_profile_extension_must_preserve_dag(contract_env):
    _, _, workflow = contract_env
    profile = load_document(ROOT / "profiles" / "developer-tool.yaml")
    mutated = deepcopy(profile)
    mutated["extensions"] = [{
        "id": "late_extension",
        "node": {"kind": "skill", "skill": "late-extension"},
        "insert_after": "prd",
        "before": "idea",
        "required": True,
        "config": {},
    }]
    assert "extension_cycle" in rules(profile_semantics(mutated, "developer-tool.yaml", workflow))


def test_profile_extension_cannot_add_readiness_writer(contract_env):
    _, _, workflow = contract_env
    profile = load_document(ROOT / "profiles" / "developer-tool.yaml")
    mutated = deepcopy(profile)
    mutated["extensions"] = [{
        "id": "second_readiness_writer",
        "node": {"kind": "verifier", "skill": "build-readiness-verifier"},
        "insert_after": "prd",
        "before": "prd_consistency_verifier",
        "required": True,
        "config": {},
    }]
    assert "readiness_writer" in rules(profile_semantics(mutated, "developer-tool.yaml", workflow))


def test_profile_added_gate_requires_rationale(contract_env):
    _, _, workflow = contract_env
    profile = load_document(ROOT / "profiles" / "developer-tool.yaml")
    mutated = deepcopy(profile)
    mutated["extensions"] = [{
        "id": "extra_gate",
        "node": {"kind": "human_gate", "gate": "extra-gate"},
        "insert_after": "gate_research",
        "before": "research_verifier",
        "required": True,
        "config": {},
    }]
    assert "extension_gate_rationale" in rules(profile_semantics(mutated, "developer-tool.yaml", workflow))


def test_profile_extension_skill_reference_must_exist(contract_env):
    _, _, workflow = contract_env
    profile = load_document(ROOT / "profiles" / "developer-tool.yaml")
    mutated = deepcopy(profile)
    mutated["extensions"] = [{
        "id": "missing_skill_extension",
        "node": {"kind": "skill", "skill": "missing-skill"},
        "insert_after": "gate_research",
        "before": "research_verifier",
        "required": True,
        "config": {},
    }]
    diagnostics = profile_semantics(mutated, "developer-tool.yaml", workflow, build_repository_catalog())
    assert "missing_skill_reference" in rules(diagnostics)
