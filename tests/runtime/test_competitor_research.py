from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from skillgraph_runtime import (
    AdaptiveIdeaShapingService,
    CompetitorResearchService,
    CreateRunCommand,
    FixtureCompetitorResearchProvider,
    FixtureHostLLMProvider,
    NodeAddress,
    RuntimeContractError,
    RuntimeKernel,
    RuntimeOperations,
)
from skillgraph_runtime.domain import GateDecision, NodeStatus
from skillgraph_runtime.storage import RunStorage, declared_workspace_path_matches


ROOT = Path(__file__).resolve().parents[2]


class FixedIds:
    def __init__(self) -> None:
        self.attempt = 0

    def new_run_id(self) -> str:
        return "run_p04"

    def new_attempt_id(self) -> str:
        self.attempt += 1
        return f"ATT-P04-{self.attempt}"


class FixedClock:
    def __init__(self) -> None:
        self.index = 0

    def now(self) -> str:
        self.index += 1
        return (datetime(2026, 8, 20, tzinfo=timezone.utc) + timedelta(seconds=self.index)).strftime("%Y-%m-%dT%H:%M:%SZ")


def full_hypothesis() -> dict:
    return {
        "hypothesis": {
            "idea": {"normalized_summary": "A traceable coding-agent progress observability tool."},
            "problem": {"statement": "Builders cannot see long-running coding-agent progress.", "trigger": "A task runs for many minutes.", "current_alternative": "Read logs manually.", "pain_hypothesis": "Manual log reading hides blockers."},
            "target_users": {"primary": ["AI developer tool builders"], "secondary": ["Engineering managers"]},
            "scenario": {"primary_context": "While a coding agent executes a repository task.", "trigger": "The user needs a status update.", "desired_outcome": "Understand progress and blockers."},
            "jtbd": {"functional": "Inspect execution progress.", "emotional": None, "social": None},
            "value_proposition": {"core_value": "Traceable progress visibility.", "why_better_hypothesis": "It summarizes execution state without guessing."},
            "solution": {"direction_hypothesis": "An observability panel.", "alternatives_considered": ["Raw logs"], "core_mechanism": "Structured runtime events are aggregated into progress state."},
            "scope": {"initial_boundary": "Local coding-agent runs.", "non_goals": ["Autonomous coding"]},
        },
        "assumptions": [{"id": "ASM-USER-001", "type": "user", "claim": "Builders need a concise progress view.", "criticality": "high"}],
        "unknowns": [{"id": "UNK-MARKET-001", "dimension": "market", "question": "Which tools already expose equivalent progress?", "researchable": True}],
        "research_seeds": {"competitor_questions": ["Which coding-agent tools provide progress observability?"], "user_questions": [], "market_questions": ["Which tools already expose equivalent progress?"], "technology_questions": []},
    }


def source(index: int, *, source_type: str | None = None) -> dict:
    identifier = f"SRC-{index:03d}"
    return {
        "id": identifier,
        "source_type": source_type or ("product_page" if index % 2 else "repository"),
        "canonical_url": f"https://example.test/{identifier.lower()}",
        "title": f"Source {index}",
        "publisher": "Example Publisher",
        "author": None,
        "published_at": "2026-08-01T00:00:00Z",
        "accessed_at": "2026-08-20T00:00:00Z",
        "source_tier": 1,
        "access_status": "public",
        "license_or_access_notes": None,
        "content_hash": None,
        "excerpt_or_summary": "Public product information.",
        "excerpt_word_count": 3,
        "freshness_status": "FRESH" if index % 2 else "STALE",
        "untrusted_content": True,
        "contains_personal_data": False,
    }


def candidate(index: int, category: str) -> dict:
    identifier = f"cmp_{index:03d}"
    return {
        "id": identifier,
        "name": f"Competitor {index}",
        "category": category,
        "homepage": f"https://example.test/{identifier}",
        "repository": None,
        "relevance_reason": f"Supports the same observability workflow ({category}).",
        "source_ids": [f"SRC-{index:03d}"],
    }


