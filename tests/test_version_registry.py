from copy import deepcopy
from dataclasses import replace

from jsonschema import Draft202012Validator

import pytest

from scripts.contract_bundles import (
    ContractResolutionError,
    load_bundle_context,
    load_version_registry,
    require_bundle_version,
    resolve_bundle_reference,
    resolve_contract_bundle,
    validate_bundle,
    verify_integrity,
)
from scripts.validate_contracts import ROOT, load_document


def test_registry_schema_and_config_are_valid():
    schema = load_document(ROOT / "contracts" / "registry.schema.json")
    document = load_document(ROOT / "contracts" / "registry.yaml")

    Draft202012Validator.check_schema(schema)
    assert list(Draft202012Validator(schema).iter_errors(document)) == []

    registry = load_version_registry(require_bundles=False)
    assert registry.default_new_run_version == "0.3.0"
    assert set(registry.versions) == {"0.1.0", "0.2.0", "0.3.0"}
    assert registry.versions["0.1.0"].status == "immutable_baseline"
    assert registry.versions["0.2.0"].status == "frozen_previous"
    assert registry.versions["0.3.0"].status == "current"


def test_registry_allows_only_the_current_version_for_new_runs():
    registry = load_version_registry(require_bundles=False)
    allowed = [version for version, entry in registry.versions.items() if entry.new_runs_allowed]
    assert allowed == ["0.3.0"]
    assert registry.versions["0.1.0"].resume_allowed is False
    assert registry.versions["0.1.0"].audit_allowed is True
    assert registry.versions["0.2.0"].resume_allowed is True
    assert registry.versions["0.2.0"].new_runs_allowed is False


def test_registry_compatibility_matrix_is_default_deny_and_read_only():
    registry = load_version_registry(require_bundles=False)
    assert registry.default_compatibility_policy == "deny"
    assert {rule.ref_type for rule in registry.compatibility_rules} == {"source", "evidence", "claim"}
    for rule in registry.compatibility_rules:
        assert rule.source_contract_version == "0.1.0"
        assert rule.target_contract_version in {"0.2.0", "0.3.0"}
        assert rule.access == "read_only"
        assert rule.current_manifest_allowed is False
        assert rule.state_driving_allowed is False
        assert set(rule.required_revalidation) == {
            "source_schema",
            "content_hash",
            "freshness",
            "provenance",
            "security",
            "verification",
        }


def test_registry_schema_rejects_non_current_default_and_unsafe_rule():
    schema = load_document(ROOT / "contracts" / "registry.schema.json")
    document = load_document(ROOT / "contracts" / "registry.yaml")

    wrong_default = deepcopy(document)
    wrong_default["registry"]["default_new_run_version"] = "0.1.0"
    assert list(Draft202012Validator(schema).iter_errors(wrong_default))

    unsafe_rule = deepcopy(document)
    unsafe_rule["registry"]["compatibility_matrix"]["rules"][0]["current_manifest_allowed"] = True
    assert list(Draft202012Validator(schema).iter_errors(unsafe_rule))


def test_bundle_resolution_defaults_new_runs_to_v03_and_keeps_v02_resume_only():
    registry = load_version_registry(require_bundles=False)

    current = resolve_contract_bundle(registry=registry)
    assert current.contract_version == "0.3.0"
    assert current.operation == "new_run"

    baseline = resolve_contract_bundle("0.1.0", operation="audit", registry=registry)
    assert baseline.contract_version == "0.1.0"
    assert baseline.status == "immutable_baseline"

    for operation in ("new_run", "resume"):
        with pytest.raises(ContractResolutionError) as captured:
            resolve_contract_bundle("0.1.0", operation=operation, registry=registry)
        assert captured.value.code == "SCHEMA_VERSION_UNSUPPORTED"

    frozen = resolve_contract_bundle("0.2.0", operation="resume", registry=registry)
    assert frozen.contract_version == "0.2.0"
    assert frozen.status == "frozen_previous"
    with pytest.raises(ContractResolutionError) as captured:
        resolve_contract_bundle("0.2.0", operation="new_run", registry=registry)
    assert captured.value.code == "SCHEMA_VERSION_UNSUPPORTED"


