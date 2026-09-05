from copy import deepcopy

from jsonschema import Draft202012Validator

from scripts.contract_bundles import (
    load_bundle_context,
    load_bundle_schemas,
    load_version_registry,
    resolve_contract_bundle,
)
from scripts.validate_contracts import (
    artifact_schema_diagnostics,
    interaction_semantics,
    load_document,
    reference_diagnostics,
    research_origin_diagnostics,
    validate_instance,
)


def v02_environment():
    registry = load_version_registry()
    bundle = resolve_contract_bundle("0.2.0", operation="audit", registry=registry)
    context = load_bundle_context(bundle)
    schemas, schema_registry = load_bundle_schemas(context)
    return context, schemas, schema_registry


def rules(diagnostics):
    return {item.rule for item in diagnostics}


def test_v02_foundational_schemas_are_draft_202012_and_locally_closed():
    _, schemas, _ = v02_environment()
    foundational = {
        "common.schema.json",
        "artifact.schema.json",
        "source.schema.json",
        "evidence.schema.json",
        "claim.schema.json",
        "decision.schema.json",
    }
    for name in foundational:
        Draft202012Validator.check_schema(schemas[name])
    assert reference_diagnostics(schemas) == []


def test_v02_foundational_positive_fixtures_validate():
    context, schemas, schema_registry = v02_environment()
    cases = {
        "artifact.yaml": "artifact.schema.json",
        "source.yaml": "source.schema.json",
        "evidence.yaml": "evidence.schema.json",
        "claim.yaml": "claim.schema.json",
        "decision.yaml": "decision.schema.json",
    }
    for filename, schema_name in cases.items():
        document = load_document(context.bundle.root / "fixtures" / "valid" / filename)
        assert validate_instance(document, schema_name, filename, schemas, schema_registry) == []


def test_v02_artifact_header_and_error_taxonomy_are_version_locked():
    context, schemas, schema_registry = v02_environment()
    artifact = load_document(context.bundle.root / "fixtures" / "valid" / "artifact.yaml")
    mixed = deepcopy(artifact)
    mixed["artifact"]["schema_version"] = "0.1.0"
    assert "const" in rules(validate_instance(mixed, "artifact.schema.json", "artifact.yaml", schemas, schema_registry))

    error_codes = set(schemas["common.schema.json"]["$defs"]["error_code"]["enum"])
    assert {"INSUFFICIENT_PRODUCT_CONTEXT", "SCHEMA_VERSION_UNSUPPORTED"} <= error_codes
    assert schemas["artifact.schema.json"]["additionalProperties"] is True
    assert schemas["artifact.schema.json"]["properties"]["artifact"]["additionalProperties"] is False


def test_v02_remote_or_parent_schema_refs_are_rejected():
    _, schemas, _ = v02_environment()
    remote = deepcopy(schemas)
    remote["artifact.schema.json"]["properties"]["artifact"]["properties"]["schema_version"]["$ref"] = "https://example.com/common.schema.json"
    assert "external_ref" in rules(reference_diagnostics(remote))

    parent = deepcopy(schemas)
    parent["artifact.schema.json"]["properties"]["artifact"]["properties"]["schema_version"]["$ref"] = "../schemas/common.schema.json#/$defs/schema_version"
    assert "unsafe_ref" in rules(reference_diagnostics(parent))


def test_v02_wire_contract_positive_fixtures_validate():
    context, schemas, schema_registry = v02_environment()
    cases = {
        "workflow-state.yaml": "workflow-state.schema.json",
        "workflow-state-interaction.yaml": "workflow-state.schema.json",
        "executor-request.yaml": "executor-request.schema.json",
        "executor-request-interaction-resume.yaml": "executor-request.schema.json",
        "executor-result-success.yaml": "executor-result.schema.json",
        "executor-result-failure.yaml": "executor-result.schema.json",
        "executor-result-waiting.yaml": "executor-result.schema.json",
        "run-policy.yaml": "run-policy.schema.json",
        "artifact-manifest.json": "artifact-manifest.schema.json",
        "verification.yaml": "verification.schema.json",
        "gate.yaml": "gate.schema.json",
        "readiness.yaml": "readiness-result.schema.json",
    }
    for filename, schema_name in cases.items():
        document = load_document(context.bundle.root / "fixtures" / "valid" / filename)
        assert validate_instance(document, schema_name, filename, schemas, schema_registry) == []
        assert interaction_semantics(document, filename) == []