def deep_dive(raw_candidate: dict) -> dict:
    source_id = raw_candidate["source_ids"][0]
    return {
        "competitor": {"id": raw_candidate["id"], "name": raw_candidate["name"], "category": raw_candidate["category"]},
        "positioning": {"description": "Traceable developer workflow observability."},
        "target_users": ["Developers"],
        "product": {"core_workflow": ["Observe", "Diagnose"], "features": ["Timeline"], "integrations": [], "ux_model": "web"},
        "business": {"pricing": None, "license": None, "monetization": None},
        "traction": {
            "github_stars": {"value": None, "observed_at": "2026-08-20T00:00:00Z", "source_id": None},
            "star_growth_30d": {"value": None, "method": None, "observed_at": "2026-08-20T00:00:00Z", "source_ids": []},
            "contributors": None,
            "releases_90d": None,
        },
        "user_feedback": {"positive": [], "negative": []},
        "strengths": [],
        "weaknesses": [],
        "strategic_threat": {"level": "unknown", "reasoning": "Public evidence is limited."},
        "source_ids": [source_id],
    }


def fixture_catalog() -> dict:
    candidates = [candidate(index, category) for index, category in enumerate(("direct", "indirect", "substitute", "adjacent", "platform_risk"), start=1)]
    catalog = {"discovery": {"sources": [source(index) for index in range(1, 6)], "competitors": candidates}}
    catalog.update({f"deep_dive:{item['id']}": {"sources": [], "deep_dive": deep_dive(item)} for item in candidates})
    return catalog


def gate_document() -> dict:
    return {
        "decision": {
            "id": "DEC-P04-001",
            "date": "2026-08-20T00:05:00Z",
            "gate_id": "gate_research",
            "question": "Approve research scope?",
            "decision": "APPROVE",
            "rationale": ["Scope is approved for deterministic fixture research."],
            "evidence_ids": [],
            "artifact_refs": [],
            "alternatives": ["Cancel"],
            "accepted_risks": [],
            "structured_diff_ref": None,
            "reversible": True,
            "approved_by": {"type": "user", "id": "user-1"},
        }
    }


def services(tmp_path: Path, catalog: dict | None = None, *, host_max_parallel: int = 2):
    kernel = RuntimeKernel(ROOT, storage_root=tmp_path, id_factory=FixedIds(), clock=FixedClock(), host_max_parallel=host_max_parallel)
    idea = AdaptiveIdeaShapingService(kernel, FixtureHostLLMProvider({"*": full_hypothesis()}))
    competitor = CompetitorResearchService(kernel, FixtureCompetitorResearchProvider(catalog or fixture_catalog()))
    return kernel, RuntimeOperations(kernel, idea_shaping=idea, competitor_research=competitor)


def prepare_discovery(tmp_path: Path, catalog: dict | None = None, *, host_max_parallel: int = 2):
    kernel, operations = services(tmp_path, catalog, host_max_parallel=host_max_parallel)
    created = kernel.create_persisted_run(CreateRunCommand("Build a trustworthy coding-agent progress dashboard", "developer_tool"))
    run_id = created.run_id
    initial = kernel.schedule_persisted(run_id)
    operations.execute_p0_03_attempt(run_id, initial.attempts_to_start[0].attempt_id)
    contract = kernel.schedule_persisted(run_id)
    operations.execute_p0_03_attempt(run_id, contract.attempts_to_start[0].attempt_id)
    kernel.submit_persisted_gate_decision(run_id, NodeAddress((), "gate_research"), GateDecision.APPROVE, decision_document=gate_document())
    kernel.schedule_persisted(run_id, requested_nodes=(NodeAddress((), "competitor"),))
    discovery = kernel.schedule_persisted(run_id, requested_nodes=(NodeAddress(("competitor",), "discovery"),))
    assert len(discovery.attempts_to_start) == 1
    return kernel, operations, run_id, discovery.attempts_to_start[0].attempt_id