def test_bundle_resolution_fails_closed_for_unknown_or_implicit_resume_version():
    registry = load_version_registry(require_bundles=False)

    with pytest.raises(ContractResolutionError) as captured:
        resolve_contract_bundle("9.9.9", operation="new_run", registry=registry)
    assert captured.value.code == "SCHEMA_VERSION_UNSUPPORTED"

    with pytest.raises(ContractResolutionError) as captured:
        resolve_contract_bundle(operation="resume", registry=registry)
    assert captured.value.code == "INPUT_INVALID"


def test_versioned_references_must_match_the_selected_bundle():
    assert require_bundle_version("developer_tool@0.3.0", "0.3.0") == "developer_tool"

    with pytest.raises(ContractResolutionError) as captured:
        require_bundle_version("developer_tool@0.2.0", "0.3.0")
    assert captured.value.code == "SCHEMA_VERSION_UNSUPPORTED"
    assert captured.value.rule == "mixed_bundle_version"

    with pytest.raises(ContractResolutionError):
        require_bundle_version("developer_tool", "0.2.0")


def test_bundle_references_never_escape_or_fallback_from_selected_root():
    registry = load_version_registry(require_bundles=False)
    baseline = resolve_contract_bundle("0.1.0", operation="audit", registry=registry)
    context = load_bundle_context(baseline)

    resolved = resolve_bundle_reference(context, "schemas/common.schema.json", allowed_prefixes=("schemas",))
    assert resolved == (ROOT / "schemas" / "common.schema.json").resolve()

    for unsafe in ("../schemas/common.schema.json", "schemas\\common.schema.json", "https://example.com/schema.json"):
        with pytest.raises(ContractResolutionError):
            resolve_bundle_reference(context, unsafe, allowed_prefixes=("schemas",))

    with pytest.raises(ContractResolutionError) as captured:
        resolve_bundle_reference(context, "schemas/not-present.schema.json", allowed_prefixes=("schemas",))
    assert captured.value.rule == "missing_contract_asset"


def test_v02_frozen_inventory_and_v03_current_inventory_are_complete_and_locked():
    registry = load_version_registry()
    frozen = load_bundle_context(resolve_contract_bundle("0.2.0", operation="audit", registry=registry))
    current = load_bundle_context(resolve_contract_bundle(registry=registry))

    assert len(list(frozen.schema_dir.glob("*.schema.json"))) == 23
    assert len([path for path in frozen.skill_dir.iterdir() if path.is_dir()]) == 23
    assert len(list(frozen.profile_dir.glob("*.yaml"))) == 4
    assert len(list(frozen.subgraph_dir.glob("*.yaml"))) == 1
    assert len(list(frozen.template_dir.glob("*.md"))) == 5
    assert len(list(current.schema_dir.glob("*.schema.json"))) == 23
    assert (current.template_dir / "competitor-report.html").is_file()
    assert not (current.template_dir / "competitor-report.md").exists()
    assert verify_integrity(registry) == []


def test_v02_frozen_manifest_hash_is_checked_before_bundle_inventory():
    registry = load_version_registry()
    protection = registry.frozen_bundle_manifests["0.2.0"]
    tampered = replace(
        registry,
        frozen_bundle_manifests={"0.2.0": replace(protection, sha256="0" * 64)},
    )
    failures = verify_integrity(tampered)
    assert any("frozen bundle 0.2.0 manifest: expected" in failure for failure in failures)


def test_public_bundle_validator_keeps_v01_v02_and_v03_contexts_isolated():
    registry = load_version_registry()
    baseline = resolve_contract_bundle("0.1.0", operation="audit", registry=registry)
    frozen = resolve_contract_bundle("0.2.0", operation="audit", registry=registry)
    current = resolve_contract_bundle("0.3.0", operation="new_run", registry=registry)

    baseline_diagnostics, baseline_checked = validate_bundle(baseline, registry=registry)
    frozen_diagnostics, frozen_checked = validate_bundle(frozen, registry=registry)
    current_diagnostics, current_checked = validate_bundle(current, registry=registry)

    assert baseline_diagnostics == []
    assert baseline_checked == 111
    assert frozen_diagnostics == []
    assert frozen_checked == 132
    assert current_diagnostics == []
    assert current_checked == 134
