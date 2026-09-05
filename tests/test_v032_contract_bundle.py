from __future__ import annotations

import pytest

from scripts.contract_bundles import ContractBundle, ContractResolutionError, load_bundle_context, load_version_registry, resolve_contract_bundle
from scripts.validate_contracts import ROOT, load_document, load_schemas, validate_bundle, validate_instance


def _v032_context():
    root = ROOT / "contracts" / "0.3.2"
    return load_bundle_context(ContractBundle("0.3.2", root, "staged", "audit"))


def test_v032_report_pipeline_bundle_is_closed_without_registry_promotion():
    registry = load_version_registry()
    assert "0.3.2" not in registry.versions
    diagnostics, checked = validate_bundle(_v032_context(), version_registry=registry)
    assert diagnostics == []
    assert checked == 169
    for operation in ("new_run", "resume", "audit"):
        with pytest.raises(ContractResolutionError) as captured:
            resolve_contract_bundle("0.3.2", operation=operation, registry=registry)
        assert captured.value.code == "SCHEMA_VERSION_UNSUPPORTED"


def test_v032_separates_chart_projection_and_report_builder_contracts():
    context = _v032_context()
    subgraph = load_document(context.bundle.root / "subgraphs" / "competitor-research.yaml")
    nodes = subgraph["nodes"]
    assert nodes["chart_rendering"]["depends_on"] == ["fact_provenance"]
    assert nodes["report_publication_projection"]["depends_on"] == ["fact_provenance", "chart_rendering"]
    assert nodes["report_builder"]["depends_on"] == ["report_publication_projection"]
    schemas, schema_registry = load_schemas(context.schema_dir)
    collection = load_document(context.bundle.root / "fixtures" / "valid" / "chart-bundle-collection.yaml")
    publication = load_document(context.bundle.root / "fixtures" / "valid" / "report-publication-projection.yaml")
    report = load_document(context.bundle.root / "fixtures" / "valid" / "competitor-report.yaml")
    assert validate_instance(collection, "chart.schema.json#/$defs/chart_bundle_collection", "collection.yaml", schemas, schema_registry) == []
    assert validate_instance(publication, "competitor.schema.json#/$defs/report_publication_projection", "publication.yaml", schemas, schema_registry) == []
    assert validate_instance(report, "competitor.schema.json#/$defs/competitor_report", "report.yaml", schemas, schema_registry) == []