def test_competitor_research_end_to_end_persists_sources_and_fanout(tmp_path: Path):
    kernel, operations, run_id, discovery_attempt = prepare_discovery(tmp_path)
    discovered = operations.execute_p0_04_attempt(run_id, discovery_attempt)
    assert discovered["outcome"] == "DISCOVERED"
    storage = RunStorage(tmp_path, run_id)
    assert len(storage.read_source_index(kernel.load_run(run_id).state_version)) == 5

    ranking_plan = kernel.schedule_persisted(run_id, requested_nodes=(NodeAddress(("competitor",), "candidate_ranking"),))
    ranked = operations.execute_p0_04_attempt(run_id, ranking_plan.attempts_to_start[0].attempt_id)
    assert ranked["outcome"] == "RANKED"
    assert ranked["selected_competitors"] == ["cmp_001", "cmp_002", "cmp_003", "cmp_004", "cmp_005"]
    assert len(ranked["scheduled_attempt_ids"]) == 2
    snapshot = kernel.load_run(run_id)
    template = NodeAddress(("competitor",), "deep_dive")
    assert snapshot.fanout_instances[template] == tuple(ranked["selected_competitors"])
    ranking = storage.read_artifact(ranked["artifact_ref"])
    assert "Default Ranking Policy v1" in ranking["selection_methodology"]
    assert ranking["excluded_candidates"] == []

    while True:
        snapshot = kernel.load_run(run_id)
        active = [item.attempt_id for item in snapshot.attempts if item.status.value == "RUNNING" and item.address.node_id == "deep_dive"]
        if not active:
            break
        for attempt_id in active:
            result = operations.execute_p0_04_attempt(run_id, attempt_id)
            assert result["outcome"] == "DEEP_DIVE_COMPLETED"
    completed = kernel.load_run(run_id)
    deep_states = [state for address, state in completed.node_states.items() if address.node_id == "deep_dive"]
    assert len(deep_states) == 5 and all(state.status is NodeStatus.VERIFIED for state in deep_states)
    assert all(len(state.artifact_refs) == 1 for state in deep_states)
    assert completed.node_states[NodeAddress(("competitor",), "normalizer")].status in {NodeStatus.READY, NodeStatus.RUNNING}


def test_fanout_and_source_index_survive_kernel_recreation(tmp_path: Path):
    kernel, operations, run_id, discovery_attempt = prepare_discovery(tmp_path)
    operations.execute_p0_04_attempt(run_id, discovery_attempt)
    ranking_plan = kernel.schedule_persisted(run_id, requested_nodes=(NodeAddress(("competitor",), "candidate_ranking"),))
    operations.execute_p0_04_attempt(run_id, ranking_plan.attempts_to_start[0].attempt_id)
    before = kernel.load_run(run_id)

    restored = RuntimeKernel(ROOT, storage_root=tmp_path, id_factory=FixedIds(), clock=FixedClock(), host_max_parallel=2)
    after = restored.load_run(run_id)
    template = NodeAddress(("competitor",), "deep_dive")
    assert after.fanout_instances == before.fanout_instances
    assert len(restored.source_index_for(run_id)) == 5
    resumed = restored.schedule_persisted(run_id)
    assert resumed.next_snapshot.fanout_instances == before.fanout_instances


def test_insufficient_discovery_preserves_artifact_and_blocks(tmp_path: Path):
    catalog = {"discovery": {"sources": [source(1, source_type="product_page")], "competitors": [candidate(index, "direct") for index in range(1, 6)]}}
    kernel, operations, run_id, discovery_attempt = prepare_discovery(tmp_path, catalog)
    outcome = operations.execute_p0_04_attempt(run_id, discovery_attempt)
    snapshot = kernel.load_run(run_id)
    state = snapshot.node_states[NodeAddress(("competitor",), "discovery")]
    assert outcome["outcome"] == "INSUFFICIENT_EVIDENCE"
    assert state.status is NodeStatus.BLOCKED and state.artifact_refs
    assert len(RunStorage(tmp_path, run_id).read_source_index(snapshot.state_version)) == 1


def test_provider_cannot_submit_runtime_authority_or_change_deep_dive_identity(tmp_path: Path):
    forbidden = fixture_catalog()
    forbidden["discovery"] = {"sources": [], "competitors": [], "artifact": {"type": "competitor_candidates"}}
    _kernel, operations, _run_id, discovery_attempt = prepare_discovery(tmp_path / "forbidden", forbidden)
    with pytest.raises(RuntimeContractError) as authority:
        operations.execute_p0_04_attempt(_run_id, discovery_attempt)
    assert authority.value.code == "SECURITY_POLICY_VIOLATION"

    catalog = fixture_catalog()
    catalog["deep_dive:cmp_001"]["deep_dive"]["competitor"]["id"] = "cmp_002"
    kernel, operations, run_id, discovery_attempt = prepare_discovery(tmp_path / "identity", catalog)
    operations.execute_p0_04_attempt(run_id, discovery_attempt)
    ranking_plan = kernel.schedule_persisted(run_id, requested_nodes=(NodeAddress(("competitor",), "candidate_ranking"),))
    operations.execute_p0_04_attempt(run_id, ranking_plan.attempts_to_start[0].attempt_id)
    first_deep = next(item.attempt_id for item in kernel.load_run(run_id).attempts if item.status.value == "RUNNING" and item.address.instance_key == "cmp_001")
    with pytest.raises(RuntimeContractError) as identity:
        operations.execute_p0_04_attempt(run_id, first_deep)
    assert identity.value.rule == "competitor_deep_dive_identity"


