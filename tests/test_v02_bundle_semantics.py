from copy import deepcopy

from scripts.contract_bundles import (
    load_bundle_context,
    load_bundle_schemas,
    load_version_registry,
    resolve_contract_bundle,
)
from scripts.validate_contracts import (
    CORE_NODE_CONTRACTS,
    REQUIRED_SKILL_IDS,
    REQUIRED_SUBGRAPH_IDS,
    REQUIRED_TEMPLATE_CONTRACTS,
    build_repository_catalog,
    fixture_diagnostics,
    load_document,
    profile_semantics,
    readiness_writer_diagnostics,
    skill_contract_diagnostics,
    skill_markdown_diagnostics,
    subgraph_semantics,
    template_contract_diagnostics,
    validate_instance,
    workflow_semantics,
)


def v02_environment():
    registry = load_version_registry()
    context = load_bundle_context(resolve_contract_bundle(registry=registry))
    schemas, schema_registry = load_bundle_schemas(context)
    catalog = build_repository_catalog(context.bundle.root)
    workflow = load_document(context.workflow_path)
    return context, schemas, schema_registry, catalog, workflow


def rules(diagnostics):
    return {item.rule for item in diagnostics}


def test_v02_core_workflow_is_version_locked_and_topology_preserving():
    _, schemas, schema_registry, catalog, workflow = v02_environment()
    assert validate_instance(workflow, "workflow.schema.json", "workflow.yaml", schemas, schema_registry) == []
    assert workflow_semantics(workflow, "workflow.yaml", catalog, contract_version="0.2.0") == []
    assert set(workflow["nodes"]) == set(CORE_NODE_CONTRACTS)
    assert workflow["nodes"]["idea"] == {"kind": "skill", "skill": "idea-intake", "required": True}
    assert workflow["nodes"]["build_readiness_verifier"]["skill"] == "build-readiness-verifier"

    mixed = deepcopy(workflow)
    mixed["workflow"]["version"] = "0.1.0"
    assert "contract_version" in rules(workflow_semantics(mixed, "workflow.yaml", catalog, contract_version="0.2.0"))


def test_v02_four_profiles_validate_and_compose_against_the_selected_workflow():
    context, schemas, schema_registry, catalog, workflow = v02_environment()
    profile_paths = sorted(context.profile_dir.glob("*.yaml"))
    assert len(profile_paths) == 4
    for path in profile_paths:
        document = load_document(path)
        source = path.relative_to(context.bundle.root).as_posix()
        assert validate_instance(document, "profile.schema.json", source, schemas, schema_registry) == []
        assert profile_semantics(document, source, workflow, catalog, contract_version="0.2.0") == []


def test_v02_profile_extensions_cannot_replace_core_or_override_interaction_policy():
    context, _, _, catalog, workflow = v02_environment()
    profile = load_document(context.profile_dir / "developer-tool.yaml")

    collision = deepcopy(profile)
    collision["extensions"] = [{
        "id": "idea",
        "node": {"kind": "skill", "skill": "user-evidence"},
        "insert_after": "idea",
        "before": "contract",
        "required": False,
        "config": {},
    }]
    assert "extension_collision" in rules(profile_semantics(collision, "profiles/developer-tool.yaml", workflow, catalog, contract_version="0.2.0"))

    interaction_override = deepcopy(profile)
    interaction_override["extensions"] = [{
        "id": "custom_probe",
        "node": {"kind": "skill", "skill": "user-evidence"},
        "insert_after": "idea",
        "before": "contract",
        "required": False,
        "config": {"max_rounds": 12},
    }]
    assert "profile_interaction_override" in rules(profile_semantics(interaction_override, "profiles/developer-tool.yaml", workflow, catalog, contract_version="0.2.0"))


def test_v02_profile_identity_and_version_drift_fail_closed():
    context, _, _, catalog, workflow = v02_environment()
    profile = load_document(context.profile_dir / "developer-tool.yaml")

    wrong_id = deepcopy(profile)
    wrong_id["profile"]["id"] = "consumer_app"
    assert "contract_identity" in rules(profile_semantics(wrong_id, "profiles/developer-tool.yaml", workflow, catalog, contract_version="0.2.0"))

    wrong_version = deepcopy(profile)
    wrong_version["profile"]["version"] = "0.1.0"
    assert "contract_version" in rules(profile_semantics(wrong_version, "profiles/developer-tool.yaml", workflow, catalog, contract_version="0.2.0"))


def test_v02_all_23_skill_contracts_and_markdown_files_are_closed():
    context, schemas, schema_registry, catalog, _ = v02_environment()
    documents = {}
    assert catalog.skill_ids == REQUIRED_SKILL_IDS
    for skill_id in sorted(REQUIRED_SKILL_IDS):
        directory = context.skill_dir / skill_id
        document = load_document(directory / "skill.yaml")
        documents[skill_id] = document
        source = f"skills/{skill_id}/skill.yaml"
        assert validate_instance(document, "skill.schema.json", source, schemas, schema_registry) == []
        assert skill_contract_diagnostics(document, source, skill_id, catalog, schemas, contract_version="0.2.0") == []
        markdown = (directory / "SKILL.md").read_text(encoding="utf-8")
        assert skill_markdown_diagnostics(
            markdown,
            f"skills/{skill_id}/SKILL.md",
            skill_id,
            interaction_required="interaction" in document,
        ) == []
    assert readiness_writer_diagnostics(documents) == []


