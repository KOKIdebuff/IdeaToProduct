from __future__ import annotations

from copy import deepcopy

import pytest

from scripts.contract_bundles import ContractBundle, ContractResolutionError, load_bundle_context, load_version_registry, resolve_contract_bundle
from scripts.validate_contracts import (
    ROOT,
    load_document,
    load_schemas,
    report_successor_diagnostics,
    transparent_score_collection_diagnostics,
    validate_bundle,
    validate_instance,
)


def _v032_context():
    root = ROOT / "contracts" / "0.3.2"
    return load_bundle_context(ContractBundle("0.3.2", root, "staged", "audit"))


def test_v032_report_pipeline_bundle_is_closed_without_registry_promotion():
    registry = load_version_registry()
    assert "0.3.2" not in registry.versions
    diagnostics, checked = validate_bundle(_v032_context(), version_registry=registry)
    assert diagnostics == []
    assert checked == 209
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


def test_v032_report_successors_preserve_unowned_sections_and_lineage():
    root = _v032_context().bundle.root / "fixtures" / "valid"
    initial = load_document(root / "competitor-report.yaml")
    score = load_document(root / "competitor-report-score-successor.yaml")
    verification = load_document(root / "competitor-report-verification-successor.yaml")

    assert report_successor_diagnostics(initial, "initial.yaml") == []
    assert report_successor_diagnostics(score, "score.yaml", initial) == []
    assert report_successor_diagnostics(verification, "verification.yaml", score) == []
    for base, successor, version in ((None, initial, 1), (initial, score, 2), (score, verification, 3)):
        bundle_root = f"artifacts/02-research/competitors/report-bundles/ART-COMPETITOR-REPORT-001@{version}/"
        assert successor["report_root_ref"] == bundle_root + "competitor-report.html"
        assert successor["inventory_ref"] == bundle_root + "inventory.json"
        if base is not None:
            assert successor["report_root_ref"] != base["report_root_ref"]
            assert successor["inventory_ref"] != base["inventory_ref"]

    changed_verification = deepcopy(score)
    changed_verification["verification"] = {"status": "PASS", "verification_ref": "ART-COMPETITOR-VERIFICATION-001@1"}
    assert "report_section_ownership" in {item.rule for item in report_successor_diagnostics(changed_verification, "score.yaml", initial)}

    stale = deepcopy(score)
    stale["base_report_ref"] = stale["artifact"]["supersedes"] = "ART-COMPETITOR-REPORT-001@9"
    assert "report_successor_base" in {item.rule for item in report_successor_diagnostics(stale, "score.yaml", initial)}


@pytest.mark.parametrize(
    ("fixture_name", "expected_rule"),
    [
        ("report-successor-reused-root.yaml", "report_bundle_reuse"),
        ("report-successor-reused-inventory.yaml", "report_bundle_reuse"),
        ("report-successor-wrong-bundle-version.yaml", "report_bundle_identity"),
        ("report-successor-outside-bundle.yaml", "report_bundle_identity"),
        ("report-successor-mixed-bundles.yaml", "report_bundle_identity"),
    ],
)
def test_v032_successor_rejects_wrong_or_reused_bundle_identity(fixture_name, expected_rule):
    root = _v032_context().bundle.root / "fixtures"
    base = load_document(root / "valid" / "competitor-report.yaml")
    successor = load_document(root / "invalid" / fixture_name)
    rules = {item.rule for item in report_successor_diagnostics(successor, fixture_name, base)}
    assert expected_rule in rules


@pytest.mark.parametrize(
    ("section", "status", "reference_field", "reference"),
    [
        ("verification", "PENDING", "verification_ref", "ART-COMPETITOR-VERIFICATION-001@1"),
        ("verification", "PASS", "verification_ref", None),
        ("verification", "PARTIAL", "verification_ref", None),
        ("verification", "FAIL", "verification_ref", None),
        ("scoring", "NOT_PERFORMED", "score_collection_ref", "ART-TRANSPARENT-SCORE-COLLECTION-001@1"),
        ("scoring", "AVAILABLE", "score_collection_ref", None),
    ],
)
def test_v032_report_rejects_status_ref_mismatches(section, status, reference_field, reference):
    context = _v032_context()
    schemas, registry = load_schemas(context.schema_dir)
    report = load_document(context.bundle.root / "fixtures" / "valid" / "competitor-report.yaml")
    report[section] = {"status": status, reference_field: reference}
    assert validate_instance(report, "competitor.schema.json#/$defs/competitor_report", "report.yaml", schemas, registry)


