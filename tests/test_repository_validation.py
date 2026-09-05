from __future__ import annotations

from scripts.validate_contracts import (
    FIXTURE_MANIFEST,
    PROFILE_EXPECTATIONS,
    REQUIRED_SCHEMA_NAMES,
    REQUIRED_SKILL_IDS,
    REQUIRED_SUBGRAPH_IDS,
    ROOT,
    STAGED_STATIC_BUNDLE_ROOTS,
    auxiliary_contract_check_count,
    required_skill_ids_for_version,
    template_contracts_for_version,
    load_document,
    main,
    validate_repository,
)


def expected_bundle_checked_count(fixture_manifest, contract_version: str):
    manifest = load_document(fixture_manifest)
    fixture_count = len(manifest["cases"]) + len(manifest.get("legacy_cases", []))
    return (
        len(REQUIRED_SCHEMA_NAMES)
        + 2 * len(required_skill_ids_for_version(contract_version))
        + len(REQUIRED_SUBGRAPH_IDS)
        + len(template_contracts_for_version(contract_version))
        + 1  # workflow.yaml
        + len(PROFILE_EXPECTATIONS)
        + fixture_count
        + auxiliary_contract_check_count(contract_version)
    )


def test_repository_contracts_are_valid():
    diagnostics, checked = validate_repository()
    baseline_count = expected_bundle_checked_count(FIXTURE_MANIFEST, "0.1.0")
    frozen_count = expected_bundle_checked_count(ROOT / "contracts" / "0.2.0" / "fixtures" / "manifest.json", "0.2.0")
    current_count = expected_bundle_checked_count(ROOT / "contracts" / "0.3.0" / "fixtures" / "manifest.json", "0.3.0")
    staged_v031_count = expected_bundle_checked_count(ROOT / STAGED_STATIC_BUNDLE_ROOTS["0.3.1"] / "fixtures" / "manifest.json", "0.3.1")
    staged_v032_count = expected_bundle_checked_count(ROOT / STAGED_STATIC_BUNDLE_ROOTS["0.3.2"] / "fixtures" / "manifest.json", "0.3.2")
    expected = 3 + baseline_count + frozen_count + current_count + staged_v031_count + staged_v032_count  # Registry Schema/config + immutable integrity audit
    assert baseline_count == 111
    assert frozen_count == 132
    assert current_count == 134
    assert staged_v031_count == 162
    assert staged_v032_count == 169
    assert expected == 711
    assert checked == expected
    assert diagnostics == []


def test_validator_exit_code_is_zero():
    assert main() == 0
