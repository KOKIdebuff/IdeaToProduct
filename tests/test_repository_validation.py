from __future__ import annotations

from scripts.validate_contracts import (
    FIXTURE_MANIFEST,
    PROFILE_EXPECTATIONS,
    REQUIRED_SCHEMA_NAMES,
    REQUIRED_SKILL_IDS,
    REQUIRED_SUBGRAPH_IDS,
    REQUIRED_TEMPLATE_CONTRACTS,
    ROOT,
    load_document,
    main,
    validate_repository,
)


def expected_bundle_checked_count(fixture_manifest):
    manifest = load_document(fixture_manifest)
    fixture_count = len(manifest["cases"]) + len(manifest.get("legacy_cases", []))
    return (
        len(REQUIRED_SCHEMA_NAMES)
        + 2 * len(REQUIRED_SKILL_IDS)
        + len(REQUIRED_SUBGRAPH_IDS)
        + len(REQUIRED_TEMPLATE_CONTRACTS)
        + 1  # workflow.yaml
        + len(PROFILE_EXPECTATIONS)
        + fixture_count
    )


def test_repository_contracts_are_valid():
    diagnostics, checked = validate_repository()
    baseline_count = expected_bundle_checked_count(FIXTURE_MANIFEST)
    current_count = expected_bundle_checked_count(ROOT / "contracts" / "0.2.0" / "fixtures" / "manifest.json")
    expected = 3 + baseline_count + current_count  # Registry Schema/config + immutable integrity audit
    assert baseline_count == 111
    assert current_count == 132
    assert expected == 246
    assert checked == expected
    assert diagnostics == []


def test_validator_exit_code_is_zero():
    assert main() == 0