def test_directory_declaration_is_contained_and_deep_dive_path_is_instance_bound():
    declared = ("artifacts/02-research/competitors/deep-dives/",)
    assert declared_workspace_path_matches("artifacts/02-research/competitors/deep-dives/cmp_001.yaml", declared)
    assert not declared_workspace_path_matches("artifacts/02-research/competitors/deep-dives", declared)
    assert not declared_workspace_path_matches("artifacts/02-research/competitors/deep-dives-escaped/cmp_001.yaml", declared)


def _complete_p04_through_analysis(tmp_path: Path, *, catalog: dict | None = None, host_max_parallel: int = 2):
    kernel, operations, run_id, discovery_attempt = prepare_discovery(tmp_path, catalog, host_max_parallel=host_max_parallel)
    operations.execute_p0_04_attempt(run_id, discovery_attempt)
    ranking = kernel.schedule_persisted(run_id, requested_nodes=(NodeAddress(("competitor",), "candidate_ranking"),))
    operations.execute_p0_04_attempt(run_id, ranking.attempts_to_start[0].attempt_id)
    while True:
        active = [
            item.attempt_id
            for item in kernel.load_run(run_id).attempts
            if item.status.value == "RUNNING" and item.address.node_id == "deep_dive"
        ]
        if not active:
            break
        for attempt_id in active:
            operations.execute_p0_04_attempt(run_id, attempt_id)

    normalizer = next(
        item.attempt_id
        for item in kernel.load_run(run_id).attempts
        if item.status.value == "RUNNING" and item.address.node_id == "normalizer"
    )
    operations.execute_p0_04_attempt(run_id, normalizer)
    while True:
        active = [
            item.attempt_id
            for item in kernel.load_run(run_id).attempts
            if item.status.value == "RUNNING" and item.address.node_id in {"feature_analysis", "traction_analysis", "review_analysis", "pricing_analysis"}
        ]
        if not active:
            break
        for attempt_id in active:
            operations.execute_p0_04_attempt(run_id, attempt_id)
    return kernel, operations, run_id


def test_normalized_dataset_and_deterministic_analyses_persist_provenance(tmp_path: Path):
    kernel, _operations, run_id = _complete_p04_through_analysis(tmp_path)
    snapshot = kernel.load_run(run_id)
    storage = RunStorage(tmp_path, run_id)

    dataset_state = snapshot.node_states[NodeAddress(("competitor",), "normalizer")]
    dataset = storage.read_artifact(dataset_state.artifact_refs[-1])
    assert [item["id"] for item in dataset["competitors"]] == ["cmp_001", "cmp_002", "cmp_003", "cmp_004", "cmp_005"]
    assert dataset["competitors"][0]["metrics"]["star_growth_30d"]["value"] is None
    assert dataset["competitors"][0]["metrics"]["star_growth_30d"]["observed_at"] == "2026-08-20T00:00:00Z"

    analysis_addresses = tuple(NodeAddress(("competitor",), node_id) for node_id in ("feature_analysis", "traction_analysis", "review_analysis", "pricing_analysis"))
    assert all(snapshot.node_states[address].status is NodeStatus.VERIFIED for address in analysis_addresses)
    feature = storage.read_artifact(snapshot.node_states[analysis_addresses[0]].artifact_refs[-1])
    traction = storage.read_artifact(snapshot.node_states[analysis_addresses[1]].artifact_refs[-1])
    review = storage.read_artifact(snapshot.node_states[analysis_addresses[2]].artifact_refs[-1])
    pricing = storage.read_artifact(snapshot.node_states[analysis_addresses[3]].artifact_refs[-1])
    assert any("coverage" in observation and "0.5" in observation for observation in feature["observations"])
    assert all("Momentum Score" not in observation for observation in traction["observations"])
    assert any("not population rates" in observation for observation in review["observations"])
    assert any("pricing=null" in observation for observation in pricing["observations"])
    assert all(document["evidence_ids"] for document in (feature, traction, review, pricing))

    evidence, claims = storage.read_research_provenance(snapshot.state_version)
    evidence_ids = {item["id"] for item in evidence}
    assert evidence_ids and claims
    assert all(set(item["evidence_ids"]).issubset(evidence_ids) for item in claims)
    assert snapshot.node_states[NodeAddress(("competitor",), "visualization")].status is NodeStatus.READY

    restored = RuntimeKernel(ROOT, storage_root=tmp_path, id_factory=FixedIds(), clock=FixedClock(), host_max_parallel=2)
    recovered_evidence, recovered_claims = RunStorage(tmp_path, run_id).read_research_provenance(restored.load_run(run_id).state_version)
    assert recovered_evidence == evidence and recovered_claims == claims


