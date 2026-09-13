from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

from scripts.validate_contracts import load_schemas, validate_instance
from skillgraph_runtime.errors import RuntimeContractError
from skillgraph_runtime.scoring import (
    IndependentScoreVerifier,
    ScoreVerification,
    VerifiedJudgment,
    aggregate_transparent_scores,
    load_profile_rubric,
    validate_dimension_judgment,
)


ROOT = Path(__file__).resolve().parents[2]
BUNDLE = ROOT / "contracts" / "0.3.2"


def report_projection() -> dict:
    return {
        "artifact": {"type": "report_projection", "schema_version": "0.3.2"},
        "fact_groups": [
            {
                "citation_source_ids": ["SRC-001", "SRC-002"],
                "facts": [
                    {
                        "claim_refs": ["CL-001"],
                        "evidence_refs": ["EV-001", "EV-002"],
                        "source_refs": ["SRC-001"],
                    },
                    {
                        "claim_refs": ["CL-002"],
                        "evidence_refs": ["EV-003"],
                        "source_refs": ["SRC-002"],
                    },
                ]
            }
        ],
        "citation_closure": {
            "claim_ids": ["CL-001", "CL-002"],
            "evidence_ids": ["EV-001", "EV-002", "EV-003"],
            "source_ids": ["SRC-001", "SRC-002"],
        },
    }


def claim_category_index() -> dict[str, str]:
    """System-owned view derived from validated Claim records."""

    return {"CL-001": "product", "CL-002": "market"}


def proposal(dimension_id: str, *, competitor_id: str = "cmp_alpha", score: int | None = 8) -> dict:
    claim_ref, evidence_ref = ("CL-002", "EV-003") if dimension_id == "ecosystem_maturity" else ("CL-001", "EV-001")
    return {
        "competitor_id": competitor_id,
        "rubric_ref": "rubrics/developer-tool-scoring.yaml",
        "rubric_version": "1.0.0",
        "dimension_id": dimension_id,
        "judgment_status": "SCORED" if score is not None else "UNRESOLVED",
        "score": score,
        "claim_refs": [claim_ref] if score is not None else [],
        "evidence_refs": [evidence_ref] if score is not None else [],
        "rationale": "Supported by the immutable report projection." if score is not None else "Evidence remains unresolved.",
    }


def accepted_record(
    dimension_id: str,
    *,
    competitor_id: str = "cmp_alpha",
    score: int | None = 8,
    index: int = 1,
) -> VerifiedJudgment:
    rubric = load_profile_rubric(BUNDLE, "developer_tool@0.3.2")
    raw = proposal(dimension_id, competitor_id=competitor_id, score=score)
    judgment_ref = f"ART-JUDGMENT-{competitor_id.upper().replace('_', '-')}-{index}@1"
    verification = IndependentScoreVerifier().verify(
        judgment_ref,
        raw,
        report_projection(),
        rubric,
        claim_category_index=claim_category_index(),
    )
    assert verification.result == "ACCEPT"
    assert verification.accepted_judgment is not None
    return VerifiedJudgment(
        judgment_ref=judgment_ref,
        verification_ref=f"ART-VERIFY-{competitor_id.upper().replace('_', '-')}-{index}@1",
        judgment=verification.accepted_judgment,
        verification=verification,
    )


@pytest.mark.parametrize(
    ("profile_id", "rubric_ref", "first_dimension"),
    [
        ("developer_tool", "rubrics/developer-tool-scoring.yaml", "workflow_fit"),
        ("ai_agent_product", "rubrics/ai-agent-product-scoring.yaml", "agent_capability"),
        ("consumer_app", "rubrics/consumer-app-scoring.yaml", "user_experience"),
        ("b2b_saas", "rubrics/b2b-saas-scoring.yaml", "workflow_fit"),
    ],
)
def test_loads_only_the_profile_locked_equal_weight_rubric(profile_id: str, rubric_ref: str, first_dimension: str):
    rubric = load_profile_rubric(BUNDLE, profile_id)

    assert rubric.profile_ref == f"{profile_id}@0.3.2"
    assert rubric.rubric_ref == rubric_ref
    assert rubric.rubric_version == "1.0.0"
    assert rubric.dimension_ids[0] == first_dimension
    assert rubric.configured_weights == {dimension_id: 0.2 for dimension_id in rubric.dimension_ids}
    assert rubric.content_hash.startswith("sha256:")
    assert len(rubric.content_hash) == 71


