"""Runtime-owned integration for staged Contract 0.3.2 P0-04 outputs.

This module is an embedding-only boundary.  It does not register 0.3.2, add a
CLI operation, or grant providers storage authority.  Immutable objects and a
mutation receipt are written first; Current Manifest remains the sole commit
point for effective state.
"""

from __future__ import annotations

import hashlib
from html.parser import HTMLParser
import json
from pathlib import Path, PurePosixPath
import re
import tempfile
from typing import Any, Mapping, Sequence
from urllib.parse import urlparse

import yaml

from .chart_rendering import ChartRenderingProposal
from .chart_renderer import NativeChartRenderer
from .domain import NodeAddress, NodeStatus, RunSnapshot, deep_thaw
from .errors import RuntimeContractError
from .fact_provenance import canonical_value_hash, json_pointer_value
from .publication_projection import materialize_report_publication_projection
from .report_publisher import (
    ImmutableReportBundlePublisher,
    ReportPublicationRequest,
    _validate_canonical_svg,
    build_competitor_report_document,
)
from .scoring import (
    IndependentScoreVerifier,
    VerifiedJudgment,
    aggregate_transparent_scores,
    load_profile_rubric,
    validate_dimension_judgment,
)
from .storage import RunStorage, _safe_relative


_INTEGRATED_TYPES = {
    "chart_bundle_collection": "schemas/chart.schema.json#/$defs/chart_bundle_collection",
    "report_publication_projection": "schemas/competitor.schema.json#/$defs/report_publication_projection",
    "competitor_report": "schemas/competitor.schema.json#/$defs/competitor_report",
    "transparent_score": "schemas/competitor.schema.json#/$defs/transparent_score",
}
_TYPE_PREFIX = {
    "chart_bundle_collection": "CHART-BUNDLE-COLLECTION",
    "report_publication_projection": "REPORT-PUBLICATION-PROJECTION",
    "competitor_report": "COMPETITOR-REPORT",
    "transparent_score": "TRANSPARENT-SCORE",
}
_SHA256 = re.compile(r"^sha256:[0-9a-f]{64}$")


