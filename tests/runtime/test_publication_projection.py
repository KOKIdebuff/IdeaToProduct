from __future__ import annotations

from copy import deepcopy

import pytest

from scripts.contract_bundles import ContractBundle, load_bundle_context
from scripts.validate_contracts import ROOT, load_schemas, validate_instance
from skillgraph_runtime.errors import RuntimeContractError
from skillgraph_runtime.fact_provenance import canonical_value_hash
from skillgraph_runtime.publication_projection import materialize_report_publication_projection


def _header(identifier: str, artifact_type: str, *, attempt: str) -> dict:
    return {
        "id": identifier,
        "type": artifact_type,
        "schema_version": "0.3.2",
        "version": 1,
        "produced_by": {"skill": "report-publication-projection", "attempt": attempt},
        "created_at": "2026-09-03T00:00:00Z",
        "supersedes": None,
        "status": "active",
    }


def _inputs() -> dict:
    text_value = "Product A has a documented paid plan."
    base_fact = {
        "fact_id": "FACT-TEXT-001",
        "origin_artifact_ref": "ART-DATASET-001@1",
        "origin_field_pointer": "/competitors/0/metrics/pricing/value",
        "content_hash": canonical_value_hash(text_value),
        "fact_class": "dataset",
        "claim_refs": ["CL-TEXT-001"],
        "evidence_refs": ["EV-TEXT-001"],
        "source_refs": ["SRC-TEXT-001"],
    }
    base = {
        "artifact": _header("ART-REPORT-PROJECTION-001", "report_projection", attempt="ATT-BASE-001"),
        "input_state_version": 10,
        "input_artifact_refs": ["ART-DATASET-001@1"],
        "fact_groups": [
            {
                "id": "FG-PRICING-001",
                "section_id": "pricing",
                "dom_scope_id": "pricing-product-a",
                "facts": [base_fact],
                "citation_source_ids": ["SRC-TEXT-001"],
            }
        ],
        "citation_closure": {
            "claim_ids": ["CL-TEXT-001"],
            "evidence_ids": ["EV-TEXT-001"],
            "source_ids": ["SRC-TEXT-001"],
        },
        "verification_status": "PENDING",
        "scoring_status": "NOT_PERFORMED",
    }
    chart_bundle = {
        "artifact": _header("ART-CHART-001", "chart_bundle", attempt="ATT-CHART-001"),
        "chart": {"id": "chart-feature-001", "type": "feature_matrix", "renderer_kind": "matrix"},
        "data_ref": "artifacts/02-research/competitors/visualizations/feature-matrix/data.json",
        "chart_spec_ref": "artifacts/02-research/competitors/visualizations/feature-matrix/chart-spec.json",
        "svg_ref": "artifacts/02-research/competitors/visualizations/feature-matrix/chart.svg",
        "insight_ref": "artifacts/02-research/competitors/visualizations/feature-matrix/insight.md",
        "compatibility_export": {"requested": False, "status": "NOT_REQUESTED", "error": None},
        "observation": "Product A has stronger verified feature coverage.",
        "interpretation": "The matrix remains limited to cited observed fields.",
        "product_implication": "Differentiate through workflow depth.",
        "confidence": "MEDIUM",
        "claim_refs": ["CL-CHART-001"],
        "evidence_ids": ["EV-CHART-001"],
        "limitations": ["Missing data remains explicit."],
    }
    collection = {
        "artifact": _header("ART-CHART-COLLECTION-001", "chart_bundle_collection", attempt="ATT-CHART-001"),
        "bundles": [chart_bundle],
    }
    claims = [
        {
            "id": "CL-TEXT-001",
            "statement": text_value,
            "category": "competitor",
            "status": "VALIDATED",
            "confidence": "HIGH",
            "evidence_ids": ["EV-TEXT-001"],
            "contradiction_ids": [],
        },
        {
            "id": "CL-CHART-001",
            "statement": chart_bundle["observation"],
            "category": "competitor",
            "status": "VALIDATED",
            "confidence": "MEDIUM",
            "evidence_ids": ["EV-CHART-001"],
            "contradiction_ids": [],
        },
    ]
    evidence = [
        {
            "id": "EV-TEXT-001",
            "claim_id": "CL-TEXT-001",
            "source_id": "SRC-TEXT-001",
            "evidence_type": "qualitative",
            "direction": "supports",
            "relevance": "high",
            "reliability": "high",
            "freshness": "high",
            "notes": "Supports pricing fact.",
        },
        {
            "id": "EV-CHART-001",
            "claim_id": "CL-CHART-001",
            "source_id": "SRC-CHART-001",
            "evidence_type": "qualitative",
            "direction": "supports",
            "relevance": "high",
            "reliability": "high",
            "freshness": "high",
            "notes": "Supports chart observation.",
        },
    ]
    sources = {
        "SRC-TEXT-001": {"id": "SRC-TEXT-001"},
        "SRC-CHART-001": {"id": "SRC-CHART-001"},
    }
    return {
        "artifact": {"id": "ART-PUBLICATION-PROJECTION-001", **_header(
            "ART-PUBLICATION-PROJECTION-001", "report_publication_projection", attempt="ATT-PUBLICATION-001"
        )},
        "base_projection": base,
        "chart_bundle_collection": collection,
        "claims": claims,
        "evidence": evidence,
        "sources": sources,
    }


def _materialize(values: dict) -> dict:
    return materialize_report_publication_projection(**values)


