"""Kernel-owned P0-04 competitor discovery, ranking, and Deep Dive services.

Providers may inspect approved input Artifacts and propose source-backed facts,
but they never receive the Runtime Kernel, storage, Artifact headers, or a
write capability.  Ranking and all Runtime transitions remain deterministic.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any, Callable, Mapping, Protocol, Sequence, TYPE_CHECKING

from .domain import AttemptStatus, FanOutExpansion, NodeAddress, NodeStatus, deep_freeze, deep_thaw
from .errors import RuntimeContractError
from .fact_provenance import canonical_value_hash

if TYPE_CHECKING:  # pragma: no cover - imports only support static checking
    from .kernel import RuntimeKernel


_CATEGORIES = ("direct", "indirect", "substitute", "adjacent", "platform_risk")
_CATEGORY_SCORES = {category: len(_CATEGORIES) - index for index, category in enumerate(_CATEGORIES)}
_DISCOVERY_KEYS = frozenset({"sources", "competitors"})
_DEEP_DIVE_KEYS = frozenset({"sources", "deep_dive"})
_CANDIDATE_KEYS = frozenset({"id", "name", "category", "homepage", "repository", "relevance_reason", "source_ids"})
_ANALYSIS_NODE_TYPES = {
    "feature_analysis": "feature",
    "traction_analysis": "traction",
    "review_analysis": "review",
    "pricing_analysis": "pricing",
}
_ANALYSIS_ADDRESSES = tuple(NodeAddress(("competitor",), node_id) for node_id in _ANALYSIS_NODE_TYPES)
_PROJECTION_ANALYSES = (
    ("feature_analysis", "feature", "FG-FEATURE", "analysis-feature"),
    ("traction_analysis", "traction", "FG-TRACTION", "analysis-traction"),
    ("review_analysis", "review", "FG-REVIEW", "analysis-review"),
    ("pricing_analysis", "pricing", "FG-PRICING", "analysis-pricing"),
)


class CompetitorResearchProvider(Protocol):
    """Read-only fact provider for P0-04 research nodes."""

    def discover(self, request: "CompetitorDiscoveryRequest") -> Mapping[str, Any]: ...

    def deep_dive(self, request: "CompetitorDeepDiveRequest") -> Mapping[str, Any]: ...


@dataclass(frozen=True)
class CompetitorDiscoveryRequest:
    run_id: str
    attempt_id: str
    idea_definition: Mapping[str, Any]
    research_contract: Mapping[str, Any]
    source_index: Mapping[str, Mapping[str, Any]]


@dataclass(frozen=True)
class CompetitorDeepDiveRequest:
    run_id: str
    attempt_id: str
    competitor: Mapping[str, Any]
    ranking: Mapping[str, Any]
    research_contract: Mapping[str, Any]
    source_index: Mapping[str, Mapping[str, Any]]


class CallbackCompetitorResearchProvider:
    """Embedding adapter for host-provided, untrusted research callbacks."""

    def __init__(
        self,
        discovery_callback: Callable[[CompetitorDiscoveryRequest], Mapping[str, Any]],
        deep_dive_callback: Callable[[CompetitorDeepDiveRequest], Mapping[str, Any]],
    ) -> None:
        self._discovery_callback = discovery_callback
        self._deep_dive_callback = deep_dive_callback

    @staticmethod
    def _mapping(value: Any, *, rule: str) -> Mapping[str, Any]:
        if not isinstance(value, Mapping):
            raise RuntimeContractError("Competitor Research Provider must return an object proposal", rule=rule)
        return value

    def discover(self, request: CompetitorDiscoveryRequest) -> Mapping[str, Any]:
        return self._mapping(self._discovery_callback(request), rule="competitor_provider_discovery")

    def deep_dive(self, request: CompetitorDeepDiveRequest) -> Mapping[str, Any]:
        return self._mapping(self._deep_dive_callback(request), rule="competitor_provider_deep_dive")


class FixtureCompetitorResearchProvider:
    """Deterministic fixture catalog for P0-04 tests and local demos."""

    def __init__(self, catalog: Mapping[str, Mapping[str, Any]]) -> None:
        self._catalog = {str(key): deep_thaw(value) for key, value in catalog.items()}

    def discover(self, request: CompetitorDiscoveryRequest) -> Mapping[str, Any]:
        del request
        value = self._catalog.get("discovery", {})
        if not isinstance(value, Mapping):
            raise RuntimeContractError("Fixture Discovery proposal is invalid", rule="fixture_competitor_discovery")
        return deep_thaw(value)

    def deep_dive(self, request: CompetitorDeepDiveRequest) -> Mapping[str, Any]:
        competitor_id = request.competitor.get("id")
        value = self._catalog.get(f"deep_dive:{competitor_id}", self._catalog.get("deep_dive:*", {}))
        if not isinstance(value, Mapping):
            raise RuntimeContractError("Fixture Deep Dive proposal is invalid", rule="fixture_competitor_deep_dive")
        return deep_thaw(value)


class ConservativeCompetitorResearchProvider:
    """No-inference fallback: empty evidence leads to the canonical block path."""

    def discover(self, request: CompetitorDiscoveryRequest) -> Mapping[str, Any]:
        del request
        return {"sources": [], "competitors": []}

    def deep_dive(self, request: CompetitorDeepDiveRequest) -> Mapping[str, Any]:
        del request
        return {"sources": [], "deep_dive": {}}


def _copy(value: Mapping[str, Any]) -> dict[str, Any]:
    return json.loads(json.dumps(deep_thaw(value), ensure_ascii=False))


def _canonical_hash(document: Mapping[str, Any]) -> str:
    payload = _copy(document)
    payload["artifact"].pop("content_hash", None)
    return "sha256:" + hashlib.sha256(
        json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def _artifact_header(snapshot, attempt, artifact_type: str, artifact_id: str) -> dict[str, Any]:
    state = snapshot.node_states.get(attempt.address)
    previous_versions = [
        int(reference.rsplit("@", 1)[1])
        for reference in (state.artifact_refs if state is not None else ())
        if reference.startswith(artifact_id + "@") and reference.rsplit("@", 1)[1].isdigit()
    ]
    version = max(previous_versions, default=0) + 1
    return {
        "id": artifact_id,
        "type": artifact_type,
        "schema_version": snapshot.contract_version,
        "version": version,
        "produced_by": {"skill": attempt.skill_ref.rsplit("@", 1)[0], "attempt": attempt.attempt_id},
        "created_at": "",  # Runtime service fills the Kernel clock value before validation.
        "supersedes": f"{artifact_id}@{version - 1}" if version > 1 else None,
        "status": "active",
        "content_hash": "",
    }


def _artifact_id(prefix: str, run_id: str, competitor_id: str | None = None) -> str:
    run_part = run_id.removeprefix("run_").upper()
    competitor_part = "" if competitor_id is None else "-" + competitor_id.upper()
    return f"ART-{prefix}-{run_part}{competitor_part}"


def _proposal(value: Any, *, allowed: frozenset[str], rule: str) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise RuntimeContractError("Competitor Research Provider proposal must be an object", rule=rule)
    unexpected = set(value) - allowed
    if unexpected:
        raise RuntimeContractError(
            "Competitor Research Provider attempted to set unsupported or Runtime-owned fields",
            code="SECURITY_POLICY_VIOLATION",
            rule=rule,
            details={"fields": tuple(sorted(unexpected))},
        )
    return _copy(value)


def _list(value: Any, *, rule: str) -> list[Any]:
    if not isinstance(value, list):
        raise RuntimeContractError("Competitor Research Provider field must be a list", code="SCHEMA_INVALID", rule=rule)
    return value


def _required_text(value: Any, *, rule: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise RuntimeContractError("Competitor Research text fields must be non-empty strings", code="SCHEMA_INVALID", rule=rule)
    return value.strip()


def _required_competitor_count(contract: Mapping[str, Any], *, fallback: int) -> int:
    required = contract.get("required_evidence")
    value = required.get("competitor_count") if isinstance(required, Mapping) else None
    if isinstance(value, int) and not isinstance(value, bool) and value > 0:
        return value
    return fallback


def _public_source(source: Mapping[str, Any]) -> bool:
    # Source Schema already requires the stable publisher/title metadata used
    # by URL-less identity fallback.  A declared public source without a
    # stable URL remains usable for provenance; the Runtime never dereferences
    # either form of URL here.
    return source.get("access_status") == "public"


def _source_issues(source_ids: Any, source_index: Mapping[str, Mapping[str, Any]], *, label: str) -> list[str]:
    if not isinstance(source_ids, list) or not source_ids:
        return [f"{label} has no supporting Source IDs"]
    if len(source_ids) != len(set(source_ids)) or any(not isinstance(item, str) for item in source_ids):
        return [f"{label} has invalid Source IDs"]
    issues: list[str] = []
    for source_id in source_ids:
        source = source_index.get(source_id)
        if source is None:
            issues.append(f"{label} references missing Source {source_id}")
        elif not _public_source(source):
            issues.append(f"{label} references inaccessible Source {source_id}")
    return issues


def _candidate_document(snapshot, attempt, candidates: list[Any], clock_now: str) -> dict[str, Any]:
    normalized: list[dict[str, Any]] = []
    seen: set[str] = set()
    for raw in candidates:
        if not isinstance(raw, Mapping) or set(raw) != _CANDIDATE_KEYS:
            raise RuntimeContractError("Candidate proposal shape is invalid", code="SCHEMA_INVALID", rule="competitor_candidate_shape")
        identifier = _required_text(raw.get("id"), rule="competitor_candidate_id")
        if identifier in seen:
            raise RuntimeContractError("Candidate IDs must be unique", code="INPUT_INVALID", rule="competitor_candidate_duplicate")
        seen.add(identifier)
        normalized.append(
            {
                "id": identifier,
                "name": _required_text(raw.get("name"), rule="competitor_candidate_name"),
                "category": raw.get("category"),
                "homepage": raw.get("homepage"),
                "repository": raw.get("repository"),
                "relevance_reason": _required_text(raw.get("relevance_reason"), rule="competitor_candidate_reason"),
                "source_ids": list(raw.get("source_ids", [])) if isinstance(raw.get("source_ids"), list) else raw.get("source_ids"),
            }
        )
    header = _artifact_header(snapshot, attempt, "competitor_candidates", _artifact_id("CAND", snapshot.run_id))
    header["created_at"] = clock_now
    document = {"artifact": header, "competitors": normalized}
    document["artifact"]["content_hash"] = _canonical_hash(document)
    return document


def _ranking_document(snapshot, attempt, candidates: list[Mapping[str, Any]], count: int, source_index: Mapping[str, Mapping[str, Any]], clock_now: str) -> dict[str, Any]:
    def sort_key(candidate: Mapping[str, Any]) -> tuple[int, int, int, str, str]:
        source_ids = candidate["source_ids"]
        sources = [source_index[item] for item in source_ids]
        fresh = sum(source.get("freshness_status") == "FRESH" for source in sources)
        return (-_CATEGORY_SCORES[candidate["category"]], -fresh, -len(sources), candidate["name"].casefold(), candidate["id"])

    ordered = sorted(candidates, key=sort_key)
    selected, excluded = ordered[:count], ordered[count:]
    ranking: list[dict[str, Any]] = []
    for position, candidate in enumerate(selected, start=1):
        sources = [source_index[item] for item in candidate["source_ids"]]
        fresh = sum(source.get("freshness_status") == "FRESH" for source in sources)
        score = _CATEGORY_SCORES[candidate["category"]]
        ranking.append(
            {
                "competitor_id": candidate["id"],
                "rank": position,
                "score": score,
                "rationale": f"Default policy score {score} for {candidate['category']}; {fresh} FRESH and {len(sources)} resolvable public Sources.",
            }
        )
    header = _artifact_header(snapshot, attempt, "competitor_ranking", _artifact_id("RANK", snapshot.run_id))
    header["created_at"] = clock_now
    document = {
        "artifact": header,
        "selection_methodology": (
            "Default Ranking Policy v1: direct=5, indirect=4, substitute=3, adjacent=2, platform_risk=1; "
            "ties use FRESH Source count descending, resolvable public Source count descending, normalized name, then ID."
        ),
        "ranking": ranking,
        "excluded_candidates": [
            {"competitor_id": candidate["id"], "reason": f"outside the top {count} candidates under Default Ranking Policy v1"}
            for candidate in excluded
        ],
    }
    document["artifact"]["content_hash"] = _canonical_hash(document)
    return document


def _deep_dive_document(snapshot, attempt, raw: Any, competitor: Mapping[str, Any], clock_now: str) -> dict[str, Any]:
    if not isinstance(raw, Mapping):
        raise RuntimeContractError("Deep Dive proposal must be an object", code="SCHEMA_INVALID", rule="competitor_deep_dive_shape")
    if "artifact" in raw:
        raise RuntimeContractError("Provider cannot set an Artifact header", code="SECURITY_POLICY_VIOLATION", rule="competitor_deep_dive_authority")
    document = _copy(raw)
    reported = document.get("competitor")
    expected = {"id": competitor["id"], "name": competitor["name"], "category": competitor["category"]}
    if reported != expected:
        raise RuntimeContractError("Deep Dive competitor identity must match the selected candidate", code="SECURITY_POLICY_VIOLATION", rule="competitor_deep_dive_identity")
    header = _artifact_header(snapshot, attempt, "competitor_deep_dive", _artifact_id("DEEP", snapshot.run_id, competitor["id"]))
    header["created_at"] = clock_now
    document["artifact"] = header
    document["artifact"]["content_hash"] = _canonical_hash(document)
    return document


def _remap_source_ids(value: Any, aliases: Mapping[str, str], *, rule: str) -> list[str]:
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        raise RuntimeContractError("Source IDs must be a list of strings", code="SCHEMA_INVALID", rule=rule)
    return list(dict.fromkeys(aliases.get(item, item) for item in value))


def _remap_deep_dive_sources(raw: Mapping[str, Any], aliases: Mapping[str, str]) -> dict[str, Any]:
    """Rewrite Provider Source aliases before Kernel-owned Artifact creation."""

    document = _copy(raw)
    if isinstance(document.get("source_ids"), list):
        document["source_ids"] = _remap_source_ids(document["source_ids"], aliases, rule="competitor_deep_dive_source_ids")
    traction = document.get("traction")
    if isinstance(traction, dict):
        github = traction.get("github_stars")
        if isinstance(github, dict) and isinstance(github.get("source_id"), str):
            github["source_id"] = aliases.get(github["source_id"], github["source_id"])
        growth = traction.get("star_growth_30d")
        if isinstance(growth, dict) and isinstance(growth.get("source_ids"), list):
            growth["source_ids"] = _remap_source_ids(growth["source_ids"], aliases, rule="competitor_deep_dive_growth_sources")
    return document


def _metric(value: Any, *, source: str, source_ids: Sequence[str] = (), observed_at: str | None = None, method: str | None = None) -> dict[str, Any]:
    metric: dict[str, Any] = {"value": value, "source": source}
    if source_ids:
        metric["source_ids"] = list(source_ids)
    if observed_at is not None:
        metric["observed_at"] = observed_at
    if method is not None:
        metric["method"] = method
    return metric


def _dataset_document(snapshot, attempt, deep_dives: Sequence[Mapping[str, Any]], clock_now: str) -> dict[str, Any]:
    competitors: list[dict[str, Any]] = []
    for deep_dive in deep_dives:
        competitor = deep_dive["competitor"]
        source_ids = tuple(deep_dive["source_ids"])
        product = deep_dive["product"]
        traction = deep_dive["traction"]
        feedback = deep_dive["user_feedback"]
        business = deep_dive["business"]
        github = traction["github_stars"]
        growth = traction["star_growth_30d"]
        github_sources = (github["source_id"],) if isinstance(github.get("source_id"), str) else ()
        growth_sources = tuple(growth["source_ids"])
        metrics = {
            "feature_count": _metric(len(product["features"]), source="derived", source_ids=source_ids),
            "workflow_step_count": _metric(len(product["core_workflow"]), source="derived", source_ids=source_ids),
            "github_stars": _metric(github["value"], source="reported", source_ids=github_sources, observed_at=github["observed_at"]),
            "star_growth_30d": _metric(growth["value"], source="reported", source_ids=growth_sources, observed_at=growth["observed_at"], method=growth["method"]),
            # Contributors and releases are time-varying observations as well.
            # The frozen Deep Dive contract gives their shared source-observation
            # time through github_stars, so retain that value instead of inventing
            # a collection time or silently dropping temporal provenance.
            "contributors": _metric(traction["contributors"], source="reported", source_ids=source_ids, observed_at=github["observed_at"]),
            "releases_90d": _metric(traction["releases_90d"], source="reported", source_ids=source_ids, observed_at=github["observed_at"]),
            "positive_feedback_count": _metric(len(feedback["positive"]), source="derived", source_ids=source_ids, method="visible_feedback_items"),
            "negative_feedback_count": _metric(len(feedback["negative"]), source="derived", source_ids=source_ids, method="visible_feedback_items"),
            "pricing": _metric(business["pricing"], source="reported", source_ids=source_ids),
            "license": _metric(business["license"], source="reported", source_ids=source_ids),
            "monetization": _metric(business["monetization"], source="reported", source_ids=source_ids),
        }
        competitors.append({"id": competitor["id"], "name": competitor["name"], "category": competitor["category"], "metrics": metrics})
    header = _artifact_header(snapshot, attempt, "competitor_dataset", _artifact_id("DATA", snapshot.run_id))
    header["created_at"] = clock_now
    document = {
        "artifact": header,
        "schema_version": snapshot.contract_version,
        "generated_at": clock_now,
        "competitors": competitors,
    }
    document["artifact"]["content_hash"] = _canonical_hash(document)
    return document


def _analysis_document(snapshot, attempt, analysis_type: str, observations: Sequence[str], evidence_ids: Sequence[str], limitations: Sequence[str], clock_now: str) -> dict[str, Any]:
    header = _artifact_header(snapshot, attempt, "competitor_analysis", _artifact_id(f"ANL-{analysis_type.upper()}", snapshot.run_id))
    header["created_at"] = clock_now
    document = {
        "artifact": header,
        "analysis_type": analysis_type,
        "observations": list(observations),
        "evidence_ids": list(evidence_ids),
        "limitations": list(limitations),
    }
    document["artifact"]["content_hash"] = _canonical_hash(document)
    return document


def _display_number(value: Any) -> str:
    return "null" if value is None else str(value)


class CompetitorResearchService:
    """Advance the Kernel-owned Competitor Research business Attempts."""

    def __init__(
        self,
        kernel: "RuntimeKernel",
        provider: CompetitorResearchProvider | None = None,
    ) -> None:
        self.kernel = kernel
        self.provider = provider or ConservativeCompetitorResearchProvider()

    def _artifact(self, snapshot, reference: str) -> Mapping[str, Any]:
        return self.kernel._storage_for(snapshot.run_id).read_artifact(reference)

    def _idea_and_contract(self, snapshot) -> tuple[Mapping[str, Any], Mapping[str, Any]]:
        idea_state = snapshot.node_states.get(NodeAddress((), "idea"))
        if idea_state is None or idea_state.status is not NodeStatus.VERIFIED or not idea_state.artifact_refs:
            raise RuntimeContractError("Competitor Discovery requires a verified Idea Definition", rule="competitor_idea_input")
        if not snapshot.research_contract_ref:
            raise RuntimeContractError("Competitor Discovery requires a verified Research Contract", rule="competitor_contract_input")
        return self._artifact(snapshot, idea_state.artifact_refs[-1]), self._artifact(snapshot, snapshot.research_contract_ref)

    @staticmethod
    def _failure_result(snapshot, attempt, *, reason: str) -> Mapping[str, Any]:
        return {
            "executor_result": {
                "schema_version": snapshot.contract_version,
                "run_id": snapshot.run_id,
                "node_id": attempt.address.node_id,
                "attempt_id": attempt.attempt_id,
                "status": "FAILED",
                "output_artifact_refs": [],
                "source_upserts": [],
                "usage": {"automated_duration_seconds": 0, "source_count": 0, "input_tokens": 0, "output_tokens": 0, "estimated_cost": 0},
                "error": {"code": "INSUFFICIENT_EVIDENCE", "recoverable": True, "details": {"reason": reason}},
            }
        }

    def _advance_discovery(self, snapshot, attempt) -> Mapping[str, Any]:
        idea, contract = self._idea_and_contract(snapshot)
        proposal = _proposal(
            self.provider.discover(
                CompetitorDiscoveryRequest(
                    run_id=snapshot.run_id,
                    attempt_id=attempt.attempt_id,
                    idea_definition=deep_freeze(idea),
                    research_contract=deep_freeze(contract),
                    source_index=self.kernel.source_index_for(snapshot.run_id),
                )
            ),
            allowed=_DISCOVERY_KEYS,
            rule="competitor_discovery_authority",
        )
        source_records = _list(proposal.get("sources", []), rule="competitor_discovery_sources")
        candidates = _list(proposal.get("competitors", []), rule="competitor_discovery_candidates")
        if len(source_records) > attempt.budget.max_sources:
            raise RuntimeContractError("Discovery proposal exceeds the Attempt source budget", code="BUDGET_EXCEEDED", rule="competitor_discovery_budget")
        source_index = self.kernel.source_index_for(snapshot.run_id, source_records)
        aliases = self.kernel._source_aliases_for(snapshot.run_id, source_records)
        remapped_candidates = []
        for candidate in candidates:
            if not isinstance(candidate, Mapping):
                remapped_candidates.append(candidate)
                continue
            item = _copy(candidate)
            if isinstance(item.get("source_ids"), list):
                item["source_ids"] = _remap_source_ids(item["source_ids"], aliases, rule="competitor_candidate_source_ids")
            remapped_candidates.append(item)
        document = _candidate_document(snapshot, attempt, remapped_candidates, self.kernel.clock.now())
        self.kernel._validate_typed_output(snapshot, attempt.attempt_id, "artifacts/02-research/competitors/candidates.json", document)
        evidence_valid = [
            item for item in document["competitors"] if not _source_issues(item.get("source_ids"), source_index, label=f"candidate {item.get('id')}")
        ]
        source_types = {
            source_index[source_id]["source_type"]
            for item in evidence_valid
            for source_id in item["source_ids"]
            if source_id in source_index
        }
        required_count = _required_competitor_count(contract, fallback=len(evidence_valid))
        issues: list[str] = []
        if len(evidence_valid) < required_count:
            issues.append(f"only {len(evidence_valid)} source-backed candidates for required {required_count}")
        if len(source_types) < 2:
            issues.append("fewer than two source types support the candidate set")
        if issues:
            self.kernel.write_typed_artifact(
                snapshot.run_id,
                attempt.attempt_id,
                "artifacts/02-research/competitors/candidates.json",
                document,
                source_records=source_records,
            )
            failed = self.kernel.apply_persisted_executor_result(
                snapshot.run_id,
                attempt.attempt_id,
                self._failure_result(self.kernel.load_run(snapshot.run_id), attempt, reason="; ".join(issues)),
            )
            return {"state": failed.next_snapshot.to_wire_state(), "outcome": "INSUFFICIENT_EVIDENCE", "issues": issues}
        completed = self.kernel.complete_persisted_business_attempt(
            snapshot.run_id,
            attempt.attempt_id,
            (("artifacts/02-research/competitors/candidates.json", document),),
            source_records=source_records,
        )
        return {"state": completed.to_wire_state(), "outcome": "DISCOVERED", "artifact_ref": completed.node_states[attempt.address].artifact_refs[-1]}

    def _advance_ranking(self, snapshot, attempt) -> Mapping[str, Any]:
        discovery = snapshot.node_states.get(NodeAddress(("competitor",), "discovery"))
        if discovery is None or discovery.status is not NodeStatus.VERIFIED or not discovery.artifact_refs:
            raise RuntimeContractError("Candidate Ranking requires a verified Candidate Artifact", rule="competitor_ranking_input")
        _idea, contract = self._idea_and_contract(snapshot)
        candidates_document = self._artifact(snapshot, discovery.artifact_refs[-1])
        candidates = candidates_document.get("competitors")
        if not isinstance(candidates, list) or not all(isinstance(item, Mapping) for item in candidates):
            raise RuntimeContractError("Stored Candidate Artifact is invalid", code="SCHEMA_INVALID", rule="competitor_ranking_input")
        source_index = self.kernel.source_index_for(snapshot.run_id)
        issues = [issue for item in candidates for issue in _source_issues(item.get("source_ids"), source_index, label=f"candidate {item.get('id')}")]
        if issues:
            raise RuntimeContractError("Candidate Ranking has unresolved Source references", code="SCHEMA_INVALID", rule="competitor_ranking_sources", details={"issues": tuple(issues)})
        required_count = _required_competitor_count(contract, fallback=len(candidates))
        if len(candidates) < required_count:
            raise RuntimeContractError("Candidate Ranking has insufficient verified candidates", code="INSUFFICIENT_EVIDENCE", rule="competitor_ranking_count")
        document = _ranking_document(snapshot, attempt, list(candidates), required_count, source_index, self.kernel.clock.now())
        completed = self.kernel.complete_persisted_business_attempt(
            snapshot.run_id,
            attempt.attempt_id,
            (("artifacts/02-research/competitors/ranking.yaml", document),),
        )
        ranking_ref = completed.node_states[attempt.address].artifact_refs[-1]
        selected = tuple(item["competitor_id"] for item in document["ranking"])
        scheduled = self.kernel.schedule_persisted(
            snapshot.run_id,
            fanout_expansions=(FanOutExpansion(NodeAddress(("competitor",), "deep_dive"), ranking_ref, selected),),
        )
        return {
            "state": scheduled.next_snapshot.to_wire_state(),
            "outcome": "RANKED",
            "artifact_ref": ranking_ref,
            "selected_competitors": list(selected),
            "scheduled_attempt_ids": [item.attempt_id for item in scheduled.attempts_to_start],
        }

    def _advance_deep_dive(self, snapshot, attempt) -> Mapping[str, Any]:
        if attempt.address.instance_key is None:
            raise RuntimeContractError("Deep Dive must be a fan-out instance", rule="competitor_deep_dive_instance")
        ranking_state = snapshot.node_states.get(NodeAddress(("competitor",), "candidate_ranking"))
        if ranking_state is None or ranking_state.status is not NodeStatus.VERIFIED or not ranking_state.artifact_refs:
            raise RuntimeContractError("Deep Dive requires a verified Ranking Artifact", rule="competitor_deep_dive_ranking")
        ranking = self._artifact(snapshot, ranking_state.artifact_refs[-1])
        selected_ids = {item.get("competitor_id") for item in ranking.get("ranking", []) if isinstance(item, Mapping)}
        if attempt.address.instance_key not in selected_ids:
            raise RuntimeContractError("Deep Dive instance is not selected by the Ranking Artifact", code="SECURITY_POLICY_VIOLATION", rule="competitor_deep_dive_selection")
        discovery = snapshot.node_states.get(NodeAddress(("competitor",), "discovery"))
        if discovery is None or not discovery.artifact_refs:
            raise RuntimeContractError("Deep Dive requires the Candidate Artifact", rule="competitor_deep_dive_candidates")
        candidates = self._artifact(snapshot, discovery.artifact_refs[-1]).get("competitors", [])
        competitor = next((item for item in candidates if isinstance(item, Mapping) and item.get("id") == attempt.address.instance_key), None)
        if competitor is None:
            raise RuntimeContractError("Selected competitor is absent from the Candidate Artifact", code="SCHEMA_INVALID", rule="competitor_deep_dive_candidates")
        _idea, contract = self._idea_and_contract(snapshot)
        proposal = _proposal(
            self.provider.deep_dive(
                CompetitorDeepDiveRequest(
                    run_id=snapshot.run_id,
                    attempt_id=attempt.attempt_id,
                    competitor=deep_freeze(competitor),
                    ranking=deep_freeze(ranking),
                    research_contract=deep_freeze(contract),
                    source_index=self.kernel.source_index_for(snapshot.run_id),
                )
            ),
            allowed=_DEEP_DIVE_KEYS,
            rule="competitor_deep_dive_authority",
        )
        source_records = _list(proposal.get("sources", []), rule="competitor_deep_dive_sources")
        if len(source_records) > attempt.budget.max_sources:
            raise RuntimeContractError("Deep Dive proposal exceeds the Attempt source budget", code="BUDGET_EXCEEDED", rule="competitor_deep_dive_budget")
        source_index = self.kernel.source_index_for(snapshot.run_id, source_records)
        aliases = self.kernel._source_aliases_for(snapshot.run_id, source_records)
        raw_deep_dive = proposal.get("deep_dive")
        if isinstance(raw_deep_dive, Mapping):
            raw_deep_dive = _remap_deep_dive_sources(raw_deep_dive, aliases)
        document = _deep_dive_document(snapshot, attempt, raw_deep_dive, competitor, self.kernel.clock.now())
        logical_path = f"artifacts/02-research/competitors/deep-dives/{attempt.address.instance_key}.yaml"
        self.kernel._validate_typed_output(snapshot, attempt.attempt_id, logical_path, document)
        issues = _source_issues(document.get("source_ids"), source_index, label=f"Deep Dive {attempt.address.instance_key}")
        traction = document.get("traction")
        if isinstance(traction, Mapping):
            github = traction.get("github_stars")
            if isinstance(github, Mapping) and isinstance(github.get("source_id"), str):
                issues.extend(_source_issues([github["source_id"]], source_index, label="github_stars"))
            growth = traction.get("star_growth_30d")
            if isinstance(growth, Mapping) and isinstance(growth.get("source_ids"), list):
                if growth.get("value") is not None or growth["source_ids"]:
                    issues.extend(_source_issues(growth["source_ids"], source_index, label="star_growth_30d"))
        if issues:
            self.kernel.write_typed_artifact(
                snapshot.run_id,
                attempt.attempt_id,
                logical_path,
                document,
                source_records=source_records,
            )
            failed = self.kernel.apply_persisted_executor_result(
                snapshot.run_id,
                attempt.attempt_id,
                self._failure_result(self.kernel.load_run(snapshot.run_id), attempt, reason="; ".join(issues)),
            )
            return {"state": failed.next_snapshot.to_wire_state(), "outcome": "INSUFFICIENT_EVIDENCE", "issues": issues}
        completed = self.kernel.complete_persisted_business_attempt(
            snapshot.run_id,
            attempt.attempt_id,
            ((logical_path, document),),
            source_records=source_records,
        )
        scheduled = self.kernel.schedule_persisted(snapshot.run_id)
        return {
            "state": scheduled.next_snapshot.to_wire_state(),
            "outcome": "DEEP_DIVE_COMPLETED",
            "artifact_ref": completed.node_states[attempt.address].artifact_refs[-1],
        }

    def _selected_deep_dives(self, snapshot) -> tuple[Mapping[str, Any], ...]:
        ranking_state = snapshot.node_states.get(NodeAddress(("competitor",), "candidate_ranking"))
        if ranking_state is None or ranking_state.status is not NodeStatus.VERIFIED or not ranking_state.artifact_refs:
            raise RuntimeContractError("Competitor downstream work requires a verified Ranking Artifact", rule="competitor_ranking_input")
        ranking = self._artifact(snapshot, ranking_state.artifact_refs[-1])
        raw_ranking = ranking.get("ranking")
        if not isinstance(raw_ranking, list):
            raise RuntimeContractError("Stored Ranking Artifact is invalid", code="SCHEMA_INVALID", rule="competitor_ranking_input")
        selected = [item.get("competitor_id") for item in raw_ranking if isinstance(item, Mapping)]
        if not selected or any(not isinstance(item, str) for item in selected) or len(selected) != len(set(selected)):
            raise RuntimeContractError("Ranking selected competitor IDs are invalid", code="SCHEMA_INVALID", rule="competitor_ranking_input")
        documents: list[Mapping[str, Any]] = []
        for competitor_id in selected:
            address = NodeAddress(("competitor",), "deep_dive", competitor_id)
            state = snapshot.node_states.get(address)
            if state is None or state.status is not NodeStatus.VERIFIED or not state.artifact_refs:
                raise RuntimeContractError("Normalized Dataset requires every selected Deep Dive", code="DEPENDENCY_NOT_READY", rule="competitor_deep_dive_fanin")
            document = self._artifact(snapshot, state.artifact_refs[-1])
            competitor = document.get("competitor")
            if not isinstance(competitor, Mapping) or competitor.get("id") != competitor_id:
                raise RuntimeContractError("Deep Dive Artifact identity does not match Ranking", code="SCHEMA_INVALID", rule="competitor_deep_dive_identity")
            documents.append(document)
        return tuple(documents)

    def _dataset_input(self, snapshot) -> tuple[Mapping[str, Any], tuple[Mapping[str, Any], ...]]:
        state = snapshot.node_states.get(NodeAddress(("competitor",), "normalizer"))
        if state is None or state.status is not NodeStatus.VERIFIED or not state.artifact_refs:
            raise RuntimeContractError("Competitor Analysis requires a verified Dataset", rule="competitor_dataset_input")
        dataset = self._artifact(snapshot, state.artifact_refs[-1])
        competitors = dataset.get("competitors")
        if not isinstance(competitors, list) or not competitors:
            raise RuntimeContractError("Stored Competitor Dataset is invalid", code="SCHEMA_INVALID", rule="competitor_dataset_input")
        deep_dives = self._selected_deep_dives(snapshot)
        expected = [item["competitor"]["id"] for item in deep_dives]
        actual = [item.get("id") for item in competitors if isinstance(item, Mapping)]
        if actual != expected or len(actual) != len(competitors):
            raise RuntimeContractError("Competitor Dataset does not represent the selected Deep Dives", code="SCHEMA_INVALID", rule="competitor_dataset_identity")
        return dataset, deep_dives

    @staticmethod
    def _deep_dive_source_ids(deep_dives: Sequence[Mapping[str, Any]]) -> Mapping[str, tuple[str, ...]]:
        sources: dict[str, tuple[str, ...]] = {}
        for document in deep_dives:
            competitor = document["competitor"]
            source_ids = document.get("source_ids")
            if not isinstance(source_ids, list) or any(not isinstance(item, str) for item in source_ids):
                raise RuntimeContractError("Deep Dive has invalid Source IDs", code="SCHEMA_INVALID", rule="competitor_analysis_sources")
            sources[str(competitor["id"])] = tuple(sorted(set(source_ids)))
        return sources

    def _provenance_records(
        self,
        snapshot,
        attempt,
        analysis_type: str,
        observed: Sequence[tuple[str, Sequence[str]]],
    ) -> tuple[tuple[str, ...], tuple[Mapping[str, Any], ...], tuple[Mapping[str, Any], ...]]:
        source_index = self.kernel.source_index_for(snapshot.run_id)
        evidence: list[Mapping[str, Any]] = []
        claims: list[Mapping[str, Any]] = []
        evidence_ids: list[str] = []
        for statement, source_ids in observed:
            normalized_sources = tuple(sorted(set(source_ids)))
            issues = _source_issues(list(normalized_sources), source_index, label=f"{analysis_type} observation")
            if issues:
                raise RuntimeContractError("Analysis observation lacks valid provenance", code="INSUFFICIENT_EVIDENCE", rule="competitor_analysis_provenance", details={"issues": tuple(issues)})
            claim_digest = hashlib.sha256(
                f"{snapshot.run_id}|{attempt.address.node_id}|{statement}".encode("utf-8")
            ).hexdigest()[:16].upper()
            claim_id = f"CL-COMP-{claim_digest}"
            record_ids: list[str] = []
            for source_id in normalized_sources:
                source = source_index[source_id]
                evidence_digest = hashlib.sha256(f"{claim_id}|{source_id}".encode("utf-8")).hexdigest()[:16].upper()
                evidence_id = f"EV-COMP-{evidence_digest}"
                record_ids.append(evidence_id)
                tier = source.get("source_tier")
                reliability = "high" if tier == 1 else "medium" if tier == 2 else "low"
                freshness = "high" if source.get("freshness_status") == "FRESH" else "low" if source.get("freshness_status") == "STALE" else "unknown"
                evidence.append(
                    {
                        "id": evidence_id,
                        "claim_id": claim_id,
                        "source_id": source_id,
                        "evidence_type": "quantitative" if analysis_type in {"feature", "traction", "review"} else "qualitative",
                        "direction": "supports",
                        "relevance": "high",
                        "reliability": reliability,
                        "freshness": freshness,
                        "notes": f"Deterministic {analysis_type} analysis observation.",
                    }
                )
            all_fresh = all(source_index[source_id].get("freshness_status") == "FRESH" for source_id in normalized_sources)
            has_tier_one = any(source_index[source_id].get("source_tier") == 1 for source_id in normalized_sources)
            claims.append(
                {
                    "id": claim_id,
                    "statement": statement,
                    "category": "competitor",
                    "status": "VALIDATED" if all_fresh and has_tier_one else "PARTIALLY_VALIDATED",
                    "confidence": "MEDIUM" if all_fresh and has_tier_one else "LOW",
                    "evidence_ids": record_ids,
                    "contradiction_ids": [],
                }
            )
            evidence_ids.extend(record_ids)
        return tuple(sorted(set(evidence_ids))), tuple(evidence), tuple(claims)

    def _analysis_payload(
        self,
        snapshot,
        analysis_type: str,
    ) -> tuple[tuple[str, ...], tuple[str, ...], tuple[tuple[str, tuple[str, ...]], ...]]:
        _dataset, deep_dives = self._dataset_input(snapshot)
        sources_by_competitor = self._deep_dive_source_ids(deep_dives)
        all_sources = tuple(sorted({source_id for values in sources_by_competitor.values() for source_id in values}))
        observations: list[str] = []
        limitations: list[str] = []
        provenance: list[tuple[str, tuple[str, ...]]] = []

        if analysis_type == "feature":
            taxonomy: dict[str, str] = {}
            presence: dict[str, tuple[set[str], set[str]]] = {}
            for document in deep_dives:
                competitor_id = str(document["competitor"]["id"])
                product = document["product"]
                features = {item.strip().casefold() for item in product["features"] if isinstance(item, str) and item.strip()}
                workflows = {item.strip().casefold() for item in product["core_workflow"] if isinstance(item, str) and item.strip()}
                presence[competitor_id] = (features, workflows)
                for raw in (*product["features"], *product["core_workflow"]):
                    if isinstance(raw, str) and raw.strip():
                        taxonomy.setdefault(raw.strip().casefold(), raw.strip())
            method = "Methodology: exact structured features=1.0; exact structured workflow-only support=0.5; absent explicit support=0.0."
            observations.append(method)
            provenance.append((method, all_sources))
            if not taxonomy:
                limitations.append("No structured feature or workflow entries were available for the selected competitors.")
            for token, label in sorted(taxonomy.items(), key=lambda item: (item[1].casefold(), item[0])):
                values = []
                for competitor_id in sources_by_competitor:
                    features, workflows = presence[competitor_id]
                    coverage = 1.0 if token in features else 0.5 if token in workflows else 0.0
                    values.append(f"{competitor_id}={coverage:.1f}")
                statement = f"Feature coverage '{label}': {', '.join(values)}."
                observations.append(statement)
                provenance.append((statement, all_sources))

        elif analysis_type == "traction":
            method = "Methodology: prioritize observed change and activity metrics; absolute GitHub stars are context only and no composite momentum value is calculated."
            observations.append(method)
            provenance.append((method, all_sources))
            for document in deep_dives:
                competitor_id = str(document["competitor"]["id"])
                traction = document["traction"]
                growth = traction["star_growth_30d"]
                github = traction["github_stars"]
                statement = (
                    f"{competitor_id}: star_growth_30d={_display_number(growth['value'])} "
                    f"(observed_at={growth['observed_at']}); contributors={_display_number(traction['contributors'])}; "
                    f"releases_90d={_display_number(traction['releases_90d'])}; github_stars_context={_display_number(github['value'])} "
                    f"(observed_at={github['observed_at']})."
                )
                observations.append(statement)
                provenance.append((statement, sources_by_competitor[competitor_id]))
                if growth["value"] is None:
                    limitations.append(f"{competitor_id} has no observed 30-day star-growth value.")

        elif analysis_type == "review":
            method = "Methodology: report only visible feedback-item counts; these samples are not population rates or sentiment percentages."
            observations.append(method)
            provenance.append((method, all_sources))
            for document in deep_dives:
                competitor_id = str(document["competitor"]["id"])
                feedback = document["user_feedback"]
                positive, negative = len(feedback["positive"]), len(feedback["negative"])
                statement = f"{competitor_id}: visible_positive_feedback_items={positive}; visible_negative_feedback_items={negative}; sample_size={positive + negative}."
                observations.append(statement)
                provenance.append((statement, sources_by_competitor[competitor_id]))
                if positive + negative == 0:
                    limitations.append(f"{competitor_id} has no visible feedback sample.")

        elif analysis_type == "pricing":
            method = "Methodology: preserve reported pricing, license, and monetization verbatim; unavailable values are not inferred or normalized."
            observations.append(method)
            provenance.append((method, all_sources))
            source_index = self.kernel.source_index_for(snapshot.run_id)
            for document in deep_dives:
                competitor_id = str(document["competitor"]["id"])
                business = document["business"]
                statement = (
                    f"{competitor_id}: pricing={_display_number(business['pricing'])}; license={_display_number(business['license'])}; "
                    f"monetization={_display_number(business['monetization'])}."
                )
                observations.append(statement)
                competitor_sources = sources_by_competitor[competitor_id]
                provenance.append((statement, competitor_sources))
                if any(business[key] is None for key in ("pricing", "license", "monetization")):
                    limitations.append(f"{competitor_id} has unavailable pricing, license, or monetization data.")
                if any(source_index[source_id].get("freshness_status") == "STALE" for source_id in competitor_sources):
                    limitations.append(f"{competitor_id} relies on at least one STALE Source.")
        else:  # Defensive guard for the internal dispatch table.
            raise RuntimeContractError("Unsupported competitor analysis type", rule="competitor_analysis_type")

        return tuple(observations), tuple(dict.fromkeys(limitations)), tuple(provenance)

    def _blocked_outcome(self, snapshot, attempt, *, reason: str) -> Mapping[str, Any]:
        failed = self.kernel.apply_persisted_executor_result(
            snapshot.run_id,
            attempt.attempt_id,
            self._failure_result(snapshot, attempt, reason=reason),
        )
        return {"state": failed.next_snapshot.to_wire_state(), "outcome": "INSUFFICIENT_EVIDENCE", "issues": [reason]}

    def _advance_normalizer(self, snapshot, attempt) -> Mapping[str, Any]:
        try:
            deep_dives = self._selected_deep_dives(snapshot)
            source_index = self.kernel.source_index_for(snapshot.run_id)
            issues = [
                issue
                for document in deep_dives
                for issue in _source_issues(document.get("source_ids"), source_index, label=f"Deep Dive {document['competitor']['id']}")
            ]
            if issues:
                return self._blocked_outcome(snapshot, attempt, reason="; ".join(issues))
            document = _dataset_document(snapshot, attempt, deep_dives, self.kernel.clock.now())
            completed = self.kernel.complete_persisted_business_attempt(
                snapshot.run_id,
                attempt.attempt_id,
                (("artifacts/02-research/competitors/competitor-dataset.json", document),),
            )
        except RuntimeContractError as error:
            if error.code == "DEPENDENCY_NOT_READY":
                raise
            return self._blocked_outcome(snapshot, attempt, reason=str(error))
        scheduled = self.kernel.schedule_persisted(snapshot.run_id, requested_nodes=_ANALYSIS_ADDRESSES)
        return {
            "state": scheduled.next_snapshot.to_wire_state(),
            "outcome": "NORMALIZED",
            "artifact_ref": completed.node_states[attempt.address].artifact_refs[-1],
            "scheduled_attempt_ids": [item.attempt_id for item in scheduled.attempts_to_start],
        }

    def _advance_analysis(self, snapshot, attempt, analysis_type: str) -> Mapping[str, Any]:
        try:
            observations, limitations, observed = self._analysis_payload(snapshot, analysis_type)
            evidence_ids, evidence_records, claim_records = self._provenance_records(snapshot, attempt, analysis_type, observed)
            document = _analysis_document(snapshot, attempt, analysis_type, observations, evidence_ids, limitations, self.kernel.clock.now())
            logical_path = f"artifacts/02-research/competitors/analysis/{analysis_type}-analysis.yaml"
            completed = self.kernel.complete_persisted_business_attempt(
                snapshot.run_id,
                attempt.attempt_id,
                ((logical_path, document),),
                evidence_records=evidence_records,
                claim_records=claim_records,
            )
        except RuntimeContractError as error:
            if error.code == "DEPENDENCY_NOT_READY":
                raise
            return self._blocked_outcome(snapshot, attempt, reason=str(error))
        scheduled = self.kernel.schedule_persisted(snapshot.run_id, requested_nodes=_ANALYSIS_ADDRESSES)
        return {
            "state": scheduled.next_snapshot.to_wire_state(),
            "outcome": f"{analysis_type.upper()}_ANALYSIS_COMPLETED",
            "artifact_ref": completed.node_states[attempt.address].artifact_refs[-1],
            "scheduled_attempt_ids": [item.attempt_id for item in scheduled.attempts_to_start],
        }

    def _advance_fact_provenance(self, snapshot, attempt) -> Mapping[str, Any]:
        """Materialize citeable analysis observations into one Report Projection."""

        try:
            input_artifact_refs = self.kernel._report_projection_input_refs(snapshot)
            storage = self.kernel._storage_for(snapshot.run_id)
            evidence_records, claim_records, _existing_bindings = storage.read_research_provenance(snapshot.state_version)
            evidence_by_id = {str(item.get("id")): item for item in evidence_records}
            claims_by_statement: dict[str, list[Mapping[str, Any]]] = {}
            for claim in claim_records:
                statement = claim.get("statement")
                if isinstance(statement, str) and claim.get("status") in {"VALIDATED", "PARTIALLY_VALIDATED"}:
                    claims_by_statement.setdefault(statement, []).append(claim)
            source_index = self.kernel.source_index_for(snapshot.run_id)
            fact_groups: list[Mapping[str, Any]] = []
            fact_bindings: list[Mapping[str, Any]] = []
            for node_id, analysis_type, group_id, dom_scope_id in _PROJECTION_ANALYSES:
                address = NodeAddress(("competitor",), node_id)
                state = snapshot.node_states[address]
                origin_ref = state.artifact_refs[-1]
                analysis = self._artifact(snapshot, origin_ref)
                if analysis.get("analysis_type") != analysis_type:
                    raise RuntimeContractError("Analysis Artifact type does not match its node", code="SCHEMA_INVALID", rule="fact_projection_analysis_type")
                observations = analysis.get("observations")
                if not isinstance(observations, list) or not observations or any(not isinstance(item, str) or not item for item in observations):
                    raise RuntimeContractError("Analysis Artifact has no renderable observations", code="INSUFFICIENT_EVIDENCE", rule="fact_projection_observations")
                group_facts: list[Mapping[str, Any]] = []
                group_sources: set[str] = set()
                for index, observation in enumerate(observations):
                    candidates = claims_by_statement.get(observation, ())
                    if len(candidates) != 1:
                        raise RuntimeContractError("Analysis observation does not have exactly one verified Claim", code="INSUFFICIENT_EVIDENCE", rule="fact_projection_claim")
                    claim = candidates[0]
                    claim_refs = (str(claim["id"]),)
                    evidence_refs = tuple(sorted({str(item) for item in claim.get("evidence_ids", ())}))
                    if not evidence_refs or any(reference not in evidence_by_id for reference in evidence_refs):
                        raise RuntimeContractError("Analysis Claim has incomplete Evidence", code="INSUFFICIENT_EVIDENCE", rule="fact_projection_evidence")
                    source_refs = tuple(sorted({str(evidence_by_id[reference].get("source_id")) for reference in evidence_refs}))
                    if not source_refs or any(reference not in source_index for reference in source_refs):
                        raise RuntimeContractError("Analysis Evidence has incomplete Source closure", code="INSUFFICIENT_EVIDENCE", rule="fact_projection_source")
                    pointer = f"/observations/{index}"
                    content_hash = canonical_value_hash(observation)
                    digest = hashlib.sha256(f"{origin_ref}\0{pointer}\0{content_hash}".encode("utf-8")).hexdigest()[:20].upper()
                    binding = {
                        "fact_id": f"FACT-COMP-{digest}",
                        "origin_artifact_ref": origin_ref,
                        "origin_field_pointer": pointer,
                        "content_hash": content_hash,
                        "fact_class": "analysis",
                        "claim_refs": list(claim_refs),
                        "evidence_refs": list(evidence_refs),
                        "source_refs": list(source_refs),
                    }
                    group_facts.append(binding)
                    fact_bindings.append(binding)
                    group_sources.update(source_refs)
                fact_groups.append(
                    {
                        "id": group_id,
                        "section_id": node_id,
                        "dom_scope_id": dom_scope_id,
                        "facts": group_facts,
                        "citation_source_ids": sorted(group_sources),
                    }
                )
            closure = {
                "claim_ids": sorted({claim_id for item in fact_bindings for claim_id in item["claim_refs"]}),
                "evidence_ids": sorted({evidence_id for item in fact_bindings for evidence_id in item["evidence_refs"]}),
                "source_ids": sorted({source_id for item in fact_bindings for source_id in item["source_refs"]}),
            }
            header = _artifact_header(snapshot, attempt, "report_projection", _artifact_id("REPORT-PROJECTION", snapshot.run_id))
            header["created_at"] = self.kernel.clock.now()
            document = {
                "artifact": header,
                "input_state_version": snapshot.state_version + 1,
                "input_artifact_refs": list(input_artifact_refs),
                "fact_groups": fact_groups,
                "citation_closure": closure,
                "verification_status": "PENDING",
                "scoring_status": "NOT_PERFORMED",
            }
            document["artifact"]["content_hash"] = _canonical_hash(document)
            completed = self.kernel.complete_persisted_business_attempt(
                snapshot.run_id,
                attempt.attempt_id,
                (("artifacts/02-research/competitors/report-projection.json", document),),
                fact_binding_records=tuple(fact_bindings),
            )
        except RuntimeContractError as error:
            if error.code == "DEPENDENCY_NOT_READY":
                raise
            return self._blocked_outcome(snapshot, attempt, reason=str(error))
        return {
            "state": completed.to_wire_state(),
            "outcome": "FACT_PROVENANCE_MATERIALIZED",
            "artifact_ref": completed.node_states[attempt.address].artifact_refs[-1],
        }

    def advance(self, run_id: str, attempt_id: str) -> Mapping[str, Any]:
        snapshot = self.kernel.load_run(run_id)
        attempt = next((item for item in snapshot.attempts if item.attempt_id == attempt_id), None)
        if attempt is None:
            raise RuntimeContractError("Competitor Research Attempt does not exist", rule="competitor_attempt")
        state = snapshot.node_states.get(attempt.address)
        if attempt.status is not AttemptStatus.RUNNING or state is None or state.status is not NodeStatus.RUNNING:
            raise RuntimeContractError("Competitor Research Attempt is not active", rule="competitor_attempt_state")
        if attempt.address.graph_path != ("competitor",):
            raise RuntimeContractError("P0-04 service can only execute the Competitor Subgraph", rule="competitor_attempt_scope")
        if attempt.address.node_id == "discovery":
            return self._advance_discovery(snapshot, attempt)
        if attempt.address.node_id == "candidate_ranking":
            return self._advance_ranking(snapshot, attempt)
        if attempt.address.node_id == "deep_dive":
            return self._advance_deep_dive(snapshot, attempt)
        if attempt.address.node_id == "normalizer":
            return self._advance_normalizer(snapshot, attempt)
        if attempt.address.node_id in _ANALYSIS_NODE_TYPES:
            return self._advance_analysis(snapshot, attempt, _ANALYSIS_NODE_TYPES[attempt.address.node_id])
        if attempt.address.node_id == "fact_provenance":
            return self._advance_fact_provenance(snapshot, attempt)
        raise RuntimeContractError("Competitor Research Attempt belongs to a later P0-04 Task", rule="competitor_attempt_scope")