@pytest.mark.parametrize("profile", ["developer_tool@0.3.1", "unknown", "../developer_tool"])
def test_profile_loader_fails_closed_on_cross_version_or_unknown_selection(profile: str):
    with pytest.raises(RuntimeContractError) as captured:
        load_profile_rubric(BUNDLE, profile)

    assert captured.value.rule == "scoring_profile"


def test_validates_a_bounded_scored_and_unresolved_judgment():
    rubric = load_profile_rubric(BUNDLE, "developer_tool")

    scored = validate_dimension_judgment(proposal("workflow_fit"), report_projection(), rubric, claim_category_index())
    unresolved = validate_dimension_judgment(proposal("ecosystem_maturity", score=None), report_projection(), rubric, claim_category_index())

    assert scored.score == 8
    assert scored.claim_refs == ("CL-001",)
    assert scored.evidence_refs == ("EV-001",)
    assert unresolved.judgment_status == "UNRESOLVED"
    assert unresolved.score is None
    assert unresolved.claim_refs == ()


@pytest.mark.parametrize(
    ("change", "rule"),
    [
        ({"score": 7.5}, "scoring_score_range"),
        ({"score": True}, "scoring_score_range"),
        ({"score": 11}, "scoring_score_range"),
        ({"dimension_id": "not_in_rubric"}, "scoring_dimension_membership"),
        ({"rubric_version": "1.0.1"}, "scoring_rubric_version"),
        ({"claim_refs": ["CL-OUTSIDE"]}, "scoring_claim_closure"),
        ({"evidence_refs": ["EV-003"]}, "scoring_provenance_link"),
        ({"candidate_ranking_score": 99}, "scoring_judge_authority"),
        ({"final_score": 10}, "scoring_judge_authority"),
        ({"artifact": {"id": "ART-ILLEGAL"}}, "scoring_judge_authority"),
    ],
)
def test_judge_proposal_fails_closed_on_invalid_score_scope_or_authority(change: dict, rule: str):
    rubric = load_profile_rubric(BUNDLE, "developer_tool")
    raw = {**proposal("workflow_fit"), **change}

    with pytest.raises(RuntimeContractError) as captured:
        validate_dimension_judgment(raw, report_projection(), rubric, claim_category_index())

    assert captured.value.rule == rule


def test_projection_closure_must_be_exact_before_any_judgment_is_accepted():
    rubric = load_profile_rubric(BUNDLE, "developer_tool")
    projection = report_projection()
    projection["citation_closure"]["evidence_ids"].append("EV-DANGLING")

    with pytest.raises(RuntimeContractError) as captured:
        validate_dimension_judgment(proposal("workflow_fit"), projection, rubric, claim_category_index())

    assert captured.value.rule == "scoring_projection_closure"


def test_projection_group_citations_must_match_the_fact_sources():
    rubric = load_profile_rubric(BUNDLE, "developer_tool")
    projection = report_projection()
    projection["fact_groups"][0]["citation_source_ids"] = ["SRC-001"]

    with pytest.raises(RuntimeContractError) as captured:
        validate_dimension_judgment(proposal("workflow_fit"), projection, rubric, claim_category_index())

    assert captured.value.rule == "scoring_projection_closure"


def test_independent_verifier_revalidates_raw_judge_output_and_routes_retry_exhaustion():
    rubric = load_profile_rubric(BUNDLE, "developer_tool")
    verifier = IndependentScoreVerifier()
    invalid = {**proposal("workflow_fit"), "score": 10.5}

    retry = verifier.verify("ART-JUDGMENT-001@1", invalid, report_projection(), rubric, claim_category_index=claim_category_index())
    exhausted = verifier.verify(
        "ART-JUDGMENT-001@1",
        invalid,
        report_projection(),
        rubric,
        claim_category_index=claim_category_index(),
        retry_exhausted=True,
    )

    assert retry.result == "RETRY"
    assert retry.next_action == "RETRY_NODE"
    assert retry.retry_exhausted is False
    assert retry.accepted_judgment is None
    assert retry.issues[0].startswith("scoring_score_range:")
    assert exhausted.result == "REJECT"
    assert exhausted.next_action == "OPEN_RESEARCH_GAP"
    assert exhausted.retry_exhausted is True


def test_verifier_role_must_be_independent_from_the_judge():
    with pytest.raises(RuntimeContractError) as captured:
        IndependentScoreVerifier(judge_role="same-role", verifier_role="same-role")

    assert captured.value.code == "SECURITY_POLICY_VIOLATION"
    assert captured.value.rule == "scoring_role_independence"