def test_v032_multi_competitor_score_collection_is_deterministic_and_complete():
    root = _v032_context().bundle.root / "fixtures" / "valid"
    collection = load_document(root / "transparent-score-collection.yaml")
    ranking = load_document(root / "competitor-ranking.yaml")
    scores = [load_document(root / name) for name in ("transparent-score.yaml", "transparent-score-002.yaml", "transparent-score-003.yaml")]
    judgments = [load_document(root / name) for name in ("dimension-judgment.yaml", "dimension-judgment-002.yaml", "dimension-judgment-003.yaml")]
    verifications = [load_document(root / name) for name in ("score-verification.yaml", "score-verification-002.yaml", "score-verification-003.yaml")]

    assert transparent_score_collection_diagnostics(collection, scores, ranking, "collection.yaml", judgments, verifications) == []
    by_verification_ref = {f"{item['artifact']['id']}@{item['artifact']['version']}": item for item in verifications}
    for score in scores:
        for verification_ref in score["score_verification_refs"]:
            assert by_verification_ref[verification_ref]["result"] == "ACCEPT"
            assert by_verification_ref[verification_ref]["next_action"] == "AGGREGATE"

    duplicate = deepcopy(collection)
    duplicate["score_refs"][2]["competitor_id"] = "cmp_001"
    assert "score_collection_duplicate_competitor" in {item.rule for item in transparent_score_collection_diagnostics(duplicate, scores, ranking, "collection.yaml", judgments, verifications)}

    wrong_order = deepcopy(collection)
    wrong_order["score_refs"][0], wrong_order["score_refs"][1] = wrong_order["score_refs"][1], wrong_order["score_refs"][0]
    assert "score_collection_order" in {item.rule for item in transparent_score_collection_diagnostics(wrong_order, scores, ranking, "collection.yaml", judgments, verifications)}

    for field, replacement in (
        ("candidate_ranking_ref", "ART-RANKING-OTHER@1"),
        ("profile_ref", "b2b_saas@0.3.2"),
        ("rubric_ref", "rubrics/b2b-saas-scoring.yaml"),
        ("rubric_version", "2.0.0"),
    ):
        mismatch = deepcopy(collection)
        mismatch[field] = replacement
        assert "score_collection_identity" in {item.rule for item in transparent_score_collection_diagnostics(mismatch, scores, ranking, "collection.yaml", judgments, verifications)}


@pytest.mark.parametrize(
    ("fixture_name", "expected_rule"),
    [
        ("score-collection-dangling-verification.yaml", "score_collection_verification_ref"),
        ("score-collection-rejected-verification.yaml", "score_collection_verification_accept"),
        ("score-collection-retry-verification.yaml", "score_collection_verification_accept"),
        ("score-collection-mismatched-verification.yaml", "score_collection_verification_binding"),
        ("score-collection-inactive-verification.yaml", "score_collection_verification_ref"),
    ],
)
def test_v032_score_collection_rejects_unaccepted_or_misbound_verification(fixture_name, expected_rule):
    root = _v032_context().bundle.root / "fixtures"
    manifest = load_document(root / "manifest.json")
    spec = next(case for case in manifest["cases"] if case["path"].endswith(fixture_name))
    collection = load_document(root.parent / spec["path"])
    ranking = load_document(root.parent / spec["candidate_ranking_fixture"])
    scores = [load_document(root.parent / path) for path in spec["score_fixtures"]]
    judgments = [load_document(root.parent / path) for path in spec["judgment_fixtures"]]
    verifications = [load_document(root.parent / path) for path in spec["verification_fixtures"]]
    diagnostics = transparent_score_collection_diagnostics(collection, scores, ranking, fixture_name, judgments, verifications)
    assert expected_rule in {item.rule for item in diagnostics}


def test_v032_current_manifest_uses_one_score_collection_entry():
    manifest = load_document(_v032_context().bundle.root / "fixtures" / "valid" / "artifact-manifest.json")
    current = manifest["current_artifacts"]
    assert current["transparent_score_collection"]["artifact_ref"] == "ART-TRANSPARENT-SCORE-COLLECTION-001@1"
    assert "transparent_score" not in current