def test_v02_state_separates_interaction_gate_and_contract_timing():
    context, schemas, schema_registry = v02_environment()
    state = load_document(context.bundle.root / "fixtures" / "valid" / "workflow-state-interaction.yaml")
    assert state["research_contract_ref"] is None

    mixed_gate = deepcopy(state)
    mixed_gate["current_gate"] = "gate_research"
    assert validate_instance(mixed_gate, "workflow-state.schema.json", "state.yaml", schemas, schema_registry)

    missing_attempt = deepcopy(state)
    del missing_attempt["nodes"]["idea"]["active_attempt_id"]
    assert "required" in rules(validate_instance(missing_attempt, "workflow-state.schema.json", "state.yaml", schemas, schema_registry))

    mismatched_attempt = deepcopy(state)
    mismatched_attempt["nodes"]["idea"]["active_attempt_id"] = "ATT-IDEA-OTHER"
    assert "interaction_attempt_mismatch" in rules(interaction_semantics(mismatched_attempt, "state.yaml"))


def test_v02_executor_waiting_result_has_strict_conditional_fields():
    context, schemas, schema_registry = v02_environment()
    waiting = load_document(context.bundle.root / "fixtures" / "valid" / "executor-result-waiting.yaml")

    missing_checkpoint = deepcopy(waiting)
    del missing_checkpoint["executor_result"]["interaction_checkpoint"]
    assert "required" in rules(validate_instance(missing_checkpoint, "executor-result.schema.json", "result.yaml", schemas, schema_registry))

    final_output = deepcopy(waiting)
    final_output["executor_result"]["output_artifact_refs"] = ["ART-IDEA-001@1"]
    assert "maxItems" in rules(validate_instance(final_output, "executor-result.schema.json", "result.yaml", schemas, schema_registry))

    mismatched_method = deepcopy(waiting)
    mismatched_method["executor_result"]["interaction_checkpoint"]["current_method"] = "assumption_challenge"
    assert "interaction_method_mismatch" in rules(interaction_semantics(mismatched_method, "result.yaml"))

    bad_recommendation = deepcopy(waiting)
    bad_recommendation["executor_result"]["interaction_request"]["recommendation"]["option_id"] = "C"
    assert "interaction_recommendation" in rules(interaction_semantics(bad_recommendation, "result.yaml"))


def test_v02_interaction_resume_reuses_the_same_attempt():
    context, schemas, schema_registry = v02_environment()
    request = load_document(context.bundle.root / "fixtures" / "valid" / "executor-request-interaction-resume.yaml")

    mismatched = deepcopy(request)
    mismatched["executor_request"]["interaction_resume"]["checkpoint_ref"] = "runtime/attempts/ATT-IDEA-OTHER/checkpoints/CP-0002.json"
    assert "interaction_attempt_mismatch" in rules(interaction_semantics(mismatched, "request.yaml"))

    no_answer = deepcopy(request)
    del no_answer["executor_request"]["interaction_resume"]["selected_option_id"]
    del no_answer["executor_request"]["interaction_resume"]["freeform_text"]
    assert "anyOf" in rules(validate_instance(no_answer, "executor-request.schema.json", "request.yaml", schemas, schema_registry))