def test_rejects_closed_claim_when_its_category_is_outside_the_dimension_allowlist():
    rubric = load_profile_rubric(BUNDLE, "developer_tool")
    raw = {
        **proposal("workflow_fit"),
        "claim_refs": ["CL-002"],
        "evidence_refs": ["EV-003"],
    }

    with pytest.raises(RuntimeContractError) as captured:
        validate_dimension_judgment(raw, report_projection(), rubric, claim_category_index())

    assert captured.value.code == "SECURITY_POLICY_VIOLATION"
    assert captured.value.rule == "scoring_claim_category_scope"


@pytest.mark.parametrize(
    ("categories", "rule"),
    [
        ({"CL-002": "market"}, "scoring_claim_category"),
        ({"CL-001": "unknown", "CL-002": "market"}, "scoring_claim_category"),
        (None, "scoring_claim_category_index"),
    ],
)
def test_rejects_missing_unknown_or_absent_system_owned_claim_category_index(categories, rule: str):
    rubric = load_profile_rubric(BUNDLE, "developer_tool")

    with pytest.raises(RuntimeContractError) as captured:
        validate_dimension_judgment(proposal("workflow_fit"), report_projection(), rubric, categories)

    assert captured.value.rule == rule


def test_independent_verifier_repeats_claim_category_scope_validation():
    rubric = load_profile_rubric(BUNDLE, "developer_tool")
    verifier = IndependentScoreVerifier()
    raw = {
        **proposal("workflow_fit"),
        "claim_refs": ["CL-002"],
        "evidence_refs": ["EV-003"],
    }

    decision = verifier.verify(
        "ART-JUDGMENT-001@1",
        raw,
        report_projection(),
        rubric,
        claim_category_index=claim_category_index(),
    )

    assert decision.result == "RETRY"
    assert decision.next_action == "RETRY_NODE"
    assert decision.accepted_judgment is None
    assert decision.issues[0].startswith("scoring_claim_category_scope:")


def test_aggregates_four_of_five_dimensions_with_renormalized_weights_and_contract_shape():
    rubric = load_profile_rubric(BUNDLE, "developer_tool")
    records = tuple(
        accepted_record(dimension_id, score=score, index=index)
        for index, (dimension_id, score) in enumerate(zip(rubric.dimension_ids[:4], (8, 7, 6, 9)), start=1)
    )

    outcome = aggregate_transparent_scores(rubric, ["cmp_alpha"], "ART-RANKING-001@1", records)[0]

    assert outcome.status == "PARTIAL"
    assert outcome.coverage == 0.8
    assert dict(outcome.effective_weights) == {dimension_id: 0.25 for dimension_id in rubric.dimension_ids[:4]}
    assert outcome.missing_dimension_ids == ("ecosystem_maturity",)
    assert outcome.final_score == 7.5
    assert outcome.rank == 1
    assert outcome.tie_status == "UNIQUE"
    assert outcome.candidate_ranking_ref == "ART-RANKING-001@1"

    document = {
        "artifact": {
            "id": "ART-TRANSPARENT-SCORE-TEST",
            "type": "transparent_score",
            "schema_version": "0.3.2",
            "version": 1,
            "produced_by": {"skill": "competitor-scoring", "attempt": "ATT-SCORE-TEST"},
            "created_at": "2026-09-12T00:00:00Z",
            "supersedes": None,
            "status": "active",
        },
        **outcome.to_document_fields(),
    }
    schemas, registry = load_schemas(BUNDLE / "schemas")
    assert validate_instance(document, "competitor.schema.json#/$defs/transparent_score", "generated-score.yaml", schemas, registry) == []


def test_below_eighty_percent_emits_no_legal_score_or_rank():
    rubric = load_profile_rubric(BUNDLE, "developer_tool")
    records = tuple(accepted_record(dimension_id, index=index) for index, dimension_id in enumerate(rubric.dimension_ids[:3], start=1))

    outcome = aggregate_transparent_scores(rubric, ["cmp_alpha"], "ART-RANKING-001@1", records)[0]

    assert outcome.coverage == 0.6
    assert outcome.status == "NOT_PERFORMED"
    assert outcome.final_score is None
    assert outcome.rank is None
    assert outcome.tie_status == "NOT_RANKED"
    with pytest.raises(RuntimeContractError) as captured:
        outcome.to_document_fields()
    assert captured.value.rule == "scoring_coverage_threshold"


