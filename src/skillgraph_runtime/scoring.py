"""Pure Transparent Scoring core for the staged 0.3.2 contract.

This module deliberately has no persistence or Runtime integration.  Semantic
judges submit bounded dimension proposals, an independent verifier validates
them again, and the deterministic aggregator consumes only accepted results.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from decimal import Decimal
import hashlib
import json
from pathlib import Path
import re
from typing import Any, Mapping, Sequence

import yaml

from .errors import RuntimeContractError


CONTRACT_VERSION = "0.3.2"
RUBRIC_VERSION = "1.0.0"
_PROFILE_RUBRICS = {
    "developer_tool": "rubrics/developer-tool-scoring.yaml",
    "ai_agent_product": "rubrics/ai-agent-product-scoring.yaml",
    "consumer_app": "rubrics/consumer-app-scoring.yaml",
    "b2b_saas": "rubrics/b2b-saas-scoring.yaml",
}
_PROFILE_FILES = {
    profile_id: f"profiles/{profile_id.replace('_', '-')}.yaml"
    for profile_id in _PROFILE_RUBRICS
}
_CLAIM_CATEGORIES = {"user", "competitor", "market", "technology", "product"}
_COMPETITOR_ID = re.compile(r"^cmp_[a-z0-9][a-z0-9_-]*$")
_ARTIFACT_REF = re.compile(r"^\S+$")
_PROPOSAL_FIELDS = {
    "competitor_id",
    "rubric_ref",
    "rubric_version",
    "dimension_id",
    "judgment_status",
    "score",
    "claim_refs",
    "evidence_refs",
    "rationale",
}


@dataclass(frozen=True)
class RubricDimension:
    id: str
    definition: str
    weight: Decimal
    allowed_claim_categories: tuple[str, ...]
    minimum_evidence_count: int


@dataclass(frozen=True)
class ScoringRubric:
    profile_id: str
    profile_ref: str
    rubric_ref: str
    rubric_id: str
    rubric_version: str
    dimensions: tuple[RubricDimension, ...]
    minimum_weight_coverage: Decimal
    content_hash: str

    @property
    def dimension_ids(self) -> tuple[str, ...]:
        return tuple(item.id for item in self.dimensions)

    @property
    def configured_weights(self) -> dict[str, float]:
        return {item.id: float(item.weight) for item in self.dimensions}

    def dimension(self, dimension_id: str) -> RubricDimension:
        for item in self.dimensions:
            if item.id == dimension_id:
                return item
        raise RuntimeContractError(
            "Dimension is not defined by the selected Rubric",
            code="SCHEMA_INVALID",
            rule="scoring_dimension_membership",
            details={"dimension_id": dimension_id},
        )


@dataclass(frozen=True)
class DimensionJudgment:
    competitor_id: str
    rubric_ref: str
    rubric_version: str
    dimension_id: str
    judgment_status: str
    score: int | None
    claim_refs: tuple[str, ...]
    evidence_refs: tuple[str, ...]
    rationale: str
    # Kernel-owned validation metadata.  It is intentionally excluded from the
    # public Artifact shape; the Contract records Claim IDs, while this value
    # lets the deterministic aggregator reject a forged ACCEPT wrapper that
    # claims a Rubric-forbidden category.
    claim_categories: tuple[tuple[str, str], ...] = ()

    def to_document_fields(self) -> dict[str, Any]:
        return {
            "competitor_id": self.competitor_id,
            "rubric_ref": self.rubric_ref,
            "rubric_version": self.rubric_version,
            "dimension_id": self.dimension_id,
            "judgment_status": self.judgment_status,
            "score": self.score,
            "claim_refs": list(self.claim_refs),
            "evidence_refs": list(self.evidence_refs),
            "rationale": self.rationale,
        }


@dataclass(frozen=True)
class ScoreVerification:
    judgment_ref: str
    result: str
    issues: tuple[str, ...]
    retry_exhausted: bool
    next_action: str
    accepted_judgment: DimensionJudgment | None = None

    def to_document_fields(self) -> dict[str, Any]:
        return {
            "judgment_ref": self.judgment_ref,
            "result": self.result,
            "issues": list(self.issues),
            "retry_exhausted": self.retry_exhausted,
            "next_action": self.next_action,
        }


@dataclass(frozen=True)
class VerifiedJudgment:
    judgment_ref: str
    verification_ref: str
    judgment: DimensionJudgment
    verification: ScoreVerification


@dataclass(frozen=True)
class TransparentScoreOutcome:
    competitor_id: str
    profile_ref: str
    rubric_ref: str
    rubric_version: str
    configured_weights: tuple[tuple[str, float], ...]
    effective_weights: tuple[tuple[str, float], ...]
    coverage: float
    status: str
    missing_dimension_ids: tuple[str, ...]
    dimension_judgment_refs: tuple[str, ...]
    score_verification_refs: tuple[str, ...]
    final_score: int | float | None
    rank: int | None
    tie_status: str
    candidate_ranking_ref: str

    def to_document_fields(self) -> dict[str, Any]:
        """Return fields for a schema-valid Transparent Score Artifact.

        The 0.3.2 schema requires four or five effective weights.  Therefore a
        below-threshold result is an aggregation outcome, not a legal Artifact
        proposal, and must remain unpersisted.
        """

        if self.final_score is None:
            raise RuntimeContractError(
                "Weight coverage is below the Transparent Score publication threshold",
                code="INSUFFICIENT_EVIDENCE",
                rule="scoring_coverage_threshold",
                details={"coverage": self.coverage},
            )
        return {
            "competitor_id": self.competitor_id,
            "profile_ref": self.profile_ref,
            "rubric_ref": self.rubric_ref,
            "rubric_version": self.rubric_version,
            "configured_weights": dict(self.configured_weights),
            "effective_weights": dict(self.effective_weights),
            "coverage": self.coverage,
            "status": self.status,
            "missing_dimension_ids": list(self.missing_dimension_ids),
            "dimension_judgment_refs": list(self.dimension_judgment_refs),
            "score_verification_refs": list(self.score_verification_refs),
            "final_score": self.final_score,
            "rank": self.rank,
            "tie_status": self.tie_status,
            "candidate_ranking_ref": self.candidate_ranking_ref,
        }


def load_profile_rubric(bundle_root: Path, profile: str) -> ScoringRubric:
    """Load the only Rubric permitted for one staged 0.3.2 Profile."""

    profile_id = profile.split("@", 1)[0]
    expected_profile_ref = f"{profile_id}@{CONTRACT_VERSION}"
    if profile not in {profile_id, expected_profile_ref} or profile_id not in _PROFILE_RUBRICS:
        raise RuntimeContractError("Unsupported Profile/Rubric selection", code="SCHEMA_VERSION_UNSUPPORTED", rule="scoring_profile")

    root = Path(bundle_root).resolve()
    profile_document = _load_fixed_yaml(root, _PROFILE_FILES[profile_id], "scoring_profile")
    rubric_ref = _PROFILE_RUBRICS[profile_id]
    rubric_document = _load_fixed_yaml(root, rubric_ref, "scoring_rubric")

    profile_header = _require_mapping(profile_document.get("profile"), "scoring_profile")
    if profile_header != {"id": profile_id, "version": CONTRACT_VERSION}:
        raise RuntimeContractError("Profile identity/version does not match the staged contract", code="SCHEMA_VERSION_UNSUPPORTED", rule="scoring_profile_version")
    if profile_document.get("scoring_rubric_ref") != rubric_ref:
        raise RuntimeContractError("Profile references a different Scoring Rubric", code="SCHEMA_VERSION_UNSUPPORTED", rule="scoring_rubric_reference")

    header = _require_mapping(rubric_document.get("rubric"), "scoring_rubric")
    expected_header = {
        "id": f"{profile_id}_scoring",
        "version": RUBRIC_VERSION,
        "profile_ref": expected_profile_ref,
        "integer_only": True,
        "minimum": 1,
        "maximum": 10,
        "aggregation": "weighted_arithmetic_mean",
        "minimum_weight_coverage": 0.8,
        "missing_evidence": "renormalize_available_weights_partial",
        "tie_break": "evidence_coverage_then_shared_rank",
    }
    for key, expected in expected_header.items():
        if header.get(key) != expected or type(header.get(key)) is not type(expected):
            raise RuntimeContractError("Scoring Rubric policy/version drifted", code="SCHEMA_VERSION_UNSUPPORTED", rule="scoring_rubric_version", details={"field": key})
    if not isinstance(header.get("change_rationale"), str) or not header["change_rationale"].strip():
        raise RuntimeContractError("Scoring Rubric requires change rationale", code="SCHEMA_INVALID", rule="scoring_rubric_changelog")
    changelog = header.get("changelog")
    if not isinstance(changelog, list) or not any(isinstance(item, Mapping) and item.get("version") == RUBRIC_VERSION for item in changelog):
        raise RuntimeContractError("Scoring Rubric version is absent from its changelog", code="SCHEMA_VERSION_UNSUPPORTED", rule="scoring_rubric_changelog")

    raw_dimensions = rubric_document.get("dimensions")
    if not isinstance(raw_dimensions, list) or len(raw_dimensions) != 5:
        raise RuntimeContractError("Scoring Rubric must define exactly five dimensions", code="SCHEMA_INVALID", rule="scoring_rubric_dimensions")
    dimensions = tuple(_parse_dimension(item) for item in raw_dimensions)
    if len({item.id for item in dimensions}) != len(dimensions):
        raise RuntimeContractError("Scoring Rubric dimension IDs must be unique", code="SCHEMA_INVALID", rule="scoring_rubric_dimensions")
    if any(item.weight != Decimal("0.2") for item in dimensions) or sum((item.weight for item in dimensions), Decimal(0)) != Decimal(1):
        raise RuntimeContractError("Scoring Rubric weights must use the approved equal-weight map", code="SCHEMA_INVALID", rule="scoring_rubric_weights")

    bands = rubric_document.get("score_bands")
    actual_bands = tuple((item.get("minimum"), item.get("maximum")) for item in bands if isinstance(item, Mapping)) if isinstance(bands, list) else ()
    if actual_bands != ((1, 2), (3, 4), (5, 6), (7, 8), (9, 10)):
        raise RuntimeContractError("Scoring Rubric bands must cover integer scores 1 through 10", code="SCHEMA_INVALID", rule="scoring_rubric_bands")

    digest = hashlib.sha256(json.dumps(rubric_document, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")).hexdigest()
    return ScoringRubric(
        profile_id=profile_id,
        profile_ref=expected_profile_ref,
        rubric_ref=rubric_ref,
        rubric_id=str(header["id"]),
        rubric_version=RUBRIC_VERSION,
        dimensions=dimensions,
        minimum_weight_coverage=Decimal("0.8"),
        content_hash=f"sha256:{digest}",
    )


def validate_dimension_judgment(
    proposal: Mapping[str, Any],
    report_projection: Mapping[str, Any],
    rubric: ScoringRubric,
    claim_category_index: Mapping[str, str] | None = None,
) -> DimensionJudgment:
    """Validate a proposal without granting the semantic Judge write authority.

    ``claim_category_index`` must be a read-only view derived from
    system-validated Claim records.  It is deliberately separate from the
    Judge proposal so a provider cannot self-assert an allowed category.
    """

    if not isinstance(proposal, Mapping):
        raise RuntimeContractError("Dimension Judgment proposal must be an object", code="SCHEMA_INVALID", rule="scoring_judgment_shape")
    extra = set(proposal) - _PROPOSAL_FIELDS
    missing = _PROPOSAL_FIELDS - set(proposal)
    if extra or missing:
        code = "SECURITY_POLICY_VIOLATION" if extra else "SCHEMA_INVALID"
        raise RuntimeContractError("Dimension Judgment proposal has forbidden or missing fields", code=code, rule="scoring_judge_authority", details={"extra": sorted(extra), "missing": sorted(missing)})

    competitor_id = proposal["competitor_id"]
    if not isinstance(competitor_id, str) or _COMPETITOR_ID.fullmatch(competitor_id) is None:
        raise RuntimeContractError("Dimension Judgment competitor_id is invalid", code="SCHEMA_INVALID", rule="scoring_competitor")
    if proposal["rubric_ref"] != rubric.rubric_ref or proposal["rubric_version"] != rubric.rubric_version:
        raise RuntimeContractError("Dimension Judgment does not use the selected Rubric version", code="SCHEMA_VERSION_UNSUPPORTED", rule="scoring_rubric_version")
    dimension = rubric.dimension(proposal["dimension_id"])
    status = proposal["judgment_status"]
    score = proposal["score"]
    if status not in {"SCORED", "UNRESOLVED"}:
        raise RuntimeContractError("Dimension Judgment status is invalid", code="SCHEMA_INVALID", rule="scoring_judgment_status")
    if status == "SCORED" and (type(score) is not int or not 1 <= score <= 10):
        raise RuntimeContractError("Scored Dimension Judgment requires an integer from 1 through 10", code="SCHEMA_INVALID", rule="scoring_score_range")
    if status == "UNRESOLVED" and score is not None:
        raise RuntimeContractError("Unresolved Dimension Judgment cannot carry a score", code="SCHEMA_INVALID", rule="scoring_unresolved_score")

    claim_refs = _string_refs(proposal["claim_refs"], "CL-", "scoring_claim_refs")
    evidence_refs = _string_refs(proposal["evidence_refs"], "EV-", "scoring_evidence_refs")
    rationale = proposal["rationale"]
    if not isinstance(rationale, str) or not rationale.strip():
        raise RuntimeContractError("Dimension Judgment requires a rationale", code="SCHEMA_INVALID", rule="scoring_rationale")

    projection_links = _projection_links(report_projection)
    if status == "UNRESOLVED":
        claim_categories = _validated_claim_categories(claim_refs, claim_category_index, dimension)
        if claim_refs or evidence_refs:
            raise RuntimeContractError("Unresolved Dimension Judgment cannot claim supporting provenance", code="SCHEMA_INVALID", rule="scoring_unresolved_provenance")
    else:
        if not claim_refs or len(evidence_refs) < dimension.minimum_evidence_count:
            raise RuntimeContractError("Dimension Judgment has insufficient supporting provenance", code="INSUFFICIENT_EVIDENCE", rule="scoring_minimum_evidence")
        for claim_ref in claim_refs:
            linked = projection_links.get(claim_ref)
            if linked is None:
                raise RuntimeContractError("Dimension Judgment Claim is outside the Projection Closure", code="INSUFFICIENT_EVIDENCE", rule="scoring_claim_closure")
            if not linked.intersection(evidence_refs):
                raise RuntimeContractError("Dimension Judgment Claim has no referenced linked Evidence", code="INSUFFICIENT_EVIDENCE", rule="scoring_provenance_link")
        if any(not any(evidence_ref in linked for linked in (projection_links[claim] for claim in claim_refs)) for evidence_ref in evidence_refs):
            raise RuntimeContractError("Dimension Judgment Evidence is not linked to a referenced Claim", code="INSUFFICIENT_EVIDENCE", rule="scoring_evidence_closure")
        claim_categories = _validated_claim_categories(claim_refs, claim_category_index, dimension)

    return DimensionJudgment(
        competitor_id=competitor_id,
        rubric_ref=rubric.rubric_ref,
        rubric_version=rubric.rubric_version,
        dimension_id=dimension.id,
        judgment_status=status,
        score=score,
        claim_refs=claim_refs,
        evidence_refs=evidence_refs,
        rationale=rationale.strip(),
        claim_categories=claim_categories,
    )


class IndependentScoreVerifier:
    """Re-validate raw Judge output and emit a deterministic decision."""

    def __init__(self, *, judge_role: str = "competitor-scoring", verifier_role: str = "competitor-score-verifier") -> None:
        if not judge_role or not verifier_role or judge_role == verifier_role:
            raise RuntimeContractError("Judge and Score Verifier roles must be independent", code="SECURITY_POLICY_VIOLATION", rule="scoring_role_independence")
        self.judge_role = judge_role
        self.verifier_role = verifier_role

    def verify(
        self,
        judgment_ref: str,
        proposal: Mapping[str, Any] | DimensionJudgment,
        report_projection: Mapping[str, Any],
        rubric: ScoringRubric,
        *,
        claim_category_index: Mapping[str, str] | None = None,
        retry_exhausted: bool = False,
    ) -> ScoreVerification:
        _validate_artifact_ref(judgment_ref, "scoring_judgment_ref")
        raw = proposal.to_document_fields() if isinstance(proposal, DimensionJudgment) else proposal
        try:
            # Repeat category-scope validation using the system-owned index;
            # never trust categories retained on a Judge-created object.
            judgment = validate_dimension_judgment(raw, report_projection, rubric, claim_category_index)
        except RuntimeContractError as error:
            issue = f"{error.rule}: {error}"
            return ScoreVerification(
                judgment_ref=judgment_ref,
                result="REJECT" if retry_exhausted else "RETRY",
                issues=(issue,),
                retry_exhausted=retry_exhausted,
                next_action="OPEN_RESEARCH_GAP" if retry_exhausted else "RETRY_NODE",
            )
        return ScoreVerification(
            judgment_ref=judgment_ref,
            result="ACCEPT",
            issues=(),
            retry_exhausted=False,
            next_action="AGGREGATE",
            accepted_judgment=judgment,
        )


def aggregate_transparent_scores(
    rubric: ScoringRubric,
    candidate_competitor_ids: Sequence[str],
    candidate_ranking_ref: str,
    verified_judgments: Sequence[VerifiedJudgment],
) -> tuple[TransparentScoreOutcome, ...]:
    """Aggregate accepted dimension judgments, then rank eligible competitors."""

    _validate_artifact_ref(candidate_ranking_ref, "scoring_candidate_ranking_ref")
    candidates = tuple(candidate_competitor_ids)
    if not candidates or len(set(candidates)) != len(candidates) or any(not isinstance(item, str) or _COMPETITOR_ID.fullmatch(item) is None for item in candidates):
        raise RuntimeContractError("Candidate competitor IDs must be unique and valid", code="SCHEMA_INVALID", rule="scoring_candidates")

    grouped: dict[str, dict[str, VerifiedJudgment]] = {item: {} for item in candidates}
    judgment_refs: set[str] = set()
    verification_refs: set[str] = set()
    for record in verified_judgments:
        _validate_verified_record(record, rubric)
        if record.judgment_ref in judgment_refs or record.verification_ref in verification_refs:
            raise RuntimeContractError("Scoring Artifact references must be globally unique", code="STATE_VERSION_CONFLICT", rule="scoring_duplicate_ref")
        judgment_refs.add(record.judgment_ref)
        verification_refs.add(record.verification_ref)
        judgment = record.judgment
        if judgment.competitor_id not in grouped:
            raise RuntimeContractError("Verified Judgment competitor is outside Candidate Ranking", code="SECURITY_POLICY_VIOLATION", rule="scoring_candidate_separation")
        existing = grouped[judgment.competitor_id].get(judgment.dimension_id)
        if existing is not None:
            raise RuntimeContractError("Competitor has duplicate verified Dimension Judgments", code="STATE_VERSION_CONFLICT", rule="scoring_duplicate_dimension")
        grouped[judgment.competitor_id][judgment.dimension_id] = record

    outcomes = tuple(_aggregate_competitor(rubric, competitor_id, candidate_ranking_ref, grouped[competitor_id]) for competitor_id in candidates)
    return _rank_outcomes(outcomes)


def _aggregate_competitor(
    rubric: ScoringRubric,
    competitor_id: str,
    candidate_ranking_ref: str,
    records: Mapping[str, VerifiedJudgment],
) -> TransparentScoreOutcome:
    scored = {
        dimension_id: record
        for dimension_id, record in records.items()
        if record.judgment.judgment_status == "SCORED"
    }
    available_weight = sum((rubric.dimension(item).weight for item in scored), Decimal(0))
    missing = tuple(item for item in rubric.dimension_ids if item not in scored)
    effective: tuple[tuple[str, float], ...]
    if available_weight:
        effective = tuple((item, _number(rubric.dimension(item).weight / available_weight)) for item in rubric.dimension_ids if item in scored)
    else:
        effective = ()
    eligible = available_weight >= rubric.minimum_weight_coverage
    final_score: int | float | None = None
    if eligible:
        total = sum((Decimal(record.judgment.score) * rubric.dimension(item).weight for item, record in scored.items()), Decimal(0))
        final_score = _number(total / available_weight)
    all_records = tuple(records[item] for item in rubric.dimension_ids if item in records)
    return TransparentScoreOutcome(
        competitor_id=competitor_id,
        profile_ref=rubric.profile_ref,
        rubric_ref=rubric.rubric_ref,
        rubric_version=rubric.rubric_version,
        configured_weights=tuple(rubric.configured_weights.items()),
        effective_weights=effective,
        coverage=_number(available_weight),
        status="COMPLETE" if available_weight == Decimal(1) else ("PARTIAL" if eligible else "NOT_PERFORMED"),
        missing_dimension_ids=missing,
        dimension_judgment_refs=tuple(record.judgment_ref for record in all_records),
        score_verification_refs=tuple(record.verification_ref for record in all_records),
        final_score=final_score,
        rank=None,
        tie_status="NOT_RANKED",
        candidate_ranking_ref=candidate_ranking_ref,
    )


def _rank_outcomes(outcomes: tuple[TransparentScoreOutcome, ...]) -> tuple[TransparentScoreOutcome, ...]:
    eligible = sorted(
        (item for item in outcomes if item.final_score is not None),
        key=lambda item: (-Decimal(str(item.final_score)), -Decimal(str(item.coverage)), item.competitor_id),
    )
    ranked: dict[str, TransparentScoreOutcome] = {}
    for index, item in enumerate(eligible, start=1):
        peer_key = (item.final_score, item.coverage)
        previous = eligible[index - 2] if index > 1 else None
        rank = ranked[previous.competitor_id].rank if previous is not None and (previous.final_score, previous.coverage) == peer_key else index
        tied = sum(1 for candidate in eligible if (candidate.final_score, candidate.coverage) == peer_key) > 1
        ranked[item.competitor_id] = replace(item, rank=rank, tie_status="TIED" if tied else "UNIQUE")
    return tuple(ranked.get(item.competitor_id, item) for item in outcomes)


def _validate_verified_record(record: VerifiedJudgment, rubric: ScoringRubric) -> None:
    if not isinstance(record, VerifiedJudgment):
        raise RuntimeContractError("Aggregator accepts only independently verified Judgment records", code="SECURITY_POLICY_VIOLATION", rule="scoring_verification_required")
    _validate_artifact_ref(record.judgment_ref, "scoring_judgment_ref")
    _validate_artifact_ref(record.verification_ref, "scoring_verification_ref")
    verification = record.verification
    if verification.result != "ACCEPT" or verification.next_action != "AGGREGATE" or verification.retry_exhausted or verification.issues:
        raise RuntimeContractError("Aggregator accepts only successful independent verification", code="SECURITY_POLICY_VIOLATION", rule="scoring_verification_required")
    if verification.judgment_ref != record.judgment_ref or verification.accepted_judgment != record.judgment:
        raise RuntimeContractError("Verification does not bind the supplied Judgment", code="SECURITY_POLICY_VIOLATION", rule="scoring_verification_binding")
    if record.judgment.rubric_ref != rubric.rubric_ref or record.judgment.rubric_version != rubric.rubric_version:
        raise RuntimeContractError("Verified Judgment uses a different Rubric version", code="SCHEMA_VERSION_UNSUPPORTED", rule="scoring_rubric_version")
    dimension = rubric.dimension(record.judgment.dimension_id)
    judgment = record.judgment
    if not isinstance(judgment.competitor_id, str) or _COMPETITOR_ID.fullmatch(judgment.competitor_id) is None:
        raise RuntimeContractError("Verified Judgment competitor_id is invalid", code="SCHEMA_INVALID", rule="scoring_competitor")
    if judgment.judgment_status == "SCORED":
        if type(judgment.score) is not int or not 1 <= judgment.score <= 10 or not judgment.claim_refs or not judgment.evidence_refs:
            raise RuntimeContractError("Verified scored Judgment is malformed", code="SCHEMA_INVALID", rule="scoring_verified_judgment")
        if tuple(claim for claim, _category in judgment.claim_categories) != judgment.claim_refs:
            raise RuntimeContractError("Verified Judgment has missing or mismatched Claim category metadata", code="SECURITY_POLICY_VIOLATION", rule="scoring_claim_category")
        if any(category not in dimension.allowed_claim_categories for _claim, category in judgment.claim_categories):
            raise RuntimeContractError("Verified Judgment uses a Rubric-forbidden Claim category", code="SECURITY_POLICY_VIOLATION", rule="scoring_claim_category_scope")
    elif judgment.judgment_status == "UNRESOLVED":
        if judgment.score is not None or judgment.claim_refs or judgment.evidence_refs or judgment.claim_categories:
            raise RuntimeContractError("Verified unresolved Judgment is malformed", code="SCHEMA_INVALID", rule="scoring_verified_judgment")
    else:
        raise RuntimeContractError("Verified Judgment status is invalid", code="SCHEMA_INVALID", rule="scoring_verified_judgment")


def _projection_links(report_projection: Mapping[str, Any]) -> dict[str, frozenset[str]]:
    if not isinstance(report_projection, Mapping):
        raise RuntimeContractError("Report Projection must be an object", code="SCHEMA_INVALID", rule="scoring_projection")
    artifact = report_projection.get("artifact")
    if not isinstance(artifact, Mapping) or artifact.get("type") != "report_projection" or artifact.get("schema_version") != CONTRACT_VERSION:
        raise RuntimeContractError("Scoring requires a staged 0.3.2 Report Projection", code="SCHEMA_VERSION_UNSUPPORTED", rule="scoring_projection_version")
    closure = _require_mapping(report_projection.get("citation_closure"), "scoring_projection_closure")
    closure_claims = _string_refs(closure.get("claim_ids"), "CL-", "scoring_projection_closure")
    closure_evidence = _string_refs(closure.get("evidence_ids"), "EV-", "scoring_projection_closure")
    closure_sources = _string_refs(closure.get("source_ids"), "SRC-", "scoring_projection_closure")
    groups = report_projection.get("fact_groups")
    if not isinstance(groups, list) or not groups:
        raise RuntimeContractError("Report Projection has no fact groups", code="SCHEMA_INVALID", rule="scoring_projection_closure")
    links: dict[str, set[str]] = {}
    actual_evidence: set[str] = set()
    actual_sources: set[str] = set()
    for group in groups:
        if not isinstance(group, Mapping) or not isinstance(group.get("facts"), list):
            raise RuntimeContractError("Report Projection fact group is malformed", code="SCHEMA_INVALID", rule="scoring_projection_closure")
        group_sources: set[str] = set()
        for fact in group["facts"]:
            if not isinstance(fact, Mapping):
                raise RuntimeContractError("Report Projection Fact Binding is malformed", code="SCHEMA_INVALID", rule="scoring_projection_closure")
            claims = _string_refs(fact.get("claim_refs"), "CL-", "scoring_projection_closure")
            evidence = _string_refs(fact.get("evidence_refs"), "EV-", "scoring_projection_closure")
            sources = _string_refs(fact.get("source_refs"), "SRC-", "scoring_projection_closure")
            if not claims or not evidence or not sources:
                raise RuntimeContractError("Report Projection Fact Binding has incomplete provenance", code="INSUFFICIENT_EVIDENCE", rule="scoring_projection_closure")
            for claim in claims:
                links.setdefault(claim, set()).update(evidence)
            actual_evidence.update(evidence)
            actual_sources.update(sources)
            group_sources.update(sources)
        citation_sources = _string_refs(group.get("citation_source_ids"), "SRC-", "scoring_projection_closure")
        if group_sources != set(citation_sources):
            raise RuntimeContractError("Report Projection Fact Group citation sources do not match its facts", code="INSUFFICIENT_EVIDENCE", rule="scoring_projection_closure")
    if set(links) != set(closure_claims) or actual_evidence != set(closure_evidence) or actual_sources != set(closure_sources):
        raise RuntimeContractError("Report Projection Citation Closure is not minimal and complete", code="INSUFFICIENT_EVIDENCE", rule="scoring_projection_closure")
    return {claim: frozenset(evidence) for claim, evidence in links.items()}


def _parse_dimension(raw: Any) -> RubricDimension:
    item = _require_mapping(raw, "scoring_rubric_dimensions")
    if set(item) != {"id", "definition", "weight", "allowed_claim_categories", "minimum_evidence_count"}:
        raise RuntimeContractError("Scoring Rubric Dimension shape is invalid", code="SCHEMA_INVALID", rule="scoring_rubric_dimensions")
    dimension_id = item["id"]
    definition = item["definition"]
    categories = item["allowed_claim_categories"]
    minimum = item["minimum_evidence_count"]
    if not isinstance(dimension_id, str) or not dimension_id or not isinstance(definition, str) or not definition.strip():
        raise RuntimeContractError("Scoring Rubric Dimension identity/definition is invalid", code="SCHEMA_INVALID", rule="scoring_rubric_dimensions")
    if not isinstance(categories, list) or not categories or len(set(categories)) != len(categories) or any(item not in _CLAIM_CATEGORIES for item in categories):
        raise RuntimeContractError("Scoring Rubric claim categories are invalid", code="SCHEMA_INVALID", rule="scoring_rubric_dimensions")
    if type(minimum) is not int or minimum < 1:
        raise RuntimeContractError("Scoring Rubric minimum Evidence count is invalid", code="SCHEMA_INVALID", rule="scoring_rubric_dimensions")
    return RubricDimension(dimension_id, definition.strip(), Decimal(str(item["weight"])), tuple(categories), minimum)


def _validated_claim_categories(
    claim_refs: tuple[str, ...],
    claim_category_index: Mapping[str, str] | None,
    dimension: RubricDimension,
) -> tuple[tuple[str, str], ...]:
    if not isinstance(claim_category_index, Mapping):
        raise RuntimeContractError(
            "Dimension Judgment validation requires a system-owned Claim category index",
            code="DEPENDENCY_NOT_READY",
            rule="scoring_claim_category_index",
        )
    for claim_ref, category in claim_category_index.items():
        if not isinstance(claim_ref, str) or not claim_ref.startswith("CL-") or len(claim_ref) == 3 or not isinstance(category, str) or category not in _CLAIM_CATEGORIES:
            raise RuntimeContractError(
                "Claim category index contains an unknown Claim identity or category",
                code="SCHEMA_INVALID",
                rule="scoring_claim_category",
            )
    validated: list[tuple[str, str]] = []
    for claim_ref in claim_refs:
        category = claim_category_index.get(claim_ref)
        if category is None:
            raise RuntimeContractError(
                "Dimension Judgment Claim has no system-owned category",
                code="INSUFFICIENT_EVIDENCE",
                rule="scoring_claim_category",
                details={"claim_ref": claim_ref},
            )
        if category not in dimension.allowed_claim_categories:
            raise RuntimeContractError(
                "Dimension Judgment Claim category is outside the Rubric dimension scope",
                code="SECURITY_POLICY_VIOLATION",
                rule="scoring_claim_category_scope",
                details={"claim_ref": claim_ref, "category": category, "dimension_id": dimension.id},
            )
        validated.append((claim_ref, category))
    return tuple(validated)


def _load_fixed_yaml(root: Path, relative: str, rule: str) -> Mapping[str, Any]:
    path = (root / relative).resolve()
    try:
        path.relative_to(root)
        if path.is_symlink():
            raise OSError("symbolic links are not allowed")
        document = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, yaml.YAMLError) as exc:
        raise RuntimeContractError("Unable to load fixed scoring contract", code="SCHEMA_INVALID", rule=rule, details={"path": relative}) from exc
    return _require_mapping(document, rule)


def _require_mapping(value: Any, rule: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise RuntimeContractError("Scoring contract value must be an object", code="SCHEMA_INVALID", rule=rule)
    return value


def _string_refs(value: Any, prefix: str, rule: str) -> tuple[str, ...]:
    if not isinstance(value, (list, tuple)) or any(not isinstance(item, str) or not item.startswith(prefix) or len(item) == len(prefix) for item in value):
        raise RuntimeContractError("Scoring references are malformed", code="SCHEMA_INVALID", rule=rule)
    if len(set(value)) != len(value):
        raise RuntimeContractError("Scoring references must be unique", code="SCHEMA_INVALID", rule=rule)
    return tuple(value)


def _validate_artifact_ref(value: str, rule: str) -> None:
    if not isinstance(value, str) or _ARTIFACT_REF.fullmatch(value) is None:
        raise RuntimeContractError("Artifact reference is invalid", code="SCHEMA_INVALID", rule=rule)


def _number(value: Decimal) -> int | float:
    normalized = value.quantize(Decimal("0.000001")).normalize()
    return int(normalized) if normalized == normalized.to_integral_value() else float(normalized)


__all__ = [
    "DimensionJudgment",
    "IndependentScoreVerifier",
    "RubricDimension",
    "ScoreVerification",
    "ScoringRubric",
    "TransparentScoreOutcome",
    "VerifiedJudgment",
    "aggregate_transparent_scores",
    "load_profile_rubric",
    "validate_dimension_judgment",
]