def _canonical_hash(value: Any) -> str:
    return "sha256:" + hashlib.sha256(
        json.dumps(deep_thaw(value), ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def _key_hash(value: str) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > 256:
        raise RuntimeContractError("idempotency_key must be a non-empty bounded string", rule="idempotency_key")
    return "sha256:" + hashlib.sha256(value.encode("utf-8")).hexdigest()


def _artifact_ref(document: Mapping[str, Any], expected_type: str) -> str:
    header = document.get("artifact") if isinstance(document, Mapping) else None
    if not isinstance(header, Mapping) or header.get("type") != expected_type:
        raise RuntimeContractError("Integrated Artifact type is invalid", code="SCHEMA_INVALID", rule="staged_artifact")
    identifier, version = header.get("id"), header.get("version")
    if not isinstance(identifier, str) or type(version) is not int or version < 1:
        raise RuntimeContractError("Integrated Artifact identity is invalid", code="SCHEMA_INVALID", rule="staged_artifact")
    return f"{identifier}@{version}"


def _with_content_hash(document: Mapping[str, Any]) -> dict[str, Any]:
    value = deep_thaw(document)
    header = value.get("artifact")
    if not isinstance(header, dict):
        raise RuntimeContractError("Integrated Artifact header is missing", code="SCHEMA_INVALID", rule="staged_artifact")
    header.pop("content_hash", None)
    header["content_hash"] = _canonical_hash(value)
    return value


def _current_entry(storage: RunStorage, artifact_type: str) -> Mapping[str, Any] | None:
    manifest = storage._manifest() or {}
    entry = manifest.get("current_artifacts", {}).get(artifact_type)
    return entry if isinstance(entry, Mapping) else None


def _request_hash(operation: str, request: Any) -> str:
    return _canonical_hash({"operation": operation, "request": request})


def _mutation_identity(operation: str, key: str, request_hash: str, artifact_ref: str) -> dict[str, str]:
    return {
        "key_hash": _key_hash(key),
        "request_hash": request_hash,
        "operation": operation,
        "artifact_ref": artifact_ref,
    }


def _replay_committed(
    kernel: Any,
    snapshot: RunSnapshot,
    artifact_type: str,
    *,
    operation: str,
    key_hash: str,
    request_hash: str,
) -> Mapping[str, Any] | None:
    storage = kernel._storage_for(snapshot.run_id)
    manifest = storage._manifest() or {}
    for current_type, raw_entry in manifest.get("current_artifacts", {}).items():
        if isinstance(raw_entry, Mapping) and raw_entry.get("idempotency_key_hash") == key_hash:
            if current_type != artifact_type or raw_entry.get("operation") != operation or raw_entry.get("request_hash") != request_hash:
                raise RuntimeContractError("Mutation key is bound to a different committed result", code="IDEMPOTENCY_CONFLICT", rule="mutation_replay")
            validate_staged_runtime_resume(kernel, snapshot)
            return storage.read_artifact(str(raw_entry["artifact_ref"]))
    return None


def _header(kernel: Any, snapshot: RunSnapshot, attempt_id: str, artifact_type: str) -> dict[str, Any]:
    attempt = next((item for item in snapshot.attempts if item.attempt_id == attempt_id), None)
    if attempt is None:
        raise RuntimeContractError("Integration Attempt does not exist", rule="staged_attempt")
    storage = kernel._storage_for(snapshot.run_id)
    current = _current_entry(storage, artifact_type)
    supersedes = current.get("artifact_ref") if current is not None else None
    if isinstance(supersedes, str) and "@" in supersedes:
        identifier, raw_version = supersedes.rsplit("@", 1)
        version = int(raw_version) + 1
    else:
        seed = f"{snapshot.run_id}|{artifact_type}"
        if artifact_type == "chart_bundle_collection":
            seed += f"|{attempt_id}"
        token = hashlib.sha256(seed.encode()).hexdigest()[:20].upper()
        identifier = f"ART-{_TYPE_PREFIX[artifact_type]}-{token}"
        version = 1
    return {
        "id": identifier,
        "type": artifact_type,
        "schema_version": snapshot.contract_version,
        "version": version,
        "produced_by": {"skill": attempt.skill_ref.rsplit("@", 1)[0], "attempt": attempt_id},
        "created_at": attempt.started_at,
        "supersedes": supersedes,
        "status": "active",
    }


def _runtime_chart_document(kernel: Any, snapshot: RunSnapshot, attempt_id: str, proposal: ChartRenderingProposal) -> dict[str, Any]:
    """Replace proposal identity fields with headers owned by the active Skill Attempt."""

    document = proposal.to_wire_document()
    collection_header = _header(kernel, snapshot, attempt_id, "chart_bundle_collection")
    bundles = document.get("bundles")
    if not isinstance(bundles, list) or not bundles:
        raise RuntimeContractError("Chart proposal has no bundles", code="SCHEMA_INVALID", rule="chart_runtime_header")
    seen_ids: set[str] = set()
    for bundle in bundles:
        chart = bundle.get("chart") if isinstance(bundle, Mapping) else None
        chart_id = chart.get("id") if isinstance(chart, Mapping) else None
        if not isinstance(chart_id, str) or chart_id in seen_ids:
            raise RuntimeContractError("Chart instance identity is invalid", code="SCHEMA_INVALID", rule="chart_runtime_header")
        seen_ids.add(chart_id)
        token = hashlib.sha256(f"{snapshot.run_id}|{attempt_id}|chart_bundle|{chart_id}".encode()).hexdigest()[:20].upper()
        identifier = f"ART-CHART-BUNDLE-{token}"
        bundle["artifact"] = {
            "id": identifier,
            "type": "chart_bundle",
            "schema_version": snapshot.contract_version,
            "version": 1,
            "produced_by": dict(collection_header["produced_by"]),
            "created_at": collection_header["created_at"],
            "supersedes": None,
            "status": "active",
        }
        bundle["artifact"]["content_hash"] = kernel._artifact_content_hash(bundle)
    document["artifact"] = collection_header
    return _with_content_hash(document)


def _chart_request_body(proposal: ChartRenderingProposal) -> dict[str, Any]:
    body = proposal.to_wire_document()
    body.pop("artifact", None)
    bundles = body.get("bundles")
    if not isinstance(bundles, list) or not bundles or any(not isinstance(bundle, dict) for bundle in bundles):
        raise RuntimeContractError("Chart proposal has no valid bundles", code="SCHEMA_INVALID", rule="chart_runtime_header")
    for bundle in bundles:
        bundle.pop("artifact", None)
    return body


def _active_current_ref(kernel: Any, snapshot: RunSnapshot, artifact_type: str) -> tuple[str, Mapping[str, Any]]:
    entry = _current_entry(kernel._storage_for(snapshot.run_id), artifact_type)
    if entry is None or not isinstance(entry.get("artifact_ref"), str):
        raise RuntimeContractError("Required current Artifact is unavailable", code="DEPENDENCY_NOT_READY", rule="staged_dependency", details={"artifact_type": artifact_type})
    reference = entry["artifact_ref"]
    return reference, kernel._storage_for(snapshot.run_id).read_artifact(reference)


def _referenced_chart_assets(collection: Mapping[str, Any]) -> set[str]:
    result: set[str] = set()
    bundles = collection.get("bundles")
    if not isinstance(bundles, list) or not bundles:
        raise RuntimeContractError("Chart collection has no bundles", code="SCHEMA_INVALID", rule="chart_assets")
    for bundle in bundles:
        if not isinstance(bundle, Mapping):
            raise RuntimeContractError("Chart collection entry is malformed", code="SCHEMA_INVALID", rule="chart_assets")
        for field in ("data_ref", "chart_spec_ref", "svg_ref", "insight_ref"):
            if not isinstance(bundle.get(field), str):
                raise RuntimeContractError("Chart asset reference is missing", code="SCHEMA_INVALID", rule="chart_assets")
            result.add(_safe_relative(bundle[field]).as_posix())
        if "png_ref" in bundle:
            result.add(_safe_relative(bundle["png_ref"]).as_posix())
    return result


def _validate_chart_assets(kernel: Any, snapshot: RunSnapshot, collection: Mapping[str, Any], assets: Mapping[str, bytes]) -> None:
    if set(assets) != _referenced_chart_assets(collection):
        raise RuntimeContractError("Chart assets do not exactly match collection references", code="SCHEMA_INVALID", rule="chart_assets")
    renderer = NativeChartRenderer.from_bundle_root(kernel.compiled_bundle_for(snapshot).context.bundle.root)
    for bundle in collection["bundles"]:
        try:
            spec = json.loads(assets[bundle["chart_spec_ref"]].decode("utf-8"))
            data = json.loads(assets[bundle["data_ref"]].decode("utf-8"))
            svg = assets[bundle["svg_ref"]].decode("utf-8")
            insight = assets[bundle["insight_ref"]].decode("utf-8")
        except (KeyError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise RuntimeContractError("Chart asset payload is unreadable", code="SCHEMA_INVALID", rule="chart_assets") from exc
        if renderer.render_svg(spec, data) != svg:
            raise RuntimeContractError("Canonical SVG does not match its Spec/Data", code="SCHEMA_INVALID", rule="chart_svg_identity")
        _validate_canonical_svg(svg)
        if not insight.strip() or len(insight.encode("utf-8")) > 1024 * 1024:
            raise RuntimeContractError("Chart insight asset is malformed", code="SCHEMA_INVALID", rule="chart_assets")
        png_ref = bundle.get("png_ref")
        if png_ref is not None and not assets[png_ref].startswith(b"\x89PNG\r\n\x1a\n"):
            raise RuntimeContractError("Chart PNG compatibility asset is invalid", code="SCHEMA_INVALID", rule="chart_png")


def _validate_chart_headers(kernel: Any, snapshot: RunSnapshot, collection: Mapping[str, Any]) -> None:
    header = collection.get("artifact")
    producer = header.get("produced_by") if isinstance(header, Mapping) else None
    attempt_id = producer.get("attempt") if isinstance(producer, Mapping) else None
    attempt = next((item for item in snapshot.attempts if item.attempt_id == attempt_id), None)
    token = hashlib.sha256(f"{snapshot.run_id}|chart_bundle_collection|{attempt_id}".encode()).hexdigest()[:20].upper() if isinstance(attempt_id, str) else None
    version = header.get("version") if isinstance(header, Mapping) else None
    supersedes = header.get("supersedes") if isinstance(header, Mapping) else None
    if (
        attempt is None
        or attempt.address != NodeAddress(("competitor",), "chart_rendering")
        or not attempt.verified
        or producer != {"skill": attempt.skill_ref.rsplit("@", 1)[0], "attempt": attempt_id}
        or header.get("created_at") != attempt.started_at
        or header.get("schema_version") != snapshot.contract_version
        or header.get("status") != "active"
        or type(version) is not int
        or version < 1
        or (version == 1 and (supersedes is not None or header.get("id") != f"ART-CHART-BUNDLE-COLLECTION-{token}"))
        or (version > 1 and supersedes != f"{header.get('id')}@{version - 1}")
    ):
        raise RuntimeContractError("Current Chart producer is invalid", code="SECURITY_POLICY_VIOLATION", rule="chart_runtime_producer")
    seen_ids: set[str] = set()
    for bundle in collection.get("bundles", ()):
        chart = bundle.get("chart") if isinstance(bundle, Mapping) else None
        chart_id = chart.get("id") if isinstance(chart, Mapping) else None
        nested = bundle.get("artifact") if isinstance(bundle, Mapping) else None
        if not isinstance(chart_id, str) or not isinstance(nested, Mapping):
            raise RuntimeContractError("Current Chart bundle is malformed", code="SCHEMA_INVALID", rule="chart_runtime_producer")
        token = hashlib.sha256(f"{snapshot.run_id}|{attempt_id}|chart_bundle|{chart_id}".encode()).hexdigest()[:20].upper()
        if (
            chart_id in seen_ids
            or nested.get("id") != f"ART-CHART-BUNDLE-{token}"
            or nested.get("type") != "chart_bundle"
            or nested.get("schema_version") != snapshot.contract_version
            or nested.get("version") != 1
            or nested.get("produced_by") != producer
            or nested.get("created_at") != attempt.started_at
            or nested.get("supersedes") is not None
            or nested.get("status") != "active"
            or nested.get("content_hash") != kernel._artifact_content_hash(bundle)
        ):
            raise RuntimeContractError("Current Chart bundle producer or hash is invalid", code="SECURITY_POLICY_VIOLATION", rule="chart_runtime_producer")
        seen_ids.add(chart_id)


def _profile(kernel: Any, snapshot: RunSnapshot) -> Mapping[str, Any]:
    path = kernel.compiled_bundle_for(snapshot).context.profile_dir / f"{snapshot.profile_ref.split('@', 1)[0].replace('_', '-')}.yaml"
    try:
        value = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        raise RuntimeContractError("Product Profile is unreadable", code="SCHEMA_INVALID", rule="runtime_profile") from exc
    if not isinstance(value, Mapping) or value.get("profile", {}).get("id") != snapshot.profile_ref.split("@", 1)[0]:
        raise RuntimeContractError("Product Profile identity is invalid", code="SCHEMA_INVALID", rule="runtime_profile")
    return value


def _fact_values(storage: RunStorage, projection: Mapping[str, Any]) -> dict[str, Any]:
    values: dict[str, Any] = {}
    for group in projection.get("fact_groups", ()):
        for fact in group.get("facts", ()) if isinstance(group, Mapping) else ():
            fact_id, origin, pointer = fact.get("fact_id"), fact.get("origin_artifact_ref"), fact.get("origin_field_pointer")
            if not all(isinstance(item, str) for item in (fact_id, origin, pointer)):
                raise RuntimeContractError("Publication Fact Binding is malformed", code="SCHEMA_INVALID", rule="report_fact_value")
            if fact.get("fact_class") == "chart":
                continue
            value = json_pointer_value(storage.read_artifact(origin), pointer, rule="report_fact_value")
            if canonical_value_hash(value) != fact.get("content_hash"):
                raise RuntimeContractError("Publication Fact value hash is stale", code="SCHEMA_INVALID", rule="report_fact_value")
            values[fact_id] = value
    return values


class _OfflineReportParser(HTMLParser):
    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        lowered = tag.lower()
        if lowered in {"script", "iframe", "object", "embed", "link", "base"}:
            raise RuntimeContractError("Runtime Report contains an active element", code="SECURITY_POLICY_VIOLATION", rule="runtime_report_html")
        for name, value in attrs:
            key = name.lower()
            raw = value or ""
            if key.startswith("on") or key in {"srcdoc", "integrity", "crossorigin"}:
                raise RuntimeContractError("Runtime Report contains an active attribute", code="SECURITY_POLICY_VIOLATION", rule="runtime_report_html")
            if key == "style" and ("url(" in raw.lower() or "expression(" in raw.lower()):
                raise RuntimeContractError("Runtime Report contains an active style reference", code="SECURITY_POLICY_VIOLATION", rule="runtime_report_html")
            if key == "src" and ("://" in raw or raw.startswith(("//", "data:", "javascript:"))):
                raise RuntimeContractError("Runtime Report contains a remote or executable asset", code="SECURITY_POLICY_VIOLATION", rule="runtime_report_html")
            if key == "href" and raw.strip().lower().startswith(("//", "data:", "javascript:", "file:")):
                raise RuntimeContractError("Runtime Report contains an unsafe hyperlink", code="SECURITY_POLICY_VIOLATION", rule="runtime_report_html")
            if key == "href" and "://" in raw:
                parsed = urlparse(raw)
                if lowered != "a" or parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username or parsed.password:
                    raise RuntimeContractError("Runtime Report contains an unsafe hyperlink", code="SECURITY_POLICY_VIOLATION", rule="runtime_report_html")


def _validate_runtime_report_assets(document: Mapping[str, Any], assets: Mapping[str, bytes]) -> None:
    root_ref, inventory_ref = document.get("report_root_ref"), document.get("inventory_ref")
    if not isinstance(root_ref, str) or not isinstance(inventory_ref, str) or root_ref not in assets or inventory_ref not in assets:
        raise RuntimeContractError("Runtime Report root or inventory is missing", code="ARTIFACT_MISSING", rule="runtime_report_bundle")
    try:
        html = assets[root_ref].decode("utf-8")
        inventory = json.loads(assets[inventory_ref].decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise RuntimeContractError("Runtime Report bundle is unreadable", code="SCHEMA_INVALID", rule="runtime_report_bundle") from exc
    parser = _OfflineReportParser()
    parser.feed(html)
    parser.close()
    if not html.lower().startswith("<!doctype html>") or "<script" in html.lower():
        raise RuntimeContractError("Runtime Report root is not offline-safe HTML", code="SECURITY_POLICY_VIOLATION", rule="runtime_report_html")
    bundle_root = PurePosixPath(root_ref).parent
    records = inventory.get("files") if isinstance(inventory, Mapping) else None
    if not isinstance(records, list) or not records:
        raise RuntimeContractError("Runtime Report inventory is malformed", code="SCHEMA_INVALID", rule="runtime_report_inventory")
    expected = {path for path in assets if PurePosixPath(path).parent == bundle_root or bundle_root in PurePosixPath(path).parents}
    expected.discard(inventory_ref)
    observed: set[str] = set()
    for item in records:
        if not isinstance(item, Mapping) or not isinstance(item.get("path"), str) or _SHA256.fullmatch(str(item.get("sha256"))) is None:
            raise RuntimeContractError("Runtime Report inventory entry is malformed", code="SCHEMA_INVALID", rule="runtime_report_inventory")
        relative = _safe_relative(item["path"]).as_posix()
        logical = (bundle_root / relative).as_posix()
        if logical in observed or logical not in assets:
            raise RuntimeContractError("Runtime Report inventory path is invalid", code="SCHEMA_INVALID", rule="runtime_report_inventory")
        if "sha256:" + hashlib.sha256(assets[logical]).hexdigest() != item["sha256"]:
            raise RuntimeContractError("Runtime Report inventory hash is invalid", code="SCHEMA_INVALID", rule="runtime_report_inventory")
        observed.add(logical)
    if observed != expected:
        raise RuntimeContractError("Runtime Report inventory does not exactly cover bundle files", code="SCHEMA_INVALID", rule="runtime_report_inventory")
    for path, payload in assets.items():
        if path.endswith("/chart.svg"):
            try:
                _validate_canonical_svg(payload.decode("utf-8"))
            except UnicodeDecodeError as exc:
                raise RuntimeContractError("Runtime Report SVG is not UTF-8", code="SCHEMA_INVALID", rule="runtime_report_svg") from exc


def _verified_score_inputs(
    kernel: Any,
    snapshot: RunSnapshot,
    projection: Mapping[str, Any],
    ranking_ref: str,
    judgment_verification_refs: Sequence[tuple[str, str]],
) -> tuple[Any, tuple[str, ...], tuple[VerifiedJudgment, ...], tuple[tuple[str, str, str, str], ...]]:
    storage = kernel._storage_for(snapshot.run_id)
    ranking = storage.read_artifact(ranking_ref)
    candidate_ids = tuple(str(item.get("competitor_id")) for item in ranking.get("ranking", ()) if isinstance(item, Mapping))
    _evidence, claims, _bindings = storage.read_research_provenance(snapshot.state_version)
    category_index = {
        str(item["id"]): str(item["category"])
        for item in claims
        if isinstance(item.get("id"), str) and isinstance(item.get("category"), str)
    }
    rubric = load_profile_rubric(kernel.compiled_bundle_for(snapshot).context.bundle.root, snapshot.profile_ref)
    scoring_state = snapshot.node_states.get(NodeAddress(("competitor",), "scoring"))
    verifier_state = snapshot.node_states.get(NodeAddress(("competitor",), "score_verifier"))
    if scoring_state is None or scoring_state.status is not NodeStatus.VERIFIED or verifier_state is None or verifier_state.status is not NodeStatus.VERIFIED:
        raise RuntimeContractError("Transparent Score inputs are not verified", code="DEPENDENCY_NOT_READY", rule="score_aggregation_state")
    scoring_attempts = {
        item.attempt_id for item in snapshot.attempts if item.address == NodeAddress(("competitor",), "scoring") and item.verified
    }
    verifier_attempts = {
        item.attempt_id for item in snapshot.attempts if item.address == NodeAddress(("competitor",), "score_verifier") and item.verified
    }
    verified: list[VerifiedJudgment] = []
    input_hashes: list[tuple[str, str, str, str]] = []
    verifier = IndependentScoreVerifier()
    for judgment_ref, verification_ref in judgment_verification_refs:
        if judgment_ref not in scoring_state.artifact_refs or verification_ref not in verifier_state.artifact_refs:
            raise RuntimeContractError("Score input Artifact is not current for its verified node", code="STATE_VERSION_CONFLICT", rule="score_artifact_current")
        judgment_document = storage.read_artifact(judgment_ref)
        verification_document = storage.read_artifact(verification_ref)
        judgment_header = judgment_document.get("artifact", {})
        verification_header = verification_document.get("artifact", {})
        if judgment_header.get("type") != "dimension_judgment" or verification_header.get("type") != "score_verification":
            raise RuntimeContractError("Score input Artifact type is invalid", code="SCHEMA_INVALID", rule="score_artifact_type")
        if (
            judgment_header.get("produced_by", {}).get("skill") != "competitor-scoring"
            or judgment_header.get("produced_by", {}).get("attempt") not in scoring_attempts
            or verification_header.get("produced_by", {}).get("skill") != "competitor-score-verifier"
            or verification_header.get("produced_by", {}).get("attempt") not in verifier_attempts
        ):
            raise RuntimeContractError("Score input producer is not the verified Runtime owner", code="SECURITY_POLICY_VIOLATION", rule="score_artifact_producer")
        if judgment_header.get("content_hash") != kernel._artifact_content_hash(judgment_document) or verification_header.get("content_hash") != kernel._artifact_content_hash(verification_document):
            raise RuntimeContractError("Score input Artifact hash is invalid", code="SCHEMA_INVALID", rule="score_artifact_hash")
        bundle = kernel.compiled_bundle_for(snapshot)
        kernel._validate_schema_ref(judgment_document, "schemas/competitor.schema.json#/$defs/dimension_judgment", bundle, rule="score_artifact_schema")
        kernel._validate_schema_ref(verification_document, "schemas/competitor.schema.json#/$defs/score_verification", bundle, rule="score_artifact_schema")
        proposal = {key: value for key, value in judgment_document.items() if key != "artifact"}
        judgment = validate_dimension_judgment(proposal, projection, rubric, category_index)
        checked = verifier.verify(judgment_ref, proposal, projection, rubric, claim_category_index=category_index)
        declared = {key: value for key, value in verification_document.items() if key != "artifact"}
        if checked.to_document_fields() != declared or checked.result != "ACCEPT":
            raise RuntimeContractError("Persisted Score Verification does not accept the Judgment", code="SECURITY_POLICY_VIOLATION", rule="score_verification_binding")
        verified.append(VerifiedJudgment(judgment_ref, verification_ref, judgment, checked))
        input_hashes.append((judgment_ref, _canonical_hash(judgment_document), verification_ref, _canonical_hash(verification_document)))
    return rubric, candidate_ids, tuple(verified), tuple(input_hashes)


class StagedP004RuntimeIntegration:
    """Embedding-only P0-04 integration owned by the Runtime writer."""

    def __init__(self, kernel: Any) -> None:
        if kernel.storage_root is None:
            raise RuntimeContractError("Runtime integration requires storage", rule="storage_root_required")
        self.kernel = kernel

    def commit_chart_rendering(
        self,
        run_id: str,
        attempt_id: str,
        proposal: ChartRenderingProposal,
        *,
        idempotency_key: str,
    ) -> Mapping[str, Any]:
        snapshot = self.kernel.load_run(run_id)
        if snapshot.contract_version != "0.3.2" or not isinstance(proposal, ChartRenderingProposal):
            raise RuntimeContractError("Chart Runtime integration requires a staged 0.3.2 proposal", code="SCHEMA_VERSION_UNSUPPORTED", rule="staged_runtime")
        projection_ref, projection = _active_current_ref(self.kernel, snapshot, "report_projection")
        expected_inputs = tuple(dict.fromkeys((projection_ref, *tuple(projection.get("input_artifact_refs", ())))))
        if proposal.input_artifact_refs != expected_inputs:
            raise RuntimeContractError("Chart proposal inputs are stale", code="STATE_VERSION_CONFLICT", rule="chart_runtime_inputs")
        assets = dict(proposal.assets)
        operation = "commit_chart_rendering"
        request_hash = _request_hash(
            operation,
            {"attempt_id": attempt_id, "body": _chart_request_body(proposal), "assets": {key: "sha256:" + hashlib.sha256(value).hexdigest() for key, value in sorted(assets.items())}, "inputs": expected_inputs},
        )
        replay = _replay_committed(
            self.kernel,
            snapshot,
            "chart_bundle_collection",
            operation=operation,
            key_hash=_key_hash(idempotency_key),
            request_hash=request_hash,
        )
        if replay is not None:
            return {"state": snapshot.to_wire_state(), "artifact_ref": _artifact_ref(replay, "chart_bundle_collection"), "replayed": True}
        document = _runtime_chart_document(self.kernel, snapshot, attempt_id, proposal)
        _validate_chart_assets(self.kernel, snapshot, document, assets)
        artifact_ref = _artifact_ref(document, "chart_bundle_collection")
        identity = _mutation_identity(
            operation,
            idempotency_key,
            request_hash,
            artifact_ref,
        )
        completed = self.kernel.complete_persisted_business_attempt(
            run_id,
            attempt_id,
            (("artifacts/02-research/competitors/visualizations/chart-bundle-collection.json", document),),
            events=("CHART_COLLECTION_COMMITTED",),
            asset_payloads=assets,
            mutation_identity=identity,
        )
        return {"state": completed.to_wire_state(), "artifact_ref": artifact_ref, "replayed": False}

    def materialize_publication_projection(self, run_id: str, attempt_id: str, *, idempotency_key: str) -> Mapping[str, Any]:
        snapshot = self.kernel.load_run(run_id)
        projection_ref, projection = _active_current_ref(self.kernel, snapshot, "report_projection")
        collection_ref, collection = _active_current_ref(self.kernel, snapshot, "chart_bundle_collection")
        storage = self.kernel._storage_for(run_id)
        evidence, claims, _bindings = storage.read_research_provenance(snapshot.state_version)
        sources = self.kernel.source_index_for(run_id)
        operation = "materialize_publication_projection"
        request_hash = _request_hash(
            operation,
            {
                "attempt_id": attempt_id,
                "projection_ref": projection_ref,
                "projection_hash": _canonical_hash(projection),
                "collection_ref": collection_ref,
                "collection_hash": _canonical_hash(collection),
                "provenance_hash": _canonical_hash({"evidence": evidence, "claims": claims}),
                "sources_hash": _canonical_hash(sources),
            },
        )
        replay = _replay_committed(
            self.kernel,
            snapshot,
            "report_publication_projection",
            operation=operation,
            key_hash=_key_hash(idempotency_key),
            request_hash=request_hash,
        )
        if replay is not None:
            return {"state": snapshot.to_wire_state(), "artifact_ref": _artifact_ref(replay, "report_publication_projection"), "replayed": True}
        header = _header(self.kernel, snapshot, attempt_id, "report_publication_projection")
        document = materialize_report_publication_projection(
            artifact=header,
            base_projection=projection,
            chart_bundle_collection=collection,
            claims=claims,
            evidence=evidence,
            sources=sources,
        )
        document = _with_content_hash(document)
        artifact_ref = _artifact_ref(document, "report_publication_projection")
        identity = _mutation_identity(
            operation,
            idempotency_key,
            request_hash,
            artifact_ref,
        )
        completed = self.kernel.complete_persisted_business_attempt(
            run_id,
            attempt_id,
            (("artifacts/02-research/competitors/report-publication-projection.json", document),),
            events=("REPORT_PUBLICATION_PROJECTION_COMMITTED",),
            mutation_identity=identity,
        )
        return {"state": completed.to_wire_state(), "artifact_ref": artifact_ref, "replayed": False}

    def publish_report(
        self,
        run_id: str,
        attempt_id: str,
        *,
        idempotency_key: str,
        expected_base_report_ref: str | None,
    ) -> Mapping[str, Any]:
        snapshot = self.kernel.load_run(run_id)
        projection_ref, projection = _active_current_ref(self.kernel, snapshot, "report_publication_projection")
        collection_ref, collection = _active_current_ref(self.kernel, snapshot, "chart_bundle_collection")
        storage = self.kernel._storage_for(run_id)
        collection_entry = _current_entry(storage, "chart_bundle_collection") or {}
        chart_assets = storage.read_asset_inventory(
            artifact_ref=collection_ref,
            inventory_ref=str(collection_entry.get("asset_inventory_ref", "")),
            inventory_hash=str(collection_entry.get("asset_inventory_hash", "")),
        )
        evidence, claims, bindings = storage.read_research_provenance(snapshot.state_version)
        del evidence, claims
        all_sources = self.kernel.source_index_for(run_id)
        closure_sources = set(projection.get("citation_closure", {}).get("source_ids", ()))
        source_records: dict[str, Mapping[str, Any]] = {}
        for source_id in sorted(closure_sources):
            source = all_sources.get(source_id)
            if not isinstance(source, Mapping):
                raise RuntimeContractError("Publication Source is not current", code="ARTIFACT_MISSING", rule="report_citation")
            metadata = source.get("citation_metadata")
            if (
                not isinstance(metadata, Mapping)
                or not isinstance(metadata.get("publisher_short_name"), str)
                or not metadata["publisher_short_name"].strip()
                or not isinstance(metadata.get("excerpt"), str)
                or not metadata["excerpt"].strip()
                or "local_favicon_ref" not in metadata
            ):
                raise RuntimeContractError("Publication Source lacks verified citation metadata", code="SCHEMA_INVALID", rule="report_citation")
            source_records[source_id] = deep_thaw(source)
        fact_values = _fact_values(storage, projection)
        # Chart observation bindings live in Publication Projection rather than
        # the research-provenance sidecar.
        chart_documents = {
            _artifact_ref(bundle, "chart_bundle"): bundle
            for bundle in collection.get("bundles", ())
            if isinstance(bundle, Mapping)
        }
        for group in projection.get("fact_groups", ()):
            for fact in group.get("facts", ()) if isinstance(group, Mapping) else ():
                if fact.get("fact_class") == "chart":
                    origin_ref = str(fact["origin_artifact_ref"])
                    origin = chart_documents.get(origin_ref)
                    if origin is None:
                        raise RuntimeContractError("Chart Fact origin is not current", code="SCHEMA_INVALID", rule="report_fact_value")
                    fact_values[str(fact["fact_id"])] = json_pointer_value(origin, str(fact["origin_field_pointer"]), rule="report_fact_value")
        del bindings
        bundle_root = self.kernel.compiled_bundle_for(snapshot).context.bundle.root
        profile = _profile(self.kernel, snapshot)
        template_path = bundle_root / "templates" / "competitor-report.html"
        try:
            template_hash = "sha256:" + hashlib.sha256(template_path.read_bytes()).hexdigest()
        except OSError as exc:
            raise RuntimeContractError("Report template is unavailable", code="SOURCE_UNAVAILABLE", rule="report_template") from exc
        operation = "publish_competitor_report"
        request_hash = _request_hash(
            operation,
            {
                "attempt_id": attempt_id,
                "projection_ref": projection_ref,
                "projection_hash": _canonical_hash(projection),
                "collection_ref": collection_ref,
                "collection_hash": _canonical_hash(collection),
                "chart_asset_hashes": {key: "sha256:" + hashlib.sha256(value).hexdigest() for key, value in sorted(chart_assets.items())},
                "profile_hash": _canonical_hash(profile),
                "source_hash": _canonical_hash(source_records),
                "fact_hash": _canonical_hash(fact_values),
                "template_hash": template_hash,
                "expected_base_report_ref": expected_base_report_ref,
            },
        )
        replay = _replay_committed(
            self.kernel,
            snapshot,
            "competitor_report",
            operation=operation,
            key_hash=_key_hash(idempotency_key),
            request_hash=request_hash,
        )
        if replay is not None:
            return {"state": snapshot.to_wire_state(), "artifact_ref": _artifact_ref(replay, "competitor_report"), "replayed": True}
        header = _header(self.kernel, snapshot, attempt_id, "competitor_report")
        report_ref = f"{header['id']}@{header['version']}"
        request = ReportPublicationRequest(
            run_id=run_id,
            attempt_id=attempt_id,
            report_ref=report_ref,
            expected_base_report_ref=expected_base_report_ref,
            idempotency_key=idempotency_key,
            publication_projection=projection,
            chart_bundle_collection=collection,
            profile=profile,
            source_records=source_records,
            fact_values=fact_values,
            template_path=template_path,
            fixture_svg_assets=None,
        )
        run_root = storage.run_root.resolve()
        with tempfile.TemporaryDirectory(prefix="ideatoproduct-report-stage-") as temporary:
            staging_root = Path(temporary).resolve()
            try:
                staging_root.relative_to(run_root)
            except ValueError:
                pass
            else:  # pragma: no cover - defensive platform guard.
                raise RuntimeContractError("Report staging root overlaps the Run root", code="SECURITY_POLICY_VIOLATION", rule="report_staging")
            pointer = ImmutableReportBundlePublisher(staging_root)._publish_from_inventory(request, storage, collection_entry)
            staged_run = RunStorage(staging_root, run_id)
            root_ref, inventory_ref = pointer.get("root_ref"), pointer.get("inventory_ref")
            if not isinstance(root_ref, str) or not isinstance(inventory_ref, str):
                raise RuntimeContractError("Staged Report pointer is malformed", code="SCHEMA_INVALID", rule="report_staging")
            expected_root = f"artifacts/02-research/competitors/report-bundles/{report_ref}/competitor-report.html"
            expected_inventory = f"artifacts/02-research/competitors/report-bundles/{report_ref}/inventory.json"
            expected_pointer = {
                "report_ref": report_ref,
                "base_report_ref": expected_base_report_ref,
                "attempt_id": attempt_id,
                "report_publication_projection_ref": projection_ref,
                "chart_bundle_collection_ref": collection_ref,
                "root_ref": expected_root,
                "inventory_ref": expected_inventory,
            }
            if any(pointer.get(key) != value for key, value in expected_pointer.items()):
                raise RuntimeContractError("Staged Report pointer does not bind the Runtime request", code="SCHEMA_INVALID", rule="report_staging")
            isolated_inventory = staged_run._read_json(inventory_ref)
            files = isolated_inventory.get("files") if isinstance(isolated_inventory, Mapping) else None
            publication_identity = isolated_inventory.get("publication_identity") if isinstance(isolated_inventory, Mapping) else None
            if (
                not isinstance(files, list)
                or isolated_inventory.get("report_ref") != report_ref
                or not isinstance(publication_identity, Mapping)
                or publication_identity.get("result_identity") != pointer.get("result_identity")
            ):
                raise RuntimeContractError("Staged Report inventory is malformed", code="SCHEMA_INVALID", rule="report_staging")
            version_root = PurePosixPath(root_ref).parent
            assets: dict[str, bytes] = {inventory_ref: staged_run._path(inventory_ref).read_bytes()}
            for item in files:
                if not isinstance(item, Mapping) or not isinstance(item.get("path"), str):
                    raise RuntimeContractError("Staged Report inventory entry is malformed", code="SCHEMA_INVALID", rule="report_staging")
                relative = _safe_relative(item["path"])
                logical = (version_root / relative).as_posix()
                payload = staged_run._path(logical).read_bytes()
                if "sha256:" + hashlib.sha256(payload).hexdigest() != item.get("sha256"):
                    raise RuntimeContractError("Staged Report file hash is invalid", code="SCHEMA_INVALID", rule="report_staging")
                assets[logical] = payload
            document = _with_content_hash(build_competitor_report_document(artifact=header, publication_pointer=pointer))
            _validate_runtime_report_assets(document, assets)
        identity = _mutation_identity(
            operation,
            idempotency_key,
            request_hash,
            report_ref,
        )
        current_report = _current_entry(storage, "competitor_report")
        current_ref = current_report.get("artifact_ref") if current_report is not None else None
        if current_ref != expected_base_report_ref:
            raise RuntimeContractError("Report base version is stale", code="STATE_VERSION_CONFLICT", rule="report_cas")
        completed = self.kernel.complete_persisted_business_attempt(
            run_id,
            attempt_id,
            (("artifacts/02-research/competitors/report-publication.json", document),),
            events=("COMPETITOR_REPORT_COMMITTED",),
            asset_payloads=assets,
            mutation_identity=identity,
        )
        return {"state": completed.to_wire_state(), "artifact_ref": report_ref, "replayed": False}

    def commit_transparent_score(
        self,
        run_id: str,
        scoring_attempt_id: str,
        *,
        idempotency_key: str,
        competitor_id: str,
        judgment_verification_refs: Sequence[tuple[str, str]],
    ) -> Mapping[str, Any]:
        snapshot = self.kernel.load_run(run_id)
        projection_ref, projection = _active_current_ref(self.kernel, snapshot, "report_projection")
        ranking_ref, ranking = _active_current_ref(self.kernel, snapshot, "competitor_ranking")
        rubric, candidate_ids, verified, input_hashes = _verified_score_inputs(
            self.kernel,
            snapshot,
            projection,
            ranking_ref,
            judgment_verification_refs,
        )
        if competitor_id not in candidate_ids:
            raise RuntimeContractError("Transparent Score competitor is outside current ranking", code="SECURITY_POLICY_VIOLATION", rule="score_candidate")
        operation = "commit_transparent_score"
        request_hash = _request_hash(
            operation,
            {
                "scoring_attempt_id": scoring_attempt_id,
                "projection_ref": projection_ref,
                "projection_hash": _canonical_hash(projection),
                "ranking_ref": ranking_ref,
                "ranking_hash": _canonical_hash(ranking),
                "rubric_hash": rubric.content_hash,
                "competitor_id": competitor_id,
                "inputs": input_hashes,
            },
        )
        replay = _replay_committed(
            self.kernel,
            snapshot,
            "transparent_score",
            operation=operation,
            key_hash=_key_hash(idempotency_key),
            request_hash=request_hash,
        )
        if replay is not None:
            return {"state": snapshot.to_wire_state(), "artifact_ref": _artifact_ref(replay, "transparent_score"), "replayed": True}
        outcomes = aggregate_transparent_scores(rubric, candidate_ids, ranking_ref, verified)
        outcome = next(item for item in outcomes if item.competitor_id == competitor_id)
        fields = outcome.to_document_fields()
        header = _header(self.kernel, snapshot, scoring_attempt_id, "transparent_score")
        document = _with_content_hash({"artifact": header, **fields})
        artifact_ref = _artifact_ref(document, "transparent_score")
        identity = _mutation_identity(
            operation,
            idempotency_key,
            request_hash,
            artifact_ref,
        )
        updated = self.kernel.commit_runtime_owned_aggregation(
            run_id,
            scoring_attempt_id,
            f"artifacts/02-research/competitors/scoring/scores/{competitor_id}.json",
            document,
            mutation_identity=identity,
        )
        return {"state": updated.to_wire_state(), "artifact_ref": artifact_ref, "replayed": False}


def validate_staged_runtime_resume(kernel: Any, snapshot: RunSnapshot) -> None:
    """Fail closed when any effective staged integration object was tampered."""

    if snapshot.contract_version != "0.3.2":
        return
    storage = kernel._storage_for(snapshot.run_id)
    manifest = storage._manifest() or {}
    current = manifest.get("current_artifacts", {})
    effective_refs = {
        reference
        for address, state in snapshot.node_states.items()
        if state.status is NodeStatus.VERIFIED
        for reference in state.artifact_refs
    }
    documents: dict[str, Mapping[str, Any]] = {}
    assets_by_type: dict[str, Mapping[str, bytes]] = {}
    for artifact_type, schema_ref in _INTEGRATED_TYPES.items():
        entry = current.get(artifact_type)
        if entry is None:
            continue
        if not isinstance(entry, Mapping) or not isinstance(entry.get("artifact_ref"), str):
            raise RuntimeContractError("Current staged Artifact entry is malformed", code="SCHEMA_INVALID", rule="staged_resume")
        reference = entry["artifact_ref"]
        document = storage.read_artifact(reference)
        header = document.get("artifact") if isinstance(document, Mapping) else None
        if (
            _artifact_ref(document, artifact_type) != reference
            or not isinstance(header, Mapping)
            or kernel._artifact_content_hash(document) != entry.get("content_hash")
            or header.get("content_hash") != entry.get("content_hash")
        ):
            raise RuntimeContractError("Current staged Artifact identity or hash is invalid", code="SCHEMA_INVALID", rule="staged_resume")
        if reference not in effective_refs:
            raise RuntimeContractError("Current staged Artifact is not owned by a verified node", code="SCHEMA_INVALID", rule="staged_resume")
        kernel._validate_schema_ref(document, schema_ref, kernel.compiled_bundle_for(snapshot), rule="staged_resume_schema")
        identity = {
            "key_hash": str(entry.get("idempotency_key_hash", "")),
            "request_hash": str(entry.get("request_hash", "")),
            "operation": str(entry.get("operation", "")),
            "artifact_ref": reference,
        }
        storage.validate_mutation_receipt(
            receipt_ref=str(entry.get("mutation_receipt_ref", "")),
            receipt_hash=str(entry.get("mutation_receipt_hash", "")),
            expected=identity,
        )
        has_inventory = "asset_inventory_ref" in entry or "asset_inventory_hash" in entry
        if has_inventory:
            assets_by_type[artifact_type] = storage.read_asset_inventory(
                artifact_ref=reference,
                inventory_ref=str(entry.get("asset_inventory_ref", "")),
                inventory_hash=str(entry.get("asset_inventory_hash", "")),
            )
        documents[artifact_type] = document
    chart = documents.get("chart_bundle_collection")
    if chart is not None:
        _validate_chart_headers(kernel, snapshot, chart)
        _validate_chart_assets(kernel, snapshot, chart, assets_by_type.get("chart_bundle_collection", {}))
        projection_entry = current.get("report_projection", {})
        if not isinstance(projection_entry, Mapping) or chart.get("bundles") is None:
            raise RuntimeContractError("Current Chart dependencies are missing", code="SCHEMA_INVALID", rule="staged_resume")
    publication = documents.get("report_publication_projection")
    if publication is not None:
        if publication.get("report_projection_ref") != current.get("report_projection", {}).get("artifact_ref") or publication.get("chart_bundle_collection_ref") != current.get("chart_bundle_collection", {}).get("artifact_ref"):
            raise RuntimeContractError("Current Publication Projection dependencies are stale", code="SCHEMA_INVALID", rule="staged_resume")
        evidence, claims, _bindings = storage.read_research_provenance(snapshot.state_version)
        expected = materialize_report_publication_projection(
            artifact=publication["artifact"],
            base_projection=storage.read_artifact(publication["report_projection_ref"]),
            chart_bundle_collection=storage.read_artifact(publication["chart_bundle_collection_ref"]),
            claims=claims,
            evidence=evidence,
            sources={
                str(item["id"]): item
                for item in storage.read_source_index(snapshot.state_version)
                if isinstance(item, Mapping) and isinstance(item.get("id"), str)
            },
        )
        expected = _with_content_hash(expected)
        if expected != deep_thaw(publication):
            raise RuntimeContractError("Current Publication Projection closure is invalid", code="SCHEMA_INVALID", rule="staged_resume")
    report = documents.get("competitor_report")
    if report is not None:
        if report.get("report_publication_projection_ref") != current.get("report_publication_projection", {}).get("artifact_ref") or report.get("chart_bundle_collection_ref") != current.get("chart_bundle_collection", {}).get("artifact_ref"):
            raise RuntimeContractError("Current Report dependencies are stale", code="SCHEMA_INVALID", rule="staged_resume")
        _validate_runtime_report_assets(report, assets_by_type.get("competitor_report", {}))
    score = documents.get("transparent_score")
    if score is not None:
        ranking_ref = current.get("competitor_ranking", {}).get("artifact_ref")
        projection_ref = current.get("report_projection", {}).get("artifact_ref")
        if score.get("candidate_ranking_ref") != ranking_ref or not isinstance(projection_ref, str):
            raise RuntimeContractError("Current Transparent Score ranking is stale", code="SCHEMA_INVALID", rule="staged_resume")
        judgment_refs = tuple(score.get("dimension_judgment_refs", ()))
        verification_refs = tuple(score.get("score_verification_refs", ()))
        if len(judgment_refs) != len(verification_refs) or any(reference not in effective_refs for reference in (*judgment_refs, *verification_refs)):
            raise RuntimeContractError("Current Transparent Score inputs are stale", code="SCHEMA_INVALID", rule="staged_resume")
        projection = storage.read_artifact(projection_ref)
        rubric, candidates, verified, _input_hashes = _verified_score_inputs(
            kernel,
            snapshot,
            projection,
            str(ranking_ref),
            tuple(zip(judgment_refs, verification_refs)),
        )
        outcomes = aggregate_transparent_scores(rubric, candidates, str(ranking_ref), verified)
        expected = next((item for item in outcomes if item.competitor_id == score.get("competitor_id")), None)
        if expected is None or expected.to_document_fields() != {key: value for key, value in score.items() if key != "artifact"}:
            raise RuntimeContractError("Current Transparent Score is not the deterministic aggregate", code="SCHEMA_INVALID", rule="staged_resume")