def test_ranking_uses_score_then_coverage_and_equal_pairs_share_rank():
    rubric = load_profile_rubric(BUNDLE, "developer_tool")
    records: list[VerifiedJudgment] = []
    for competitor_id, dimension_count in (("cmp_full_a", 5), ("cmp_partial", 4), ("cmp_full_b", 5)):
        records.extend(
            accepted_record(dimension_id, competitor_id=competitor_id, score=8, index=index)
            for index, dimension_id in enumerate(rubric.dimension_ids[:dimension_count], start=1)
        )

    outcomes = aggregate_transparent_scores(
        rubric,
        ["cmp_partial", "cmp_full_b", "cmp_full_a"],
        "ART-RANKING-001@1",
        records,
    )
    by_id = {item.competitor_id: item for item in outcomes}

    assert by_id["cmp_full_a"].rank == 1
    assert by_id["cmp_full_b"].rank == 1
    assert by_id["cmp_full_a"].tie_status == "TIED"
    assert by_id["cmp_full_b"].tie_status == "TIED"
    assert by_id["cmp_partial"].rank == 3
    assert by_id["cmp_partial"].tie_status == "UNIQUE"


def test_aggregator_rejects_unverified_or_mismatched_records_and_outside_candidates():
    rubric = load_profile_rubric(BUNDLE, "developer_tool")
    record = accepted_record("workflow_fit")
    rejected = replace(record.verification, result="REJECT", issues=("semantic disagreement",), next_action="RETRY_NODE", accepted_judgment=None)

    with pytest.raises(RuntimeContractError) as unverified:
        aggregate_transparent_scores(rubric, ["cmp_alpha"], "ART-RANKING-001@1", [replace(record, verification=rejected)])
    assert unverified.value.rule == "scoring_verification_required"

    with pytest.raises(RuntimeContractError) as outside:
        aggregate_transparent_scores(rubric, ["cmp_other"], "ART-RANKING-001@1", [record])
    assert outside.value.rule == "scoring_candidate_separation"

    mismatched = replace(record.verification, judgment_ref="ART-JUDGMENT-DIFFERENT@1")
    with pytest.raises(RuntimeContractError) as binding:
        aggregate_transparent_scores(rubric, ["cmp_alpha"], "ART-RANKING-001@1", [replace(record, verification=mismatched)])
    assert binding.value.rule == "scoring_verification_binding"


def test_aggregator_revalidates_verified_score_shape_and_reference_uniqueness():
    rubric = load_profile_rubric(BUNDLE, "developer_tool")
    first = accepted_record("workflow_fit", index=1)
    second = accepted_record("developer_experience", index=2)

    malformed_judgment = replace(first.judgment, score=99)
    forged_acceptance = replace(first.verification, accepted_judgment=malformed_judgment)
    with pytest.raises(RuntimeContractError) as malformed:
        aggregate_transparent_scores(
            rubric,
            ["cmp_alpha"],
            "ART-RANKING-001@1",
            [replace(first, judgment=malformed_judgment, verification=forged_acceptance)],
        )
    assert malformed.value.rule == "scoring_verified_judgment"

    duplicate_ref = replace(second, judgment_ref=first.judgment_ref, verification=replace(second.verification, judgment_ref=first.judgment_ref))
    with pytest.raises(RuntimeContractError) as duplicate:
        aggregate_transparent_scores(rubric, ["cmp_alpha"], "ART-RANKING-001@1", [first, duplicate_ref])
    assert duplicate.value.rule == "scoring_duplicate_ref"

    forbidden_category = replace(first.judgment, claim_categories=(("CL-001", "market"),))
    forged_category_acceptance = replace(first.verification, accepted_judgment=forbidden_category)
    with pytest.raises(RuntimeContractError) as category:
        aggregate_transparent_scores(
            rubric,
            ["cmp_alpha"],
            "ART-RANKING-001@1",
            [replace(first, judgment=forbidden_category, verification=forged_category_acceptance)],
        )
    assert category.value.rule == "scoring_claim_category_scope"


def test_accepted_verification_shape_matches_the_staged_contract():
    rubric = load_profile_rubric(BUNDLE, "developer_tool")
    decision = IndependentScoreVerifier().verify(
        "ART-JUDGMENT-001@1",
        proposal("workflow_fit"),
        report_projection(),
        rubric,
        claim_category_index=claim_category_index(),
    )
    document = {
        "artifact": {
            "id": "ART-SCORE-VERIFY-TEST",
            "type": "score_verification",
            "schema_version": "0.3.2",
            "version": 1,
            "produced_by": {"skill": "competitor-score-verifier", "attempt": "ATT-SCORE-VERIFY-TEST"},
            "created_at": "2026-09-12T00:00:00Z",
            "supersedes": None,
            "status": "active",
        },
        **decision.to_document_fields(),
    }
    schemas, registry = load_schemas(BUNDLE / "schemas")
    assert validate_instance(document, "competitor.schema.json#/$defs/score_verification", "generated-verification.yaml", schemas, registry) == []