def test_materializes_deterministic_schema_valid_minimum_citation_closure():
    values = _inputs()
    result = _materialize(values)
    assert result == _materialize(deepcopy(values))
    assert result["report_projection_ref"] == "ART-REPORT-PROJECTION-001@1"
    assert result["chart_bundle_collection_ref"] == "ART-CHART-COLLECTION-001@1"
    assert result["verification_status"] == "PENDING"
    assert result["scoring_status"] == "NOT_PERFORMED"
    assert result["citation_closure"] == {
        "claim_ids": ["CL-CHART-001", "CL-TEXT-001"],
        "evidence_ids": ["EV-CHART-001", "EV-TEXT-001"],
        "source_ids": ["SRC-CHART-001", "SRC-TEXT-001"],
    }
    chart_group = result["fact_groups"][-1]
    assert chart_group["dom_scope_id"] == "chart-feature-matrix"
    assert chart_group["facts"][0]["origin_field_pointer"] == "/observation"
    assert chart_group["facts"][0]["content_hash"] == canonical_value_hash(
        values["chart_bundle_collection"]["bundles"][0]["observation"]
    )

    context = load_bundle_context(ContractBundle("0.3.2", ROOT / "contracts" / "0.3.2", "staged", "audit"))
    schemas, registry = load_schemas(context.schema_dir)
    assert validate_instance(
        result,
        "competitor.schema.json#/$defs/report_publication_projection",
        "generated-publication-projection.json",
        schemas,
        registry,
    ) == []


def test_extra_input_records_do_not_expand_the_minimum_closure():
    values = _inputs()
    values["claims"].append({
        "id": "CL-UNUSED-001",
        "statement": "Unused",
        "category": "competitor",
        "status": "VALIDATED",
        "confidence": "LOW",
        "evidence_ids": ["EV-UNUSED-001"],
        "contradiction_ids": [],
    })
    values["evidence"].append({
        "id": "EV-UNUSED-001",
        "claim_id": "CL-UNUSED-001",
        "source_id": "SRC-UNUSED-001",
        "evidence_type": "qualitative",
        "direction": "supports",
        "relevance": "low",
        "reliability": "low",
        "freshness": "low",
        "notes": "Not rendered.",
    })
    values["sources"]["SRC-UNUSED-001"] = {"id": "SRC-UNUSED-001"}
    assert "SRC-UNUSED-001" not in _materialize(values)["citation_closure"]["source_ids"]


@pytest.mark.parametrize(
    ("mutation", "expected_fragment"),
    [
        (lambda values: values["base_projection"]["citation_closure"]["source_ids"].append("SRC-CHART-001"), "minimum stable closure"),
        (lambda values: values["base_projection"]["fact_groups"][0]["facts"][0].__setitem__("claim_refs", ["CL-MISSING"]), "dangling Claim"),
        (lambda values: values["evidence"][0].__setitem__("source_id", "SRC-CHART-001"), "Evidence Source closure"),
        (lambda values: values["chart_bundle_collection"]["bundles"][0].__setitem__("evidence_ids", ["EV-TEXT-001"]), "Evidence closure"),
        (lambda values: values["chart_bundle_collection"]["bundles"].append(deepcopy(values["chart_bundle_collection"]["bundles"][0])), "duplicate Artifact reference"),
        (lambda values: values["claims"].append(deepcopy(values["claims"][0])), "duplicate identity"),
    ],
)
def test_fails_closed_on_dangling_mismatched_or_duplicate_provenance(mutation, expected_fragment):
    values = _inputs()
    mutation(values)
    with pytest.raises(RuntimeContractError, match=expected_fragment) as captured:
        _materialize(values)
    assert captured.value.code == "SCHEMA_INVALID"


def test_rejects_fact_groups_that_merge_different_provenance():
    values = _inputs()
    second = deepcopy(values["base_projection"]["fact_groups"][0]["facts"][0])
    second.update(
        {
            "fact_id": "FACT-TEXT-002",
            "claim_refs": ["CL-CHART-001"],
            "evidence_refs": ["EV-CHART-001"],
            "source_refs": ["SRC-CHART-001"],
        }
    )
    values["base_projection"]["fact_groups"][0]["facts"].append(second)
    values["base_projection"]["fact_groups"][0]["citation_source_ids"].append("SRC-CHART-001")
    values["base_projection"]["citation_closure"] = {
        "claim_ids": ["CL-CHART-001", "CL-TEXT-001"],
        "evidence_ids": ["EV-CHART-001", "EV-TEXT-001"],
        "source_ids": ["SRC-CHART-001", "SRC-TEXT-001"],
    }
    with pytest.raises(RuntimeContractError, match="different Evidence/Source provenance"):
        _materialize(values)


def test_rejects_duplicate_chart_type_even_with_distinct_artifact_identity():
    values = _inputs()
    duplicate = deepcopy(values["chart_bundle_collection"]["bundles"][0])
    duplicate["artifact"]["id"] = "ART-CHART-002"
    values["chart_bundle_collection"]["bundles"].append(duplicate)
    with pytest.raises(RuntimeContractError, match="duplicate chart type"):
        _materialize(values)


def test_does_not_accept_available_scoring_without_a_score_input():
    values = _inputs()
    values["base_projection"]["scoring_status"] = "AVAILABLE"
    with pytest.raises(RuntimeContractError, match="cannot claim a Score") as captured:
        _materialize(values)
    assert captured.value.code == "DEPENDENCY_NOT_READY"
