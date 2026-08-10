from __future__ import annotations

from copy import deepcopy

import pytest
import yaml

from scripts.validate_contracts import (
    ROOT,
    build_repository_catalog,
    load_document,
    subgraph_semantics,
    validate_instance,
)


SUBGRAPH_PATH = ROOT / "subgraphs" / "competitor-research.yaml"
TEMPLATE_CONTRACTS = {
    "competitor-report.md": {
        "artifact_type": "competitor_report",
        "sections": {
            "Scope and Methodology",
            "Candidate Selection",
            "Competitor Deep Dives",
            "Normalized Dataset",
            "Scoring Methodology",
            "Feature Analysis",
            "Traction Analysis",
            "Review Analysis",
            "Pricing Analysis",
            "Required Visualizations",
            "Evidence and Sources",
            "Limitations and Unknowns",
            "Verification Summary",
        },
    },
    "synthesis.md": {
        "artifact_type": "research_synthesis",
        "sections": {
            "Validated",
            "Partially Validated",
            "Invalidated",
            "Unknown",
            "Contradictions",
            "Opportunities",
            "Risks",
        },
    },
    "product-definition.md": {
        "artifact_type": "product_definition",
        "sections": {
            "Problem",
            "Target User",
            "Job to Be Done",
            "Value Proposition",
            "Differentiation",
            "Core Object",
            "Core Workflow",
            "Product Boundary",
            "Non-goals",
            "Success Definition",
        },
    },
    "feasibility.md": {
        "artifact_type": "feasibility_review",
        "sections": {
            "Result",
            "Data Availability",
            "API Availability",
            "Platform Constraints",
            "Architecture",
            "Security",
            "Performance",
            "Operations",
            "Implementation Cost",
            "Blockers",
            "Critical Assumptions",
            "Proof Required",
        },
    },
    "prd.md": {
        "artifact_type": "prd",
        "sections": {
            "Product Summary",
            "Problem and Target User",
            "Approved Product Direction",
            "Product Definition and Core Workflow",
            "MVP Scope",
            "P0 Requirements and Decision References",
            "Non-goals",
            "Feasibility, Constraints, and Proof Status",
            "Success Metrics and Exit Criteria",
            "Risks and Accepted Risk Decisions",
            "Open Questions",
            "Traceability References",
        },
    },
}


def rules(diagnostics):
    return {item.rule for item in diagnostics}


def test_competitor_subgraph_contract_is_valid(contract_env):
    schemas, registry, _ = contract_env
    subgraph = load_document(SUBGRAPH_PATH)
    catalog = build_repository_catalog()

    assert validate_instance(
        subgraph,
        "subgraph.schema.json",
        "subgraphs/competitor-research.yaml",
        schemas,
        registry,
    ) == []
    assert subgraph_semantics(
        subgraph,
        "subgraphs/competitor-research.yaml",
        catalog,
    ) == []


def test_competitor_subgraph_rejects_cycle():
    subgraph = load_document(SUBGRAPH_PATH)
    mutated = deepcopy(subgraph)
    mutated["nodes"]["discovery"]["depends_on"] = ["competitor_verifier"]

    diagnostics = subgraph_semantics(mutated, "subgraph.yaml", build_repository_catalog())

    assert "subgraph_dag_cycle" in rules(diagnostics)


def test_competitor_subgraph_rejects_missing_skill_reference():
    subgraph = load_document(SUBGRAPH_PATH)
    mutated = deepcopy(subgraph)
    mutated["nodes"]["discovery"]["skill"] = "missing-competitor-discovery"

    diagnostics = subgraph_semantics(mutated, "subgraph.yaml", build_repository_catalog())

    assert "missing_skill_reference" in rules(diagnostics)