def test_source_canonicalization_rewrites_aliases_without_fetching(tmp_path: Path):
    catalog = fixture_catalog()
    duplicate = deepcopy(catalog["discovery"]["sources"][0])
    duplicate["id"] = "SRC-ALIAS"
    duplicate["accessed_at"] = "2026-08-21T00:00:00Z"
    catalog["discovery"]["sources"].append(duplicate)
    catalog["discovery"]["competitors"][0]["source_ids"] = ["SRC-ALIAS"]
    kernel, operations, run_id, discovery_attempt = prepare_discovery(tmp_path, catalog)

    operations.execute_p0_04_attempt(run_id, discovery_attempt)
    snapshot = kernel.load_run(run_id)
    candidates = RunStorage(tmp_path, run_id).read_artifact(snapshot.node_states[NodeAddress(("competitor",), "discovery")].artifact_refs[-1])
    assert candidates["competitors"][0]["source_ids"] == ["SRC-001"]
    sources = RunStorage(tmp_path, run_id).read_source_index(snapshot.state_version)
    assert len(sources) == 5
    assert next(item for item in sources if item["id"] == "SRC-001")["accessed_at"] == "2026-08-21T00:00:00Z"


def test_source_canonicalization_rejects_conflicting_immutable_metadata(tmp_path: Path):
    catalog = fixture_catalog()
    duplicate = deepcopy(catalog["discovery"]["sources"][0])
    duplicate["id"] = "SRC-CONFLICT"
    duplicate["title"] = "Conflicting source metadata"
    catalog["discovery"]["sources"].append(duplicate)
    _kernel, operations, _run_id, discovery_attempt = prepare_discovery(tmp_path, catalog)

    with pytest.raises(RuntimeContractError) as captured:
        operations.execute_p0_04_attempt(_run_id, discovery_attempt)
    assert captured.value.rule == "source_index_dedup_conflict"


def test_source_without_url_uses_stable_metadata_identity_and_rewrites_alias(tmp_path: Path):
    catalog = fixture_catalog()
    canonical = catalog["discovery"]["sources"][0]
    canonical["canonical_url"] = None
    duplicate = deepcopy(canonical)
    duplicate["id"] = "SRC-FALLBACK"
    duplicate["accessed_at"] = "2026-08-21T00:00:00Z"
    catalog["discovery"]["sources"].append(duplicate)
    catalog["discovery"]["competitors"][0]["source_ids"] = ["SRC-FALLBACK"]
    kernel, operations, run_id, discovery_attempt = prepare_discovery(tmp_path, catalog)

    operations.execute_p0_04_attempt(run_id, discovery_attempt)
    snapshot = kernel.load_run(run_id)
    candidates = RunStorage(tmp_path, run_id).read_artifact(snapshot.node_states[NodeAddress(("competitor",), "discovery")].artifact_refs[-1])
    sources = RunStorage(tmp_path, run_id).read_source_index(snapshot.state_version)

    assert snapshot.node_states[NodeAddress(("competitor",), "discovery")].status is NodeStatus.VERIFIED
    assert candidates["competitors"][0]["source_ids"] == ["SRC-001"]
    assert len(sources) == 5
    assert next(item for item in sources if item["id"] == "SRC-001")["canonical_url"] is None


@pytest.mark.parametrize(
    ("url", "expected_code"),
    (
        ("https://user:pass@example.test/source", "INPUT_INVALID"),
        ("https://example.test:not-a-port/source", "SCHEMA_INVALID"),
    ),
)
def test_source_canonicalization_rejects_unsafe_or_malformed_urls(tmp_path: Path, url: str, expected_code: str):
    catalog = fixture_catalog()
    catalog["discovery"]["sources"][0]["canonical_url"] = url
    _kernel, operations, run_id, discovery_attempt = prepare_discovery(tmp_path, catalog)

    with pytest.raises(RuntimeContractError) as captured:
        operations.execute_p0_04_attempt(run_id, discovery_attempt)
    assert captured.value.rule == "source_canonical_url"
    assert captured.value.code == expected_code


