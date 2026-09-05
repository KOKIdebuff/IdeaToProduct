from __future__ import annotations

from copy import deepcopy

import pytest

from scripts.contract_bundles import ContractBundle, ContractResolutionError, load_bundle_context, load_version_registry, resolve_contract_bundle
from scripts.validate_contracts import (
    ROOT,
    V031_CHART_TEMPLATES,
    V031_RUBRIC_PATHS,
    build_repository_catalog,
    citation_closure_diagnostics,
    load_document,
    load_schemas,
    validate_bundle,
    validate_instance,
    v031_auxiliary_contract_diagnostics,
)


def _v031_context():
    root = ROOT / "contracts" / "0.3.1"
    return load_bundle_context(ContractBundle("0.3.1", root, "staged", "audit"))


def _rules(diagnostics):
    return {item.rule for item in diagnostics}


def test_v031_staged_bundle_is_closed_without_registry_promotion():
    registry = load_version_registry()
    assert "0.3.1" not in registry.versions

    diagnostics, checked = validate_bundle(_v031_context(), version_registry=registry)

    assert diagnostics == []
    assert checked == 162

    for operation in ("new_run", "resume", "audit"):
        with pytest.raises(ContractResolutionError) as captured:
            resolve_contract_bundle("0.3.1", operation=operation, registry=registry)
        assert captured.value.code == "SCHEMA_VERSION_UNSUPPORTED"


def test_v031_inventory_profiles_rubrics_and_chart_registry_are_closed():
    context = _v031_context()
    catalog = build_repository_catalog(context.bundle.root)

    assert len(catalog.schema_names) == 23
    assert len(catalog.skill_ids) == 26
    assert len(list(context.profile_dir.glob("*.yaml"))) == 4
    assert set(catalog.rubric_paths) == set(V031_RUBRIC_PATHS.values())
    assert set(V031_CHART_TEMPLATES) == set(load_document(context.bundle.root / "chart-templates" / "registry.yaml")["templates"])
    assert v031_auxiliary_contract_diagnostics(catalog) == []


def test_v031_fixture_schema_fragments_and_citation_closure_are_validated_locally():
    context = _v031_context()
    schemas, schema_registry = load_schemas(context.schema_dir)
    projection = load_document(context.bundle.root / "fixtures" / "valid" / "report-projection.yaml")
    source = load_document(context.bundle.root / "fixtures" / "valid" / "source.yaml")["source"]

    assert validate_instance(
        projection,
        "competitor.schema.json#/$defs/report_projection",
        "projection.yaml",
        schemas,
        schema_registry,
    ) == []
    assert citation_closure_diagnostics(projection, "projection.yaml", {source["id"]: source}) == []

    citation_missing = deepcopy(source)
    citation_missing["citation_metadata"] = None
    assert "citation_metadata" in _rules(
        citation_closure_diagnostics(projection, "projection.yaml", {source["id"]: citation_missing})
    )

    unrelated = deepcopy(source)
    unrelated["id"] = "SRC-UNRELATED"
    unrelated["citation_metadata"] = None
    assert citation_closure_diagnostics(
        projection,
        "projection.yaml",
        {source["id"]: source, unrelated["id"]: unrelated},
    ) == []


def test_v031_rejects_remote_or_cross_bundle_fixture_schema_references():
    context = _v031_context()
    schemas, schema_registry = load_schemas(context.schema_dir)
    projection = load_document(context.bundle.root / "fixtures" / "valid" / "report-projection.yaml")

    for unsafe in (
        "https://example.invalid/competitor.schema.json#/$defs/report_projection",
        "../competitor.schema.json#/$defs/report_projection",
        "other/competitor.schema.json#/$defs/report_projection",
    ):
        assert "missing_schema" in _rules(validate_instance(projection, unsafe, "projection.yaml", schemas, schema_registry))