def test_competitor_subgraph_rejects_clean_core_node_replacement():
    subgraph = load_document(SUBGRAPH_PATH)
    mutated = deepcopy(subgraph)
    replacement = mutated["nodes"].pop("feature_analysis")
    mutated["nodes"]["feature_replacement"] = replacement
    visualization_dependencies = mutated["nodes"]["visualization"]["depends_on"]
    mutated["nodes"]["visualization"]["depends_on"] = [
        "feature_replacement" if dependency == "feature_analysis" else dependency
        for dependency in visualization_dependencies
    ]
    for output_contract in mutated["output_contracts"]:
        if output_contract["producer"] == "feature_analysis":
            output_contract["producer"] = "feature_replacement"

    diagnostics = subgraph_semantics(mutated, "subgraph.yaml", build_repository_catalog())

    assert "missing_subgraph_nodes" in rules(diagnostics)


def test_competitor_subgraph_rejects_implementation_drift():
    subgraph = load_document(SUBGRAPH_PATH)
    mutated = deepcopy(subgraph)
    mutated["nodes"]["deep_dive"]["skill"] = "competitor-analysis"

    diagnostics = subgraph_semantics(mutated, "subgraph.yaml", build_repository_catalog())

    assert any(
        item.rule == "subgraph_node_mapping" and item.path == "$.nodes.deep_dive.skill"
        for item in diagnostics
    )


def test_competitor_subgraph_rejects_unknown_output_producer():
    subgraph = load_document(SUBGRAPH_PATH)
    mutated = deepcopy(subgraph)
    mutated["output_contracts"][0]["producer"] = "missing_producer"

    diagnostics = subgraph_semantics(mutated, "subgraph.yaml", build_repository_catalog())

    assert "output_contract_producer" in rules(diagnostics)


def test_competitor_verification_gap_locks_retry_targets_and_return_to(contract_env):
    schemas, registry, _ = contract_env
    verification = {
        "artifact": {
            "id": "ART-competitor-verification-001",
            "type": "competitor_verification",
            "schema_version": "0.1.0",
            "produced_by": {
                "skill": "competitor-verifier",
                "attempt": "ATT-competitor-verification-001",
            },
            "created_at": "2026-08-10T00:00:00Z",
            "supersedes": None,
            "status": "active",
        },
        "verification": {
            "overall": "FAIL",
            "issues": [
                {
                    "code": "COMPETITOR_DATA_INCOMPLETE",
                    "critical": True,
                    "retry_targets": ["deep_dive", "normalizer"],
                    "return_to": "competitor_verifier",
                }
            ],
        },
    }
    assert validate_instance(
        verification,
        "verification.schema.json",
        "competitor-verification.yaml",
        schemas,
        registry,
    ) == []

    missing_retry_targets = deepcopy(verification)
    del missing_retry_targets["verification"]["issues"][0]["retry_targets"]
    assert validate_instance(
        missing_retry_targets,
        "verification.schema.json",
        "competitor-verification.yaml",
        schemas,
        registry,
    )

    wrong_return = deepcopy(verification)
    wrong_return["verification"]["issues"][0]["return_to"] = "visualization"
    assert validate_instance(
        wrong_return,
        "verification.schema.json",
        "competitor-verification.yaml",
        schemas,
        registry,
    )


@pytest.mark.parametrize("filename", sorted(TEMPLATE_CONTRACTS))
def test_template_front_matter_and_required_sections(filename):
    expected = TEMPLATE_CONTRACTS[filename]
    text = (ROOT / "templates" / filename).read_text(encoding="utf-8")
    prefix, front_matter_text, body = text.split("---", 2)
    front_matter = yaml.safe_load(front_matter_text)
    template = front_matter["template"]

    assert prefix == ""
    assert template == {
        "id": filename.removesuffix(".md"),
        "version": "0.1.0",
        "artifact_type": expected["artifact_type"],
    }
    headings = {
        line.removeprefix("## ")
        for line in body.splitlines()
        if line.startswith("## ")
    }
    assert expected["sections"] <= headings