def test_v02_manifest_and_current_results_reject_legacy_shapes():
    context, schemas, schema_registry = v02_environment()
    manifest = load_document(context.bundle.root / "fixtures" / "valid" / "artifact-manifest.json")
    legacy_manifest = deepcopy(manifest)
    legacy_manifest["current_artifacts"]["legacy_input_ref"] = {
        "artifact_ref": "runs/legacy-run/artifacts/evidence.yaml",
        "content_hash": "sha256:" + "0" * 64,
    }
    assert validate_instance(legacy_manifest, "artifact-manifest.schema.json", "manifest.json", schemas, schema_registry)

    legacy_readiness = {"readiness": load_document(context.bundle.root / "fixtures" / "valid" / "readiness.yaml")["readiness"]}
    assert validate_instance(legacy_readiness, "readiness-result.schema.json", "readiness.yaml", schemas, schema_registry)

    legacy_verification = {
        "verification": {"overall": "PASS", "critical_issues": [], "non_critical_issues": []},
        "sections": {
            key: {"result": "PASS", "issues": []}
            for key in ("competitor", "users", "market", "technology")
        },
    }
    assert validate_instance(legacy_verification, "verification.schema.json", "verification.yaml", schemas, schema_registry)


def test_v02_business_artifact_fixtures_and_header_composition_validate():
    context, schemas, schema_registry = v02_environment()
    cases = {
        "idea-definition.yaml": "idea.schema.json",
        "research-contract.yaml": "research.schema.json",
        "competitor-dataset.yaml": "competitor.schema.json",
        "chart-bundle.yaml": "chart.schema.json",
        "proof-result.yaml": "proof-result.schema.json",
    }
    for filename, schema_name in cases.items():
        document = load_document(context.bundle.root / "fixtures" / "valid" / filename)
        assert validate_instance(document, schema_name, filename, schemas, schema_registry) == []
    assert artifact_schema_diagnostics(schemas) == []


def test_v02_idea_definition_locks_hypothesis_boundaries_and_rounds():
    context, schemas, schema_registry = v02_environment()
    idea = load_document(context.bundle.root / "fixtures" / "valid" / "idea-definition.yaml")

    validated_assumption = deepcopy(idea)
    validated_assumption["assumptions"][0]["status"] = "VALIDATED"
    assert "const" in rules(validate_instance(validated_assumption, "idea.schema.json", "idea.yaml", schemas, schema_registry))

    premature_decision = deepcopy(idea)
    premature_decision["evidence_backed_positioning"] = "Confirmed market position"
    assert "additionalProperties" in rules(validate_instance(premature_decision, "idea.schema.json", "idea.yaml", schemas, schema_registry))

    ninth_round = deepcopy(idea)
    ninth_round["shaping"]["rounds_used"] = 9
    assert "maximum" in rules(validate_instance(ninth_round, "idea.schema.json", "idea.yaml", schemas, schema_registry))

    overquestioned_clear = deepcopy(idea)
    overquestioned_clear["shaping"]["mode"] = "CLEAR"
    overquestioned_clear["shaping"]["rounds_used"] = 2
    assert "maximum" in rules(validate_instance(overquestioned_clear, "idea.schema.json", "idea.yaml", schemas, schema_registry))


def test_v02_research_questions_are_traceable_to_real_idea_origins():
    context, schemas, schema_registry = v02_environment()
    idea = load_document(context.bundle.root / "fixtures" / "valid" / "idea-definition.yaml")
    contract = load_document(context.bundle.root / "fixtures" / "valid" / "research-contract.yaml")
    assert research_origin_diagnostics(idea, contract) == []

    dangling = deepcopy(contract)
    dangling["research_questions"]["users"][0]["origin_refs"] = ["UNK-NOT-PRESENT"]
    assert "unresolved_origin_ref" in rules(research_origin_diagnostics(idea, dangling))
    assert "missing_origin_mapping" in rules(research_origin_diagnostics(idea, dangling))

    no_questions = deepcopy(contract)
    no_questions["research_questions"] = {key: [] for key in ("competitors", "users", "market", "technology")}
    result_rules = rules(research_origin_diagnostics(idea, no_questions))
    assert {"missing_origin_mapping", "partial_researchable_without_question"} <= result_rules

    mixed_profile = deepcopy(contract)
    mixed_profile["profile_ref"] = "developer_tool@0.1.0"
    assert "pattern" in rules(validate_instance(mixed_profile, "research.schema.json", "research.yaml", schemas, schema_registry))