def test_normalizer_rejects_missing_selected_deep_dive_before_writing_dataset(tmp_path: Path):
    kernel, operations, run_id, discovery_attempt = prepare_discovery(tmp_path)
    operations.execute_p0_04_attempt(run_id, discovery_attempt)
    ranking = kernel.schedule_persisted(run_id, requested_nodes=(NodeAddress(("competitor",), "candidate_ranking"),))
    operations.execute_p0_04_attempt(run_id, ranking.attempts_to_start[0].attempt_id)
    snapshot = kernel.load_run(run_id)
    missing = NodeAddress(("competitor",), "deep_dive", "cmp_001")
    states = dict(snapshot.node_states)
    states[missing] = replace(states[missing], status=NodeStatus.PENDING)
    inconsistent = replace(snapshot, node_states=states)

    with pytest.raises(RuntimeContractError) as captured:
        CompetitorResearchService(kernel)._selected_deep_dives(inconsistent)
    assert captured.value.code == "DEPENDENCY_NOT_READY"
    assert captured.value.rule == "competitor_deep_dive_fanin"


def test_feature_analysis_distinguishes_explicit_feature_workflow_and_absence(tmp_path: Path):
    catalog = fixture_catalog()
    catalog["deep_dive:cmp_001"]["deep_dive"]["product"] = {"core_workflow": ["Observe"], "features": ["Timeline"], "integrations": [], "ux_model": "web"}
    catalog["deep_dive:cmp_002"]["deep_dive"]["product"] = {"core_workflow": ["Timeline"], "features": [], "integrations": [], "ux_model": "web"}
    catalog["deep_dive:cmp_003"]["deep_dive"]["product"] = {"core_workflow": [], "features": [], "integrations": [], "ux_model": "web"}
    kernel, _operations, run_id = _complete_p04_through_analysis(tmp_path, catalog=catalog, host_max_parallel=1)
    snapshot = kernel.load_run(run_id)
    feature = RunStorage(tmp_path, run_id).read_artifact(snapshot.node_states[NodeAddress(("competitor",), "feature_analysis")].artifact_refs[-1])

    timeline = next(item for item in feature["observations"] if item.startswith("Feature coverage 'Timeline'"))
    assert "cmp_001=1.0" in timeline
    assert "cmp_002=0.5" in timeline
    assert "cmp_003=0.0" in timeline


def test_provenance_sidecar_rejects_dangling_or_conflicting_records_and_ignores_future_versions(tmp_path: Path):
    kernel, operations, run_id, discovery_attempt = prepare_discovery(tmp_path)
    operations.execute_p0_04_attempt(run_id, discovery_attempt)
    snapshot = kernel.load_run(run_id)
    storage = RunStorage(tmp_path, run_id)
    evidence = {
        "id": "EV-COMP-UNIT",
        "claim_id": "CL-COMP-UNIT",
        "source_id": "SRC-001",
        "evidence_type": "qualitative",
        "direction": "supports",
        "relevance": "high",
        "reliability": "high",
        "freshness": "high",
        "notes": "Unit-test provenance.",
    }
    claim = {
        "id": "CL-COMP-UNIT",
        "statement": "A source-backed unit claim.",
        "category": "competitor",
        "status": "VALIDATED",
        "confidence": "MEDIUM",
        "evidence_ids": ["EV-COMP-UNIT"],
        "contradiction_ids": [],
    }
    storage.write_research_provenance(
        state_version=snapshot.state_version,
        schema_version=snapshot.contract_version,
        evidence=(evidence,),
        claims=(claim,),
    )
    assert storage.read_research_provenance(snapshot.state_version - 1) == ((), ())
    idempotent_evidence, idempotent_claims = kernel._merged_research_provenance(snapshot, (evidence,), (claim,))
    assert idempotent_evidence == (evidence,)
    assert idempotent_claims == (claim,)

    conflicting = dict(evidence, notes="Different immutable evidence content.")
    with pytest.raises(RuntimeContractError) as captured:
        kernel._merged_research_provenance(snapshot, (conflicting,), ())
    assert captured.value.rule == "provenance_identity"

    dangling = dict(evidence, id="EV-COMP-DANGLING", claim_id="CL-COMP-DANGLING", source_id="SRC-NOT-THERE")
    dangling_claim = dict(claim, id="CL-COMP-DANGLING", evidence_ids=["EV-COMP-DANGLING"])
    with pytest.raises(RuntimeContractError) as captured:
        kernel._merged_research_provenance(snapshot, (dangling,), (dangling_claim,))
    assert captured.value.rule == "provenance_source_ref"
