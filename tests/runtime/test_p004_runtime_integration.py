from __future__ import annotations

from copy import deepcopy
import hashlib
import json
from pathlib import Path
import shutil

import pytest
import yaml

from skillgraph_runtime import (
    ChartRenderingCore,
    NativeChartRenderer,
    RuntimeContractError,
)
from skillgraph_runtime import graph as graph_module
from skillgraph_runtime import operations as operations_module
from skillgraph_runtime.chart_rendering import ChartRenderingProposal
from skillgraph_runtime.domain import CreateRunCommand, NodeAddress, NodeStatus, deep_thaw
from skillgraph_runtime.runtime_integration import StagedP004RuntimeIntegration
from skillgraph_runtime.scoring import IndependentScoreVerifier, load_profile_rubric, validate_dimension_judgment
from skillgraph_runtime.storage import RunStorage
from skillgraph_runtime._validation import validate_contracts as validator_module

from test_competitor_research import FixedClock, FixedIds, _complete_p04_through_analysis, fixture_catalog, services


ROOT = Path(__file__).resolve().parents[2]


def _temporary_v032_repository(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    repository_root = tmp_path / "repository"
    contracts = repository_root / "contracts"
    shutil.copytree(ROOT / "contracts", contracts)
    registry_path = contracts / "registry.yaml"
    registry = yaml.safe_load(registry_path.read_text(encoding="utf-8"))
    versions = registry["registry"]["versions"]
    registry["registry"]["default_new_run_version"] = "0.3.2"
    versions["0.3.0"] = {
        "status": "frozen_previous",
        "bundle_root": "contracts/0.3.0",
        "new_runs_allowed": False,
        "resume_allowed": True,
        "audit_allowed": True,
    }
    versions["0.3.2"] = {
        "status": "current",
        "bundle_root": "contracts/0.3.2",
        "new_runs_allowed": True,
        "resume_allowed": True,
        "audit_allowed": True,
    }
    registry_path.write_text(yaml.safe_dump(registry, sort_keys=False), encoding="utf-8")
    schema_path = contracts / "registry.schema.json"
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    registry_schema = schema["properties"]["registry"]
    registry_schema["properties"]["default_new_run_version"] = {"const": "0.3.2"}
    version_schema = registry_schema["properties"]["versions"]
    version_schema["required"].append("0.3.2")
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
    version_schema["properties"]["0.3.2"] = {
        "$ref": "#/$defs/version_entry",
        "properties": {
            "status": {"const": "current"},
            "bundle_root": {"const": "contracts/0.3.2"},
            "new_runs_allowed": {"const": True},
            "resume_allowed": {"const": True},
            "audit_allowed": {"const": True},
        },
    }
    schema_path.write_text(json.dumps(schema, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    monkeypatch.setattr(validator_module, "ROOT", repository_root)
    monkeypatch.delitem(validator_module.STAGED_STATIC_BUNDLE_ROOTS, "0.3.2")
    monkeypatch.setattr(graph_module, "validate_bundle", lambda _context, *, registry: ([], 0))
    return repository_root


def _header(kernel, snapshot, attempt_id: str, artifact_id: str, artifact_type: str, skill: str) -> dict:
    return {
        "id": artifact_id,
        "type": artifact_type,
        "schema_version": "0.3.2",
        "version": 1,
        "produced_by": {"skill": skill, "attempt": attempt_id},
        "created_at": kernel.clock.now(),
        "supersedes": None,
        "status": "active",
    }


def _hashed(kernel, document: dict) -> dict:
    result = deepcopy(document)
    result["artifact"]["content_hash"] = kernel._artifact_content_hash(result)
    return result


def _chart_request(kernel, snapshot, attempt_id: str, chart_type: str, index: int, fact: dict) -> dict:
    kinds = {
        "feature_matrix": ("matrix", "competitor_by_dimension_cells", {"competitor_id": "cmp_001", "dimension_id": "workflow_fit", "value": 0.8}),
        "positioning_map": ("scatter", "competitor_xy_points", {"competitor_id": "cmp_001", "x_value": 0.7, "y_value": 0.8, "x_label": "Workflow fit", "y_label": "Maturity"}),
        "momentum_comparison": ("bar", "category_values", {"category": "cmp_001", "series": "Momentum", "value": 7}),
        "oss_activity": ("line", "time_series_values", {"timestamp": "2026-08-20T00:00:00Z", "series": "cmp_001", "value": 5}),
    }
    renderer_kind, data_contract, row = kinds[chart_type]
    row["evidence_refs"] = list(fact["evidence_refs"])
    root = f"artifacts/02-research/competitors/visualizations/{chart_type}"
    return {
        "artifact": _header(kernel, snapshot, attempt_id, f"ART-CHART-{index:03d}", "chart_bundle", "competitor-chart-rendering"),
        "chart_instance_id": f"chart_{index:03d}",
        "chart_spec": {
            "chart_id": chart_type,
            "renderer_kind": renderer_kind,
            "data_contract": data_contract,
            "title": chart_type.replace("_", " ").title(),
            "description": "Deterministic chart derived from the verified projection.",
            "width": 960,
            "height": 540,
            "style_tokens": {"theme": "report_default"},
        },
        "chart_data": {"data_contract": data_contract, "rows": [row]},
        "data_ref": f"{root}/data.json",
        "chart_spec_ref": f"{root}/chart-spec.json",
        "svg_ref": f"{root}/chart.svg",
        "insight_ref": f"{root}/insight.md",
        "png_requested": False,
        "observation": f"Verified observation for {chart_type}.",
        "interpretation": "Interpretation is limited to cited evidence.",
        "product_implication": "Use the verified comparison in product decisions.",
        "confidence": "MEDIUM",
        "claim_refs": list(fact["claim_refs"]),
        "evidence_ids": list(fact["evidence_refs"]),
        "limitations": ["Only verified Runtime facts are rendered."],
    }


def _through_fact_provenance(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    repository_root = _temporary_v032_repository(tmp_path, monkeypatch)
    runtime_root = tmp_path / "runtime"
    catalog = fixture_catalog()
    for source in catalog["discovery"]["sources"]:
        source["citation_metadata"] = {
            "publisher_short_name": "Example Publisher",
            "excerpt": "Public product information.",
            "local_favicon_ref": None,
        }
    kernel, operations, run_id = _complete_p04_through_analysis(
        runtime_root,
        catalog=catalog,
        repository_root=repository_root,
        contract_version="0.3.2",
    )
    fact_plan = kernel.schedule_persisted(run_id, requested_nodes=(NodeAddress(("competitor",), "fact_provenance"),))
    result = operations.execute_p0_04_attempt(run_id, fact_plan.attempts_to_start[0].attempt_id)
    assert result["outcome"] == "FACT_PROVENANCE_MATERIALIZED"
    return repository_root, runtime_root, kernel, operations, run_id


def _through_report(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    repository_root, runtime_root, kernel, operations, run_id = _through_fact_provenance(tmp_path, monkeypatch)
    storage = RunStorage(runtime_root, run_id)
    snapshot = kernel.load_run(run_id)
    projection_ref = storage._manifest()["current_artifacts"]["report_projection"]["artifact_ref"]
    projection = storage.read_artifact(projection_ref)
    fact = projection["fact_groups"][0]["facts"][0]
    chart_plan = kernel.schedule_persisted(run_id, requested_nodes=(NodeAddress(("competitor",), "chart_rendering"),))
    chart_attempt = chart_plan.attempts_to_start[0].attempt_id
    chart_snapshot = kernel.load_run(run_id)
    proposal = ChartRenderingCore(NativeChartRenderer.from_bundle_root(repository_root / "contracts" / "0.3.2")).build_collection(
        report_projection=projection,
        collection_artifact=_header(kernel, chart_snapshot, chart_attempt, "ART-CHART-COLLECTION-RUNTIME", "chart_bundle_collection", "competitor-chart-rendering"),
        charts=[_chart_request(kernel, chart_snapshot, chart_attempt, chart_type, index, fact) for index, chart_type in enumerate(("feature_matrix", "positioning_map", "momentum_comparison", "oss_activity"), start=1)],
    )
    chart_result = operations.commit_p0_04_chart_rendering(run_id, chart_attempt, proposal, idempotency_key="chart-runtime-001")
    projection_plan = kernel.schedule_persisted(run_id, requested_nodes=(NodeAddress(("competitor",), "report_publication_projection"),))
    publication_result = operations.commit_p0_04_publication_projection(
        run_id, projection_plan.attempts_to_start[0].attempt_id, idempotency_key="publication-runtime-001"
    )
    report_plan = kernel.schedule_persisted(run_id, requested_nodes=(NodeAddress(("competitor",), "report_builder"),))
    report_result = operations.commit_p0_04_report(
        run_id,
        report_plan.attempts_to_start[0].attempt_id,
        idempotency_key="report-runtime-001",
        expected_base_report_ref=None,
    )
    return repository_root, runtime_root, kernel, operations, run_id, proposal, chart_result, publication_result, report_result


def test_staged_runtime_commits_chart_projection_and_offline_report(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    repository_root, runtime_root, kernel, operations, run_id, proposal, chart, publication, report = _through_report(tmp_path, monkeypatch)
    snapshot = kernel.load_run(run_id)
    storage = RunStorage(runtime_root, run_id)
    manifest = storage._manifest()
    assert snapshot.contract_version == "0.3.2"
    assert {"chart_bundle_collection", "report_publication_projection", "competitor_report"} <= set(manifest["current_artifacts"])
    assert operations.commit_p0_04_chart_rendering(run_id, next(item.attempt_id for item in snapshot.attempts if item.address.node_id == "chart_rendering"), proposal, idempotency_key="chart-runtime-001")["replayed"] is True
    assert operations.commit_p0_04_publication_projection(
        run_id,
        next(item.attempt_id for item in snapshot.attempts if item.address.node_id == "report_publication_projection"),
        idempotency_key="publication-runtime-001",
    )["replayed"] is True
    assert operations.commit_p0_04_report(
        run_id,
        next(item.attempt_id for item in snapshot.attempts if item.address.node_id == "report_builder"),
        idempotency_key="report-runtime-001",
        expected_base_report_ref=None,
    )["replayed"] is True
    report_entry = manifest["current_artifacts"]["competitor_report"]
    report_document = storage.read_artifact(report["artifact_ref"])
    assert report_document["publication_kind"] == "INITIAL"
    assert report_document["verification"] == {"status": "PENDING", "verification_ref": None}
    assert report_document["scoring"] == {"status": "NOT_PERFORMED", "score_collection_ref": None}
    report_assets = storage.read_asset_inventory(
        artifact_ref=report["artifact_ref"],
        inventory_ref=report_entry["asset_inventory_ref"],
        inventory_hash=report_entry["asset_inventory_hash"],
    )
    html = report_assets[report_document["report_root_ref"]].decode("utf-8")
    assert "<script" not in html.lower() and "https://" in html
    assert all("ideatoproduct-report-stage" not in path for path in report_assets)
    assert kernel.recover_run(run_id).uncommitted_event_offsets == ()
    assert yaml.safe_load((ROOT / "contracts" / "registry.yaml").read_text(encoding="utf-8"))["registry"]["default_new_run_version"] == "0.3.0"
    assert repository_root != ROOT
    receipt_path = storage._path(report_entry["mutation_receipt_ref"])
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    receipt["request_hash"] = "sha256:" + "0" * 64
    receipt_path.write_text(json.dumps(receipt, sort_keys=True), encoding="utf-8")
    with pytest.raises(RuntimeContractError) as receipt_tamper:
        kernel.load_run(run_id)
    assert receipt_tamper.value.rule == "mutation_receipt"


def test_same_key_changed_input_and_tampered_asset_fail_closed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    _repo, runtime_root, kernel, operations, run_id, proposal, _chart, _publication, _report = _through_report(tmp_path, monkeypatch)
    snapshot = kernel.load_run(run_id)
    chart_attempt = next(item.attempt_id for item in snapshot.attempts if item.address.node_id == "chart_rendering")
    changed_collection = proposal.to_wire_document()
    changed_collection["bundles"][0]["limitations"].append("A second valid disclosure changes the request.")
    changed = ChartRenderingProposal(changed_collection, dict(proposal.assets), proposal.input_artifact_refs)
    with pytest.raises(RuntimeContractError) as conflict:
        operations.commit_p0_04_chart_rendering(run_id, chart_attempt, changed, idempotency_key="chart-runtime-001")
    assert conflict.value.code == "IDEMPOTENCY_CONFLICT"
    storage = RunStorage(runtime_root, run_id)
    entry = storage._manifest()["current_artifacts"]["chart_bundle_collection"]
    inventory = storage._read_json(entry["asset_inventory_ref"])
    logical = inventory["assets"][0]["logical_path"]
    physical = storage._path(f"runtime/artifact-assets/{entry['artifact_ref']}/payload/{logical}")
    physical.write_bytes(b"tampered")
    with pytest.raises(RuntimeContractError) as tampered:
        kernel.load_run(run_id)
    assert tampered.value.rule == "asset_hash"


def test_upstream_invalidation_removes_all_downstream_current_outputs(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    _repo, runtime_root, kernel, _operations, run_id, *_rest = _through_report(tmp_path, monkeypatch)
    result = kernel.invalidate_persisted_downstream(run_id, NodeAddress(("competitor",), "feature_analysis"))
    assert NodeAddress(("competitor",), "chart_rendering") in result.invalidated
    manifest = RunStorage(runtime_root, run_id)._manifest()
    assert not {"report_projection", "chart_bundle_collection", "report_publication_projection", "competitor_report"}.intersection(manifest["current_artifacts"])


def test_stale_report_base_fails_without_changing_current_manifest(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    _repo, runtime_root, _kernel, operations, run_id, *_rest = _through_report(tmp_path, monkeypatch)
    storage = RunStorage(runtime_root, run_id)
    before = deepcopy(storage._manifest())
    snapshot = _kernel.load_run(run_id)
    attempt_id = next(item.attempt_id for item in snapshot.attempts if item.address.node_id == "report_builder")
    with pytest.raises(RuntimeContractError) as stale:
        operations.commit_p0_04_report(
            run_id,
            attempt_id,
            idempotency_key="report-stale-runtime-001",
            expected_base_report_ref="ART-COMPETITOR-REPORT-STALE@1",
        )
    assert stale.value.code == "STATE_VERSION_CONFLICT" and stale.value.rule == "report_cas"
    assert storage._manifest() == before


def test_pre_manifest_crash_reuses_identical_objects_and_manifest_is_only_commit_point(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    _repo, runtime_root, kernel, operations, run_id = _through_fact_provenance(tmp_path, monkeypatch)
    storage = RunStorage(runtime_root, run_id)
    snapshot = kernel.load_run(run_id)
    projection = storage.read_artifact(storage._manifest()["current_artifacts"]["report_projection"]["artifact_ref"])
    fact = projection["fact_groups"][0]["facts"][0]
    plan = kernel.schedule_persisted(run_id, requested_nodes=(NodeAddress(("competitor",), "chart_rendering"),))
    attempt_id = plan.attempts_to_start[0].attempt_id
    current = kernel.load_run(run_id)
    proposal = ChartRenderingCore(NativeChartRenderer.from_bundle_root(kernel.repository_root / "contracts" / "0.3.2")).build_collection(
        report_projection=projection,
        collection_artifact=_header(kernel, current, attempt_id, "ART-CHART-COLLECTION-CRASH", "chart_bundle_collection", "competitor-chart-rendering"),
        charts=[_chart_request(kernel, current, attempt_id, "feature_matrix", 1, fact)],
    )
    original = RunStorage.commit_snapshot
    crashed = False

    def fail_once(self, *args, **kwargs):
        nonlocal crashed
        if not crashed:
            crashed = True
            raise RuntimeError("injected before Manifest replacement")
        return original(self, *args, **kwargs)

    monkeypatch.setattr(RunStorage, "commit_snapshot", fail_once)
    with pytest.raises(RuntimeError, match="injected"):
        operations.commit_p0_04_chart_rendering(run_id, attempt_id, proposal, idempotency_key="chart-crash-001")
    assert "chart_bundle_collection" not in storage._manifest()["current_artifacts"]
    recovered = operations.commit_p0_04_chart_rendering(run_id, attempt_id, proposal, idempotency_key="chart-crash-001")
    assert recovered["replayed"] is False
    assert RunStorage(runtime_root, run_id)._manifest()["current_artifacts"]["chart_bundle_collection"]["artifact_ref"] == recovered["artifact_ref"]
    events = RunStorage(runtime_root, run_id).event_records()
    assert sum(item["event"] == "CHART_COLLECTION_COMMITTED" for item in events) == 1
    assert sum(item["event"] == "ARTIFACT_ASSETS_WRITTEN" and item.get("artifact") == recovered["artifact_ref"] for item in events) == 1


def test_post_manifest_exception_replays_from_receipt_without_duplicate_state(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    _repo, _runtime_root, kernel, operations, run_id = _through_fact_provenance(tmp_path, monkeypatch)
    plan = kernel.schedule_persisted(run_id, requested_nodes=(NodeAddress(("competitor",), "chart_rendering"),))
    attempt_id = plan.attempts_to_start[0].attempt_id
    snapshot = kernel.load_run(run_id)
    storage = kernel._storage_for(run_id)
    projection = storage.read_artifact(storage._manifest()["current_artifacts"]["report_projection"]["artifact_ref"])
    fact = projection["fact_groups"][0]["facts"][0]
    proposal = ChartRenderingCore(NativeChartRenderer.from_bundle_root(kernel.repository_root / "contracts" / "0.3.2")).build_collection(
        report_projection=projection,
        collection_artifact=_header(kernel, snapshot, attempt_id, "ART-CHART-COLLECTION-AFTER", "chart_bundle_collection", "competitor-chart-rendering"),
        charts=[_chart_request(kernel, snapshot, attempt_id, "feature_matrix", 1, fact)],
    )
    original = kernel.complete_persisted_business_attempt

    def commit_then_raise(*args, **kwargs):
        original(*args, **kwargs)
        raise RuntimeError("injected after Manifest replacement")

    monkeypatch.setattr(kernel, "complete_persisted_business_attempt", commit_then_raise)
    with pytest.raises(RuntimeError, match="after Manifest"):
        operations.commit_p0_04_chart_rendering(run_id, attempt_id, proposal, idempotency_key="chart-after-001")
    committed_version = kernel.load_run(run_id).state_version
    replay = operations.commit_p0_04_chart_rendering(run_id, attempt_id, proposal, idempotency_key="chart-after-001")
    assert replay["replayed"] is True and kernel.load_run(run_id).state_version == committed_version


def _score_document(kernel, snapshot, attempt_id: str, artifact_id: str, artifact_type: str, skill: str, fields: dict) -> dict:
    return _hashed(kernel, {"artifact": _header(kernel, snapshot, attempt_id, artifact_id, artifact_type, skill), **fields})


def test_runtime_owned_post_verifier_transparent_score_uses_persisted_claim_categories(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    _repo, runtime_root, kernel, operations, run_id = _through_fact_provenance(tmp_path, monkeypatch)
    storage = RunStorage(runtime_root, run_id)
    projection = storage.read_artifact(storage._manifest()["current_artifacts"]["report_projection"]["artifact_ref"])
    fact = projection["fact_groups"][0]["facts"][0]
    rubric = load_profile_rubric(kernel.repository_root / "contracts" / "0.3.2", "developer_tool@0.3.2")
    categories = {item["id"]: item["category"] for item in storage.read_research_provenance(kernel.load_run(run_id).state_version)[1]}
    score_plan = kernel.schedule_persisted(run_id, requested_nodes=(NodeAddress(("competitor",), "scoring"),))
    score_attempt = score_plan.attempts_to_start[0].attempt_id
    judgment_refs = []
    proposals = []
    for index, dimension in enumerate(rubric.dimension_ids[:4], start=1):
        raw = {
            "competitor_id": "cmp_001",
            "rubric_ref": rubric.rubric_ref,
            "rubric_version": rubric.rubric_version,
            "dimension_id": dimension,
            "judgment_status": "SCORED",
            "score": 6 + index,
            "claim_refs": list(fact["claim_refs"]),
            "evidence_refs": list(fact["evidence_refs"]),
            "rationale": "Bounded judgment supported by persisted Runtime evidence.",
        }
        validated = validate_dimension_judgment(raw, projection, rubric, categories)
        proposals.append(raw)
        snapshot = kernel.load_run(run_id)
        document = _score_document(kernel, snapshot, score_attempt, f"ART-JUDGMENT-RUNTIME-{index:03d}", "dimension_judgment", "competitor-scoring", validated.to_document_fields())
        if index < 4:
            stored = kernel.write_typed_artifact(run_id, score_attempt, f"artifacts/02-research/competitors/scoring/judgments/{index}.json", document)
            judgment_refs.append(stored.artifact_ref)
        else:
            completed = kernel.complete_persisted_business_attempt(run_id, score_attempt, ((f"artifacts/02-research/competitors/scoring/judgments/{index}.json", document),))
            judgment_refs.append(completed.node_states[NodeAddress(("competitor",), "scoring")].artifact_refs[-1])
    verifier_plan = kernel.schedule_persisted(run_id, requested_nodes=(NodeAddress(("competitor",), "score_verifier"),))
    verifier_attempt = verifier_plan.attempts_to_start[0].attempt_id
    verification_refs = []
    verifier = IndependentScoreVerifier()
    for index, (judgment_ref, raw) in enumerate(zip(judgment_refs, proposals), start=1):
        decision = verifier.verify(judgment_ref, raw, projection, rubric, claim_category_index=categories)
        snapshot = kernel.load_run(run_id)
        document = _score_document(kernel, snapshot, verifier_attempt, f"ART-SCORE-VERIFICATION-RUNTIME-{index:03d}", "score_verification", "competitor-score-verifier", decision.to_document_fields())
        if index < 4:
            stored = kernel.write_typed_artifact(run_id, verifier_attempt, f"artifacts/02-research/competitors/scoring/verifications/{index}.json", document)
            verification_refs.append(stored.artifact_ref)
        else:
            completed = kernel.complete_persisted_business_attempt(run_id, verifier_attempt, ((f"artifacts/02-research/competitors/scoring/verifications/{index}.json", document),))
            verification_refs.append(completed.node_states[NodeAddress(("competitor",), "score_verifier")].artifact_refs[-1])
    result = operations.commit_p0_04_transparent_score(
        run_id,
        score_attempt,
        idempotency_key="transparent-score-runtime-001",
        competitor_id="cmp_001",
        judgment_verification_refs=tuple(zip(judgment_refs, verification_refs)),
    )
    score = storage.read_artifact(result["artifact_ref"])
    assert score["status"] == "PARTIAL" and score["coverage"] == 0.8 and score["rank"] == 1
    assert score["artifact"]["produced_by"] == {"skill": "competitor-scoring", "attempt": score_attempt}
    assert kernel.load_run(run_id).node_states[NodeAddress(("competitor",), "score_verifier")].status is NodeStatus.VERIFIED
    version = kernel.load_run(run_id).state_version
    replay = operations.commit_p0_04_transparent_score(
        run_id,
        score_attempt,
        idempotency_key="transparent-score-runtime-001",
        competitor_id="cmp_001",
        judgment_verification_refs=tuple(zip(judgment_refs, verification_refs)),
    )
    assert replay["replayed"] is True and kernel.load_run(run_id).state_version == version
    invalidated = kernel.invalidate_persisted_downstream(run_id, NodeAddress(("competitor",), "feature_analysis"))
    assert NodeAddress(("competitor",), "scoring") in invalidated.invalidated
    assert "transparent_score" not in storage._manifest()["current_artifacts"]


def test_runtime_operations_integration_is_embedding_only():
    assert not {
        "commit_p0_04_chart_rendering",
        "commit_p0_04_publication_projection",
        "commit_p0_04_report",
        "commit_p0_04_transparent_score",
    }.intersection(operations_module._MUTATING | operations_module._UNIMPLEMENTED)
    assert StagedP004RuntimeIntegration.__name__ == "StagedP004RuntimeIntegration"


@pytest.mark.parametrize("tamper", ("producer", "header_hash", "manifest_hash", "schema"))
def test_current_projection_tamper_fails_load_and_recovery(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, tamper: str):
    _repo, runtime_root, kernel, _operations, run_id = _through_fact_provenance(tmp_path, monkeypatch)
    storage = RunStorage(runtime_root, run_id)
    manifest = storage._manifest()
    entry = manifest["current_artifacts"]["report_projection"]
    reference = entry["artifact_ref"]
    if tamper == "manifest_hash":
        entry["content_hash"] = "sha256:" + "0" * 64
        storage._path("runtime/current-manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    else:
        artifact_path = storage._path(f"artifacts/by-ref/{reference}.json")
        projection = json.loads(artifact_path.read_text(encoding="utf-8"))
        if tamper == "producer":
            projection["artifact"]["produced_by"]["attempt"] = "ATT-FORGED-001"
        elif tamper == "header_hash":
            projection["artifact"]["content_hash"] = "sha256:" + "0" * 64
        else:
            projection["verification_status"] = "FORGED"
        artifact_path.write_text(json.dumps(projection), encoding="utf-8")
    for read in (kernel.load_run, kernel.recover_run):
        with pytest.raises(RuntimeContractError):
            read(run_id)


def test_tampered_projection_recovery_does_not_repair_state(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    _repo, runtime_root, kernel, _operations, run_id = _through_fact_provenance(tmp_path, monkeypatch)
    storage = RunStorage(runtime_root, run_id)
    reference = storage._manifest()["current_artifacts"]["report_projection"]["artifact_ref"]
    artifact_path = storage._path(f"artifacts/by-ref/{reference}.json")
    projection = json.loads(artifact_path.read_text(encoding="utf-8"))
    projection["artifact"]["content_hash"] = "sha256:" + "0" * 64
    artifact_path.write_text(json.dumps(projection), encoding="utf-8")
    state_path = storage._path("runtime/state.json")
    state_path.write_text('{"cached":"stale"}', encoding="utf-8")
    with pytest.raises(RuntimeContractError):
        kernel.recover_run(run_id)
    assert state_path.read_text(encoding="utf-8") == '{"cached":"stale"}'


def test_projection_input_version_must_be_its_commit_version(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    _repo, runtime_root, kernel, _operations, run_id = _through_fact_provenance(tmp_path, monkeypatch)
    storage = RunStorage(runtime_root, run_id)
    kernel.schedule_persisted(run_id, requested_nodes=(NodeAddress(("competitor",), "chart_rendering"),))
    manifest = storage._manifest()
    entry = manifest["current_artifacts"]["report_projection"]
    path = storage._path(f"artifacts/by-ref/{entry['artifact_ref']}.json")
    projection = json.loads(path.read_text(encoding="utf-8"))
    projection["input_state_version"] = manifest["state_version"]
    projection["artifact"]["content_hash"] = kernel._artifact_content_hash(projection)
    entry["content_hash"] = projection["artifact"]["content_hash"]
    path.write_text(json.dumps(projection), encoding="utf-8")
    storage._path("runtime/current-manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(RuntimeContractError) as stale:
        kernel.load_run(run_id)
    assert stale.value.rule == "report_projection_integrity"


def test_existing_v030_run_recovers_without_staged_projection(tmp_path: Path):
    kernel, _operations = services(tmp_path)
    created = kernel.create_persisted_run(CreateRunCommand("A compatible product idea", "developer_tool"))
    assert created.contract_version == "0.3.0"
    resumed, _operations = services(tmp_path)
    assert resumed.load_run(created.run_id).state_version == created.state_version
    assert resumed.recover_run(created.run_id).uncommitted_event_offsets == ()


def test_chart_nested_header_is_runtime_owned(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    _repo, runtime_root, kernel, operations, run_id = _through_fact_provenance(tmp_path, monkeypatch)
    storage = RunStorage(runtime_root, run_id)
    projection = storage.read_artifact(storage._manifest()["current_artifacts"]["report_projection"]["artifact_ref"])
    fact = projection["fact_groups"][0]["facts"][0]
    plan = kernel.schedule_persisted(run_id, requested_nodes=(NodeAddress(("competitor",), "chart_rendering"),))
    attempt_id = plan.attempts_to_start[0].attempt_id
    snapshot = kernel.load_run(run_id)
    proposal = ChartRenderingCore(NativeChartRenderer.from_bundle_root(kernel.repository_root / "contracts" / "0.3.2")).build_collection(
        report_projection=projection,
        collection_artifact=_header(kernel, snapshot, attempt_id, "ART-CHART-COLLECTION-FORGED", "chart_bundle_collection", "competitor-chart-rendering"),
        charts=[_chart_request(kernel, snapshot, attempt_id, "feature_matrix", 1, fact)],
    )
    forged = proposal.to_wire_document()
    forged["bundles"][0]["artifact"]["produced_by"] = {"skill": "competitor-chart-rendering", "attempt": "ATT-FORGED-001"}
    forged["bundles"][0]["artifact"]["created_at"] = "2020-01-01T00:00:00Z"
    forged_proposal = ChartRenderingProposal(forged, dict(proposal.assets), proposal.input_artifact_refs)
    result = operations.commit_p0_04_chart_rendering(run_id, attempt_id, forged_proposal, idempotency_key="chart-forged-header")
    stored = storage.read_artifact(result["artifact_ref"])
    assert stored["artifact"]["id"] != "ART-CHART-COLLECTION-FORGED"
    assert stored["bundles"][0]["artifact"]["produced_by"] == {"skill": "competitor-chart-rendering", "attempt": attempt_id}
    assert stored["bundles"][0]["artifact"]["created_at"] == plan.attempts_to_start[0].started_at
    assert kernel.recover_run(run_id).uncommitted_event_offsets == ()


def test_persisted_chart_nested_producer_tamper_fails_recovery(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    _repo, runtime_root, kernel, _operations, run_id, *_rest = _through_report(tmp_path, monkeypatch)
    storage = RunStorage(runtime_root, run_id)
    manifest = storage._manifest()
    entry = manifest["current_artifacts"]["chart_bundle_collection"]
    path = storage._path(f"artifacts/by-ref/{entry['artifact_ref']}.json")
    collection = json.loads(path.read_text(encoding="utf-8"))
    collection["bundles"][0]["artifact"]["produced_by"]["attempt"] = "ATT-FORGED-001"
    collection["bundles"][0]["artifact"]["content_hash"] = kernel._artifact_content_hash(collection["bundles"][0])
    collection["artifact"]["content_hash"] = kernel._artifact_content_hash(collection)
    entry["content_hash"] = collection["artifact"]["content_hash"]
    path.write_text(json.dumps(collection), encoding="utf-8")
    storage._path("runtime/current-manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    for read in (kernel.load_run, kernel.recover_run):
        with pytest.raises(RuntimeContractError) as tampered:
            read(run_id)
        assert tampered.value.rule == "chart_runtime_producer"


def test_report_requires_explicit_citation_metadata_without_manifest_change(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    _repo, runtime_root, kernel, operations, run_id = _through_fact_provenance(tmp_path, monkeypatch)
    storage = RunStorage(runtime_root, run_id)
    projection = storage.read_artifact(storage._manifest()["current_artifacts"]["report_projection"]["artifact_ref"])
    fact = projection["fact_groups"][0]["facts"][0]
    chart_plan = kernel.schedule_persisted(run_id, requested_nodes=(NodeAddress(("competitor",), "chart_rendering"),))
    attempt_id = chart_plan.attempts_to_start[0].attempt_id
    snapshot = kernel.load_run(run_id)
    proposal = ChartRenderingCore(NativeChartRenderer.from_bundle_root(kernel.repository_root / "contracts" / "0.3.2")).build_collection(
        report_projection=projection,
        collection_artifact=_header(kernel, snapshot, attempt_id, "ART-CHART-COLLECTION-CITATION", "chart_bundle_collection", "competitor-chart-rendering"),
        charts=[_chart_request(kernel, snapshot, attempt_id, "feature_matrix", 1, fact)],
    )
    operations.commit_p0_04_chart_rendering(run_id, attempt_id, proposal, idempotency_key="chart-citation")
    publication_plan = kernel.schedule_persisted(run_id, requested_nodes=(NodeAddress(("competitor",), "report_publication_projection"),))
    operations.commit_p0_04_publication_projection(run_id, publication_plan.attempts_to_start[0].attempt_id, idempotency_key="publication-citation")
    report_plan = kernel.schedule_persisted(run_id, requested_nodes=(NodeAddress(("competitor",), "report_builder"),))
    before = deepcopy(storage._manifest())
    original = kernel.source_index_for
    def without_metadata(current_run_id):
        sources = deep_thaw(original(current_run_id))
        for source in sources.values():
            source.pop("citation_metadata", None)
        return sources
    monkeypatch.setattr(kernel, "source_index_for", without_metadata)
    with pytest.raises(RuntimeContractError) as missing:
        operations.commit_p0_04_report(run_id, report_plan.attempts_to_start[0].attempt_id, idempotency_key="report-citation", expected_base_report_ref=None)
    assert missing.value.rule == "report_citation"
    assert storage._manifest() == before