def test_v02_only_idea_intake_declares_the_exact_adaptive_interaction_model():
    context, schemas, schema_registry, catalog, _ = v02_environment()
    interaction_skills = []
    for skill_id in sorted(REQUIRED_SKILL_IDS):
        document = load_document(context.skill_dir / skill_id / "skill.yaml")
        if "interaction" in document:
            interaction_skills.append(skill_id)
    assert interaction_skills == ["idea-intake"]

    idea = load_document(context.skill_dir / "idea-intake" / "skill.yaml")
    interaction = idea["interaction"]
    assert set(interaction["supported_methods"]) == {
        "clarification",
        "controlled_brainstorming",
        "adaptive_product_discovery_interview",
        "assumption_challenge",
    }
    assert interaction["selection_policy"] == "highest_value_gap"
    assert interaction["one_question_at_a_time"] is True
    assert interaction["allow_freeform_answer"] is True
    assert interaction["max_rounds"] == 8
    assert interaction["early_exit_when_sufficient"] is True

    incomplete = deepcopy(idea)
    incomplete["interaction"]["supported_methods"].pop()
    assert validate_instance(incomplete, "skill.schema.json", "idea-intake.yaml", schemas, schema_registry)

    non_interactive = load_document(context.skill_dir / "user-evidence" / "skill.yaml")
    illegal = deepcopy(non_interactive)
    illegal["interaction"] = deepcopy(interaction)
    assert validate_instance(illegal, "skill.schema.json", "user-evidence.yaml", schemas, schema_registry)
    assert "interaction_contract" in rules(skill_contract_diagnostics(illegal, "skills/user-evidence/skill.yaml", "user-evidence", catalog, schemas, contract_version="0.2.0"))


def test_v02_interaction_markdown_and_yaml_must_stay_synchronized():
    context, _, _, _, _ = v02_environment()
    markdown = (context.skill_dir / "idea-intake" / "SKILL.md").read_text(encoding="utf-8")
    missing_section = markdown.replace("## Interaction Model", "## Interaction Strategy", 1)
    assert "skill_markdown_contract" in rules(skill_markdown_diagnostics(
        missing_section,
        "skills/idea-intake/SKILL.md",
        "idea-intake",
        interaction_required=True,
    ))


def test_v02_competitor_subgraph_is_versioned_and_producer_closed():
    context, schemas, schema_registry, catalog, _ = v02_environment()
    assert catalog.subgraph_ids == REQUIRED_SUBGRAPH_IDS
    document = load_document(context.subgraph_dir / "competitor-research.yaml")
    source = "subgraphs/competitor-research.yaml"
    assert validate_instance(document, "subgraph.schema.json", source, schemas, schema_registry) == []

    skill_output_types = {}
    for skill_id in REQUIRED_SKILL_IDS:
        skill = load_document(context.skill_dir / skill_id / "skill.yaml")
        skill_output_types[skill_id] = {
            output["artifact_type"]
            for output in skill["output_contracts"]
        }
    assert subgraph_semantics(document, source, catalog, skill_output_types, contract_version="0.2.0") == []

    mixed = deepcopy(document)
    mixed["subgraph"]["version"] = "0.1.0"
    assert "contract_version" in rules(subgraph_semantics(mixed, source, catalog, skill_output_types, contract_version="0.2.0"))

    bad_producer = deepcopy(document)
    bad_producer["output_contracts"][0]["producer"] = "not_present"
    assert "output_contract_producer" in rules(subgraph_semantics(bad_producer, source, catalog, skill_output_types, contract_version="0.2.0"))


def test_v02_five_templates_have_locked_front_matter_and_nonempty_bodies():
    context, _, _, catalog, _ = v02_environment()
    assert catalog.template_paths == frozenset(REQUIRED_TEMPLATE_CONTRACTS)
    for relative_path, artifact_type in REQUIRED_TEMPLATE_CONTRACTS.items():
        text = (context.bundle.root / relative_path).read_text(encoding="utf-8")
        assert template_contract_diagnostics(text, relative_path, artifact_type, contract_version="0.2.0") == []

        mixed = text.replace("version: 0.2.0", "version: 0.1.0", 1)
        assert "template_contract" in rules(template_contract_diagnostics(mixed, relative_path, artifact_type, contract_version="0.2.0"))


def test_v02_bundle_fixture_manifest_is_complete_and_all_cases_are_deterministic():
    context, schemas, schema_registry, catalog, workflow = v02_environment()
    diagnostics, checked = fixture_diagnostics(
        schemas,
        schema_registry,
        workflow,
        bundle_root=context.bundle.root,
        fixture_manifest_path=context.fixture_manifest_path,
        contract_version="0.2.0",
        catalog=catalog,
    )
    assert diagnostics == []
    assert checked == 45

    manifest = load_document(context.fixture_manifest_path)
    positive = [case for case in manifest["cases"] if case["expected_valid"]]
    assert len(positive) == 25
    assert manifest["contract_version"] == "0.2.0"
    assert manifest["path_resolution"] == "bundle_root_relative"

    partial = load_document(context.bundle.root / "fixtures/valid/idea-definition.yaml")
    clear = load_document(context.bundle.root / "fixtures/valid/idea-definition-clear.yaml")
    assert partial["shaping"] == {"mode": "PARTIAL", "rounds_used": 3, "completion_outcome": "PARTIAL_RESEARCHABLE"}
    assert clear["shaping"] == {"mode": "CLEAR", "rounds_used": 0, "completion_outcome": "SUFFICIENT"}
