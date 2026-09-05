from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import shutil

import pytest
import yaml

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
from skillgraph_runtime import graph as graph_module
from skillgraph_runtime.storage import RunStorage, declared_workspace_path_matches
from skillgraph_runtime._validation import validate_contracts as validator_module


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


def services(
    tmp_path: Path,
    catalog: dict | None = None,
    *,
    host_max_parallel: int = 2,
    repository_root: Path = ROOT,
):
    kernel = RuntimeKernel(repository_root, storage_root=tmp_path, id_factory=FixedIds(), clock=FixedClock(), host_max_parallel=host_max_parallel)
    idea = AdaptiveIdeaShapingService(kernel, FixtureHostLLMProvider({"*": full_hypothesis()}))
    competitor = CompetitorResearchService(kernel, FixtureCompetitorResearchProvider(catalog or fixture_catalog()))
    return kernel, RuntimeOperations(kernel, idea_shaping=idea, competitor_research=competitor)


def prepare_discovery(
    tmp_path: Path,
    catalog: dict | None = None,
    *,
    host_max_parallel: int = 2,
    repository_root: Path = ROOT,
    contract_version: str | None = None,
):
    kernel, operations = services(tmp_path, catalog, host_max_parallel=host_max_parallel, repository_root=repository_root)
    created = kernel.create_persisted_run(
        CreateRunCommand("Build a trustworthy coding-agent progress dashboard", "developer_tool", contract_version=contract_version)
    )
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


def _complete_p04_through_analysis(
    tmp_path: Path,
    *,
    catalog: dict | None = None,
    host_max_parallel: int = 2,
    repository_root: Path = ROOT,
    contract_version: str | None = None,
):
    kernel, operations, run_id, discovery_attempt = prepare_discovery(
        tmp_path,
        catalog,
        host_max_parallel=host_max_parallel,
        repository_root=repository_root,
        contract_version=contract_version,
    )
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


def _temporary_v031_repository(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Activate 0.3.1 only inside a disposable contract-root fixture."""

    repository_root = tmp_path / "repository"
    contracts = repository_root / "contracts"
    shutil.copytree(ROOT / "contracts", contracts)
    registry_path = contracts / "registry.yaml"
    registry = yaml.safe_load(registry_path.read_text(encoding="utf-8"))
    versions = registry["registry"]["versions"]
    registry["registry"]["default_new_run_version"] = "0.3.1"
    versions["0.3.0"] = {
        "status": "frozen_previous",
        "bundle_root": "contracts/0.3.0",
        "new_runs_allowed": False,
        "resume_allowed": True,
        "audit_allowed": True,
    }
    versions["0.3.1"] = {
        "status": "current",
        "bundle_root": "contracts/0.3.1",
        "new_runs_allowed": True,
        "resume_allowed": True,
        "audit_allowed": True,
    }
    registry_path.write_text(yaml.safe_dump(registry, sort_keys=False), encoding="utf-8")

    schema_path = contracts / "registry.schema.json"
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    registry_schema = schema["properties"]["registry"]
    registry_schema["properties"]["default_new_run_version"] = {"const": "0.3.1"}
    version_schema = registry_schema["properties"]["versions"]
    version_schema["required"].append("0.3.1")
    version_schema["properties"]["0.3.0"] = {
        "$ref": "#/$defs/version_entry",
        "properties": {
            "status": {"const": "frozen_previous"},
            "bundle_root": {"const": "contracts/0.3.0"},
            "new_runs_allowed": {"const": False},
            "resume_allowed": {"const": True},
            "audit_allowed": {"const": True},
        },
    }
    version_schema["properties"]["0.3.1"] = {
        "$ref": "#/$defs/version_entry",
        "properties": {
            "status": {"const": "current"},
            "bundle_root": {"const": "contracts/0.3.1"},
            "new_runs_allowed": {"const": True},
            "resume_allowed": {"const": True},
            "audit_allowed": {"const": True},
        },
    }
    schema_path.write_text(json.dumps(schema, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    monkeypatch.setattr(validator_module, "ROOT", repository_root)
    monkeypatch.delitem(validator_module.STAGED_STATIC_BUNDLE_ROOTS, "0.3.1")
    # Static Bundle closure is verified against the real repository separately.
    # This disposable Registry fixture exists solely to exercise the future
    # Runtime graph, and lacks the root-level frozen-document audit inputs.
    monkeypatch.setattr(graph_module, "validate_bundle", lambda _context, *, registry: ([], 0))
    return repository_root


def _complete_v031_through_fact_provenance(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    repository_root = _temporary_v031_repository(tmp_path, monkeypatch)
    kernel, operations, run_id = _complete_p04_through_analysis(
        tmp_path / "runtime",
        repository_root=repository_root,
        contract_version="0.3.1",
    )
    fact_plan = kernel.schedule_persisted(run_id, requested_nodes=(NodeAddress(("competitor",), "fact_provenance"),))
    assert len(fact_plan.attempts_to_start) == 1
    result = operations.execute_p0_04_attempt(run_id, fact_plan.attempts_to_start[0].attempt_id)
    assert result["outcome"] == "FACT_PROVENANCE_MATERIALIZED"
    return repository_root, kernel, operations, run_id


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

    evidence, claims, fact_bindings = storage.read_research_provenance(snapshot.state_version)
    evidence_ids = {item["id"] for item in evidence}
    assert evidence_ids and claims
    assert fact_bindings == ()
    assert all(set(item["evidence_ids"]).issubset(evidence_ids) for item in claims)
    assert snapshot.node_states[NodeAddress(("competitor",), "visualization")].status is NodeStatus.READY

    restored = RuntimeKernel(ROOT, storage_root=tmp_path, id_factory=FixedIds(), clock=FixedClock(), host_max_parallel=2)
    recovered_evidence, recovered_claims, recovered_bindings = RunStorage(tmp_path, run_id).read_research_provenance(restored.load_run(run_id).state_version)
    assert recovered_evidence == evidence and recovered_claims == claims and recovered_bindings == fact_bindings


def test_fact_provenance_materializes_a_closed_projection_in_an_isolated_v031_run(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    repository_root, kernel, _operations, run_id = _complete_v031_through_fact_provenance(tmp_path, monkeypatch)
    snapshot = kernel.load_run(run_id)
    storage = RunStorage(tmp_path / "runtime", run_id)
    state = snapshot.node_states[NodeAddress(("competitor",), "fact_provenance")]
    assert state.status is NodeStatus.VERIFIED
    projection_ref = state.artifact_refs[-1]
    projection = storage.read_artifact(projection_ref)
    assert projection["artifact"]["type"] == "report_projection"
    assert projection["input_state_version"] == snapshot.state_version
    assert projection["input_artifact_refs"] == list(kernel._report_projection_input_refs(snapshot))
    assert [(group["id"], group["dom_scope_id"]) for group in projection["fact_groups"]] == [
        ("FG-FEATURE", "analysis-feature"),
        ("FG-TRACTION", "analysis-traction"),
        ("FG-REVIEW", "analysis-review"),
        ("FG-PRICING", "analysis-pricing"),
    ]
    evidence, claims, fact_bindings = storage.read_research_provenance(snapshot.state_version)
    assert evidence and claims and fact_bindings
    projected_facts = [fact for group in projection["fact_groups"] for fact in group["facts"]]
    assert tuple(sorted(projected_facts, key=lambda item: item["fact_id"])) == fact_bindings
    assert projection["citation_closure"] == {
        "claim_ids": sorted({claim_id for item in fact_bindings for claim_id in item["claim_refs"]}),
        "evidence_ids": sorted({evidence_id for item in fact_bindings for evidence_id in item["evidence_refs"]}),
        "source_ids": sorted({source_id for item in fact_bindings for source_id in item["source_refs"]}),
    }
    manifest = storage._manifest()
    assert manifest["current_artifacts"]["report_projection"]["artifact_ref"] == projection_ref

    restored = RuntimeKernel(repository_root, storage_root=tmp_path / "runtime", id_factory=FixedIds(), clock=FixedClock())
    assert restored.load_run(run_id).state_version == snapshot.state_version
    assert yaml.safe_load((ROOT / "contracts" / "registry.yaml").read_text(encoding="utf-8"))["registry"]["default_new_run_version"] == "0.3.0"


def test_fact_provenance_fails_closed_when_an_observation_claim_is_missing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    repository_root = _temporary_v031_repository(tmp_path, monkeypatch)
    kernel, operations, run_id = _complete_p04_through_analysis(
        tmp_path / "runtime",
        repository_root=repository_root,
        contract_version="0.3.1",
    )
    snapshot = kernel.load_run(run_id)
    storage = RunStorage(tmp_path / "runtime", run_id)
    sidecar_path = max(
        storage._path("runtime/research-provenance").glob("*.json"),
        key=lambda path: int(path.stem),
    )
    sidecar = json.loads(sidecar_path.read_text(encoding="utf-8"))
    sidecar["claims"] = sidecar["claims"][1:]
    sidecar_path.write_text(json.dumps(sidecar, ensure_ascii=False, sort_keys=True), encoding="utf-8")

    plan = kernel.schedule_persisted(run_id, requested_nodes=(NodeAddress(("competitor",), "fact_provenance"),))
    result = operations.execute_p0_04_attempt(run_id, plan.attempts_to_start[0].attempt_id)
    assert result["outcome"] == "INSUFFICIENT_EVIDENCE"
    manifest = storage._manifest()
    assert "report_projection" not in manifest["current_artifacts"]


def test_fact_provenance_invalidation_removes_projection_and_effective_stale_bindings(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    _repository_root, kernel, _operations, run_id = _complete_v031_through_fact_provenance(tmp_path, monkeypatch)
    storage = RunStorage(tmp_path / "runtime", run_id)
    before = kernel.load_run(run_id)
    feature_address = NodeAddress(("competitor",), "feature_analysis")
    feature_ref = before.node_states[feature_address].artifact_refs[-1]
    result = kernel.invalidate_persisted_downstream(run_id, feature_address)
    after = kernel.load_run(run_id)
    assert NodeAddress(("competitor",), "fact_provenance") in result.invalidated
    assert after.node_states[NodeAddress(("competitor",), "fact_provenance")].status is NodeStatus.INVALIDATED
    assert "report_projection" not in storage._manifest()["current_artifacts"]
    _evidence, _claims, bindings = storage.read_research_provenance(after.state_version)
    assert bindings and all(binding["origin_artifact_ref"] != feature_ref for binding in bindings)


def test_fact_provenance_sidecar_reads_legacy_records_and_rejects_conflicting_bindings(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    storage = RunStorage(tmp_path, "run_fact_legacy")
    storage._write_immutable_json(
        "runtime/research-provenance/1.json",
        {"schema_version": "0.3.0", "state_version": 1, "evidence": [], "claims": []},
    )
    assert storage.read_research_provenance(1) == ((), (), ())

    _repository_root, kernel, _operations, run_id = _complete_v031_through_fact_provenance(tmp_path / "active", monkeypatch)
    snapshot = kernel.load_run(run_id)
    _evidence, _claims, bindings = RunStorage(tmp_path / "active" / "runtime", run_id).read_research_provenance(snapshot.state_version)
    conflicting = dict(bindings[0], content_hash="sha256:" + "0" * 64)
    with pytest.raises(RuntimeContractError) as captured:
        kernel._merged_research_provenance(snapshot, (), (), fact_binding_records=(conflicting,))
    assert captured.value.rule == "fact_binding_identity"


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
    assert storage.read_research_provenance(snapshot.state_version - 1) == ((), (), ())
    idempotent_evidence, idempotent_claims, idempotent_bindings = kernel._merged_research_provenance(snapshot, (evidence,), (claim,))
    assert idempotent_evidence == (evidence,)
    assert idempotent_claims == (claim,)
    assert idempotent_bindings == ()

    conflicting = dict(evidence, notes="Different immutable evidence content.")
    with pytest.raises(RuntimeContractError) as captured:
        kernel._merged_research_provenance(snapshot, (conflicting,), ())
    assert captured.value.rule == "provenance_identity"

    dangling = dict(evidence, id="EV-COMP-DANGLING", claim_id="CL-COMP-DANGLING", source_id="SRC-NOT-THERE")
    dangling_claim = dict(claim, id="CL-COMP-DANGLING", evidence_ids=["EV-COMP-DANGLING"])
    with pytest.raises(RuntimeContractError) as captured:
        kernel._merged_research_provenance(snapshot, (dangling,), (dangling_claim,))
    assert captured.value.rule == "provenance_source_ref"
