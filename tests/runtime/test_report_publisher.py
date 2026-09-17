from __future__ import annotations

import json
import hashlib
from copy import deepcopy
from dataclasses import replace
from pathlib import Path

import pytest

from scripts.contract_bundles import ContractBundle, load_bundle_context
from scripts.validate_contracts import ROOT, load_schemas, validate_instance
from skillgraph_runtime.errors import RuntimeContractError
from skillgraph_runtime.fact_provenance import canonical_value_hash
import skillgraph_runtime.report_publisher as report_publisher_module
from skillgraph_runtime.report_publisher import (
    ImmutableReportBundlePublisher,
    ReportPublicationRequest,
    build_competitor_report_document,
)


CHART_TYPES = ("feature_matrix", "momentum_comparison", "oss_activity", "positioning_map")


def _header(identifier: str, artifact_type: str, *, version: int = 1, supersedes: str | None = None) -> dict:
    return {
        "id": identifier,
        "type": artifact_type,
        "schema_version": "0.3.2",
        "version": version,
        "produced_by": {"skill": "competitor-report-builder", "attempt": "ATT-REPORT-001"},
        "created_at": "2026-09-03T00:00:00Z",
        "supersedes": supersedes,
        "status": "active",
    }


def _canonical_svg(title: str = "Chart") -> str:
    return (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 640 360" role="img">'
        f"<title>{title}</title><desc>Accessible chart description.</desc>"
        '<rect x="10" y="10" width="100" height="40" fill="#3355aa"/></svg>'
    )


def _request(tmp_path: Path) -> ReportPublicationRequest:
    text_value = '<img src="https://attacker.invalid/x" onerror="alert(1)"> is untrusted text.'
    chart_values = {chart_type: f"Verified observation for {chart_type}." for chart_type in CHART_TYPES}
    text_fact = {
        "fact_id": "FACT-TEXT-001",
        "origin_artifact_ref": "ART-DATASET-001@1",
        "origin_field_pointer": "/competitors/0/metrics/pricing/value",
        "content_hash": canonical_value_hash(text_value),
        "fact_class": "dataset",
        "claim_refs": ["CL-TEXT-001"],
        "evidence_refs": ["EV-TEXT-001"],
        "source_refs": ["SRC-001"],
    }
    groups = [
        {
            "id": "FG-PRICING-001",
            "section_id": "pricing",
            "dom_scope_id": "pricing-product-a",
            "facts": [text_fact],
            "citation_source_ids": ["SRC-001"],
        }
    ]
    bundles = []
    assets = {}
    fact_values = {"FACT-TEXT-001": text_value}
    for index, chart_type in enumerate(CHART_TYPES, start=1):
        chart_ref = f"ART-CHART-{index:03d}@1"
        observation = chart_values[chart_type]
        fact_id = f"FACT-CHART-{index:03d}"
        svg_ref = f"artifacts/02-research/competitors/visualizations/{chart_type}/chart.svg"
        groups.append(
            {
                "id": f"FG-CHART-{index:03d}",
                "section_id": "svg-visualizations",
                "dom_scope_id": f"chart-{chart_type.replace('_', '-')}",
                "facts": [
                    {
                        "fact_id": fact_id,
                        "origin_artifact_ref": chart_ref,
                        "origin_field_pointer": "/observation",
                        "content_hash": canonical_value_hash(observation),
                        "fact_class": "chart",
                        "claim_refs": ["CL-CHART-001"],
                        "evidence_refs": ["EV-CHART-001"],
                        "source_refs": ["SRC-001"],
                    }
                ],
                "citation_source_ids": ["SRC-001"],
            }
        )
        fact_values[fact_id] = observation
        bundles.append(
            {
                "artifact": _header(f"ART-CHART-{index:03d}", "chart_bundle"),
                "chart": {"id": f"chart-{index:03d}", "type": chart_type, "renderer_kind": "matrix"},
                "data_ref": f"artifacts/02-research/competitors/visualizations/{chart_type}/data.json",
                "chart_spec_ref": f"artifacts/02-research/competitors/visualizations/{chart_type}/chart-spec.json",
                "svg_ref": svg_ref,
                "insight_ref": f"artifacts/02-research/competitors/visualizations/{chart_type}/insight.md",
                "compatibility_export": {"requested": False, "status": "NOT_REQUESTED", "error": None},
                "observation": observation,
                "interpretation": "Limited to cited fields.",
                "product_implication": "Inform product differentiation.",
                "confidence": "MEDIUM",
                "claim_refs": ["CL-CHART-001"],
                "evidence_ids": ["EV-CHART-001"],
                "limitations": ["Missing data stays explicit."],
            }
        )
        assets[svg_ref] = _canonical_svg(chart_type)

    collection = {
        "artifact": _header("ART-CHART-COLLECTION-001", "chart_bundle_collection"),
        "bundles": bundles,
    }
    projection = {
        "artifact": _header("ART-PUBLICATION-PROJECTION-001", "report_publication_projection"),
        "report_projection_ref": "ART-REPORT-PROJECTION-001@1",
        "chart_bundle_collection_ref": "ART-CHART-COLLECTION-001@1",
        "fact_groups": groups,
        "citation_closure": {
            "claim_ids": ["CL-CHART-001", "CL-TEXT-001"],
            "evidence_ids": ["EV-CHART-001", "EV-TEXT-001"],
            "source_ids": ["SRC-001"],
        },
        "verification_status": "PENDING",
        "scoring_status": "NOT_PERFORMED",
    }
    source = {
        "id": "SRC-001",
        "canonical_url": "https://example.com/docs?a=1&b=2",
        "title": "Example <Documentation>",
        "citation_metadata": {
            "publisher_short_name": "Example & Co",
            "excerpt": "Verified <excerpt> & local metadata.",
            "local_favicon_ref": None,
        },
    }
    return ReportPublicationRequest(
        run_id="run_report_001",
        attempt_id="ATT-REPORT-001",
        report_ref="ART-COMPETITOR-REPORT-001@1",
        expected_base_report_ref=None,
        idempotency_key="publish-report-001",
        publication_projection=projection,
        chart_bundle_collection=collection,
        profile={"competitor_visualizations": {"required": list(CHART_TYPES)}},
        source_records={"SRC-001": source},
        fact_values=fact_values,
        template_path=ROOT / "contracts" / "0.3.2" / "templates" / "competitor-report.html",
        fixture_svg_assets=assets,
    )


def _publisher(tmp_path: Path) -> ImmutableReportBundlePublisher:
    return ImmutableReportBundlePublisher(tmp_path, fixture_assets_allowed=True)


def test_publishes_offline_contained_report_and_typed_artifact_proposal(tmp_path: Path):
    request = _request(tmp_path)
    pointer = _publisher(tmp_path).publish(request)
    assert pointer["report_ref"] == request.report_ref
    assert pointer["base_report_ref"] is None
    run_root = tmp_path / "runs" / request.run_id
    report_path = run_root / Path(*pointer["root_ref"].split("/"))
    inventory_path = run_root / Path(*pointer["inventory_ref"].split("/"))
    assert report_path.is_file() and inventory_path.is_file()
    html_text = report_path.read_text(encoding="utf-8")
    assert "<script" not in html_text.lower()
    assert 'src="http' not in html_text.lower()
    assert "cdn" not in html_text.lower()
    assert '&lt;img src=&quot;https://attacker.invalid/x&quot; onerror=&quot;alert(1)&quot;&gt;' in html_text
    assert 'href="https://example.com/docs?a=1&amp;b=2"' in html_text
    assert 'data-verification-status="PENDING"' in html_text
    assert 'data-scoring-status="NOT_PERFORMED"' in html_text
    assert html_text.count('<section id="svg-visualizations"') == 1
    assert all(f'src="visualizations/{chart_type}/chart.svg"' in html_text for chart_type in CHART_TYPES)

    inventory = json.loads(inventory_path.read_text(encoding="utf-8"))
    assert [item["path"] for item in inventory["files"]] == [
        "competitor-report.html",
        *[f"visualizations/{chart_type}/chart.svg" for chart_type in sorted(CHART_TYPES)],
    ]
    artifact = build_competitor_report_document(
        artifact=_header("ART-COMPETITOR-REPORT-001", "competitor_report"),
        publication_pointer=pointer,
    )
    assert artifact["publication_kind"] == "INITIAL"
    assert artifact["base_report_ref"] is None
    assert artifact["verification"] == {"status": "PENDING", "verification_ref": None}
    assert artifact["scoring"] == {"status": "NOT_PERFORMED", "score_collection_ref": None}
    context = load_bundle_context(ContractBundle("0.3.2", ROOT / "contracts" / "0.3.2", "staged", "audit"))
    schemas, registry = load_schemas(context.schema_dir)
    assert validate_instance(
        artifact,
        "competitor.schema.json#/$defs/competitor_report",
        "generated-competitor-report.json",
        schemas,
        registry,
    ) == []


def test_same_idempotency_key_and_request_replays_without_duplicate_output(tmp_path: Path):
    request = _request(tmp_path)
    publisher = _publisher(tmp_path)
    first = publisher.publish(request)
    second = publisher.publish(request)
    assert second == first == publisher.replay(request)
    bundle_root = tmp_path / "runs" / request.run_id / "artifacts" / "02-research" / "competitors" / "report-bundles"
    assert sorted(path.name for path in bundle_root.iterdir() if path.name != ".staging") == [request.report_ref]


def test_transient_directory_commit_lock_is_retried_without_weakening_append_only(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    request = _request(tmp_path)
    original_replace = report_publisher_module.os.replace
    attempts = 0

    def transient_replace(source, destination):
        nonlocal attempts
        if ".staging" in Path(source).parts and attempts < 2:
            attempts += 1
            raise PermissionError(13, "injected transient directory lock", str(source))
        attempts += 1
        return original_replace(source, destination)

    monkeypatch.setattr(report_publisher_module.os, "replace", transient_replace)
    monkeypatch.setattr(report_publisher_module.time, "sleep", lambda _seconds: None)

    pointer = _publisher(tmp_path).publish(request)

    assert attempts >= 3
    assert pointer["report_ref"] == request.report_ref
    assert _publisher(tmp_path).publish(request) == pointer


def test_replay_recovers_missing_index_after_current_pointer_commit(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    request = _request(tmp_path)
    publisher = _publisher(tmp_path)
    original_write = report_publisher_module._IsolatedReportStore._write_immutable_json

    def crash_before_index(self, relative: str, value):
        if relative.startswith("runtime/report-publications/"):
            raise RuntimeError("injected crash after current pointer commit")
        return original_write(self, relative, value)

    with monkeypatch.context() as scoped:
        scoped.setattr(
            report_publisher_module._IsolatedReportStore,
            "_write_immutable_json",
            crash_before_index,
        )
        with pytest.raises(RuntimeError, match="after current pointer commit"):
            publisher.publish(request)

    run_root = tmp_path / "runs" / request.run_id
    pointer_path = run_root / "runtime" / "current-report.json"
    records_root = run_root / "runtime" / "report-publications"
    pointer = json.loads(pointer_path.read_text(encoding="utf-8"))
    assert pointer["idempotency_key_hash"].startswith("sha256:")
    assert pointer["request_hash"].startswith("sha256:")
    assert pointer["result_identity"].startswith("sha256:")
    assert not records_root.exists() or list(records_root.iterdir()) == []
    inventory_path = run_root / Path(*pointer["inventory_ref"].split("/"))
    inventory = json.loads(inventory_path.read_text(encoding="utf-8"))
    assert inventory["publication_identity"]["idempotency_key_hash"] == pointer["idempotency_key_hash"]
    assert inventory["publication_identity"]["request_hash"] == pointer["request_hash"]
    assert inventory["publication_identity"]["result_identity"] == pointer["result_identity"]

    recovered = publisher.replay(request)
    assert recovered == pointer
    records = list(records_root.glob("*.json"))
    assert len(records) == 1
    record = json.loads(records[0].read_text(encoding="utf-8"))
    assert record["pointer"] == pointer
    assert record["result_identity"] == pointer["result_identity"]
    assert publisher.publish(request) == pointer


def test_crash_window_rejects_changed_input_or_key_before_recovery(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    request = _request(tmp_path)
    publisher = _publisher(tmp_path)
    original_write = report_publisher_module._IsolatedReportStore._write_immutable_json

    def crash_before_index(self, relative: str, value):
        if relative.startswith("runtime/report-publications/"):
            raise RuntimeError("injected crash")
        return original_write(self, relative, value)

    with monkeypatch.context() as scoped:
        scoped.setattr(
            report_publisher_module._IsolatedReportStore,
            "_write_immutable_json",
            crash_before_index,
        )
        with pytest.raises(RuntimeError, match="injected crash"):
            publisher.publish(request)

    changed_sources = deepcopy(request.source_records)
    changed_sources["SRC-001"]["title"] = "Changed after crash"
    with pytest.raises(RuntimeContractError, match="different request") as same_key:
        publisher.publish(replace(request, source_records=changed_sources))
    assert same_key.value.code == "IDEMPOTENCY_CONFLICT"

    with pytest.raises(RuntimeContractError, match="base version is stale") as other_key:
        publisher.publish(replace(request, idempotency_key="another-key"))
    assert other_key.value.code == "STATE_VERSION_CONFLICT"
    records_root = tmp_path / "runs" / request.run_id / "runtime" / "report-publications"
    assert not records_root.exists() or list(records_root.iterdir()) == []


def test_uncommitted_prewrite_record_is_never_treated_as_success(tmp_path: Path):
    request = _request(tmp_path)
    publisher = _publisher(tmp_path)
    template = publisher._template(request.template_path)
    key_hash, request_hash = publisher._request_hash(request, template)
    record_path = (
        tmp_path
        / "runs"
        / request.run_id
        / "runtime"
        / "report-publications"
        / f"{key_hash.removeprefix('sha256:')}.json"
    )
    record_path.parent.mkdir(parents=True)
    record_path.write_text(
        json.dumps(
            {
                "idempotency_key_hash": key_hash,
                "request_hash": request_hash,
                "result_identity": "sha256:" + "0" * 64,
                "pointer": {"report_ref": request.report_ref},
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(RuntimeContractError, match="does not identify the committed current result") as captured:
        publisher.replay(request)
    assert captured.value.code == "STATE_VERSION_CONFLICT"
    assert not (
        tmp_path / "runs" / request.run_id / "artifacts" / "02-research" / "competitors" / "report-bundles"
    ).exists()


def test_idempotency_key_reuse_with_changed_source_or_template_fails_closed(tmp_path: Path):
    request = _request(tmp_path)
    publisher = _publisher(tmp_path)
    first = publisher.publish(request)
    changed_sources = {key: dict(value) for key, value in request.source_records.items()}
    changed_sources["SRC-001"] = {**changed_sources["SRC-001"], "title": "Changed"}
    changed = replace(request, source_records=changed_sources)
    with pytest.raises(RuntimeContractError, match="different request") as captured:
        publisher.publish(changed)
    assert captured.value.code == "IDEMPOTENCY_CONFLICT"
    current = json.loads((tmp_path / "runs" / request.run_id / "runtime" / "current-report.json").read_text())
    assert current == first


def test_successor_uses_cas_and_preserves_prior_version(tmp_path: Path):
    request = _request(tmp_path)
    publisher = _publisher(tmp_path)
    first = publisher.publish(request)
    successor = replace(
        request,
        report_ref="ART-COMPETITOR-REPORT-001@2",
        expected_base_report_ref=request.report_ref,
        idempotency_key="publish-report-002",
    )
    second = publisher.publish(successor)
    assert second["base_report_ref"] == first["report_ref"]
    assert second["report_ref"] == successor.report_ref
    bundle_root = tmp_path / "runs" / request.run_id / "artifacts" / "02-research" / "competitors" / "report-bundles"
    assert (bundle_root / request.report_ref / "competitor-report.html").is_file()
    assert (bundle_root / successor.report_ref / "competitor-report.html").is_file()


def test_stale_base_and_non_incrementing_successor_fail_before_publication(tmp_path: Path):
    request = _request(tmp_path)
    publisher = _publisher(tmp_path)
    first = publisher.publish(request)
    stale = replace(
        request,
        report_ref="ART-COMPETITOR-REPORT-001@10",
        expected_base_report_ref="ART-COMPETITOR-REPORT-001@9",
        idempotency_key="publish-stale",
    )
    with pytest.raises(RuntimeContractError, match="base version is stale") as captured:
        publisher.publish(stale)
    assert captured.value.code == "STATE_VERSION_CONFLICT"
    wrong_identity = replace(
        request,
        report_ref="ART-OTHER-REPORT@2",
        expected_base_report_ref=request.report_ref,
        idempotency_key="publish-wrong-identity",
    )
    with pytest.raises(RuntimeContractError, match="same Artifact identity"):
        publisher.publish(wrong_identity)
    current = json.loads((tmp_path / "runs" / request.run_id / "runtime" / "current-report.json").read_text())
    assert current == first


@pytest.mark.parametrize(
    "svg",
    [
        '<svg viewBox="0 0 10 10" role="img"><title>x</title><desc>x</desc><script>alert(1)</script></svg>',
        '<svg viewBox="0 0 10 10" role="img"><title>x</title><desc>x</desc><foreignObject/></svg>',
        '<svg viewBox="0 0 10 10" role="img" onload="alert(1)"><title>x</title><desc>x</desc></svg>',
        '<svg viewBox="0 0 10 10" role="img"><title>x</title><desc>x</desc><image href="https://evil.invalid/x"/></svg>',
        '<svg viewBox="0 0 10 10" role="img"><title>x</title><desc>x</desc><style>@import url(https://evil.invalid/x)</style></svg>',
    ],
)
def test_unsafe_svg_is_rejected_before_pointer_update(tmp_path: Path, svg: str):
    request = _request(tmp_path)
    assets = dict(request.fixture_svg_assets or {})
    assets[next(iter(assets))] = svg
    with pytest.raises(RuntimeContractError) as captured:
        _publisher(tmp_path).publish(replace(request, fixture_svg_assets=assets))
    assert captured.value.code == "SECURITY_POLICY_VIOLATION"
    assert not (tmp_path / "runs" / request.run_id / "runtime" / "current-report.json").exists()


@pytest.mark.parametrize(
    "template",
    [
        '<!doctype html><html><body><main></main><script>alert(1)</script></body></html>',
        '<!doctype html><html><head><link rel="stylesheet" href="https://evil.invalid/x.css"></head><body><main></main></body></html>',
        '<!doctype html><html><body><main><img src="https://evil.invalid/x"></main></body></html>',
        '<!doctype html><html><body><main onclick="alert(1)"></main></body></html>',
        '<!doctype html><html><style>@import "https://evil.invalid/x.css";</style><body><main></main></body></html>',
    ],
)
def test_unsafe_template_is_rejected_before_pointer_update(tmp_path: Path, template: str):
    request = _request(tmp_path)
    template_path = tmp_path / "unsafe-template.html"
    template_path.write_text(template, encoding="utf-8")
    with pytest.raises(RuntimeContractError):
        _publisher(tmp_path).publish(replace(request, template_path=template_path))
    assert not (tmp_path / "runs" / request.run_id / "runtime" / "current-report.json").exists()


def test_collection_ref_missing_chart_and_runtime_asset_resolution_fail_closed(tmp_path: Path):
    request = _request(tmp_path)
    mismatched_projection = {**request.publication_projection, "chart_bundle_collection_ref": "ART-OTHER@1"}
    with pytest.raises(RuntimeContractError, match="does not reference"):
        _publisher(tmp_path).publish(replace(request, publication_projection=mismatched_projection))

    missing_collection = {
        **request.chart_bundle_collection,
        "bundles": request.chart_bundle_collection["bundles"][:-1],
    }
    with pytest.raises(RuntimeContractError, match="required canonical SVG chart is missing"):
        _publisher(tmp_path).publish(replace(request, chart_bundle_collection=missing_collection))

    with pytest.raises(RuntimeContractError, match="not integrated") as captured:
        _publisher(tmp_path).publish(replace(request, fixture_svg_assets=None))
    assert captured.value.rule == "report_asset_integration"


def test_contract_choose_one_is_resolved_by_exactly_one_realized_chart(tmp_path: Path):
    request = _request(tmp_path)
    collection = deepcopy(request.chart_bundle_collection)
    pricing = deepcopy(collection["bundles"][0])
    pricing["artifact"]["id"] = "ART-CHART-999"
    pricing["chart"] = {"id": "chart-999", "type": "pricing_comparison", "renderer_kind": "bar"}
    pricing["svg_ref"] = "artifacts/02-research/competitors/visualizations/pricing_comparison/chart.svg"
    collection["bundles"].append(pricing)
    assets = dict(request.fixture_svg_assets or {})
    assets[pricing["svg_ref"]] = _canonical_svg("pricing_comparison")
    profile = {
        "competitor_visualizations": {
            "required": ["feature_matrix", "positioning_map"],
            "choose_one": {
                "options": ["pricing_comparison", "sentiment_distribution"],
                "selected_by": "research_contract",
            },
        }
    }
    narrowed_assets = {
        key: value
        for key, value in assets.items()
        if any(chart_type in key for chart_type in ("feature_matrix", "positioning_map", "pricing_comparison"))
    }
    pointer = _publisher(tmp_path).publish(
        replace(
            request,
            chart_bundle_collection=collection,
            profile=profile,
            fixture_svg_assets=narrowed_assets,
        )
    )
    html_text = (
        tmp_path / "runs" / request.run_id / Path(*pointer["root_ref"].split("/"))
    ).read_text(encoding="utf-8")
    assert 'src="visualizations/pricing_comparison/chart.svg"' in html_text
    assert "sentiment_distribution" not in html_text


def test_path_traversal_and_non_http_citation_url_fail_closed(tmp_path: Path):
    request = _request(tmp_path)
    collection = deepcopy(request.chart_bundle_collection)
    collection["bundles"][0]["svg_ref"] = "../escape.svg"
    assets = dict(request.fixture_svg_assets or {})
    assets.pop(next(iter(assets)))
    assets["../escape.svg"] = _canonical_svg("escape")
    with pytest.raises(RuntimeContractError) as captured:
        _publisher(tmp_path).publish(
            replace(request, chart_bundle_collection=collection, fixture_svg_assets=assets)
        )
    assert captured.value.code == "SECURITY_POLICY_VIOLATION"

    source_records = deepcopy(request.source_records)
    source_records["SRC-001"]["canonical_url"] = "file:///etc/passwd"
    with pytest.raises(RuntimeContractError) as captured:
        _publisher(tmp_path).publish(replace(request, source_records=source_records))
    assert captured.value.code == "SECURITY_POLICY_VIOLATION"


def test_rejects_non_minimal_source_or_fact_inputs(tmp_path: Path):
    request = _request(tmp_path)
    extra_sources = {**request.source_records, "SRC-EXTRA": {"id": "SRC-EXTRA"}}
    with pytest.raises(RuntimeContractError, match="outside the minimum Citation Closure"):
        _publisher(tmp_path).publish(replace(request, source_records=extra_sources))
    with pytest.raises(RuntimeContractError, match="outside the Publication Projection"):
        _publisher(tmp_path).publish(replace(request, fact_values={**request.fact_values, "FACT-EXTRA": "x"}))


def test_inventory_tampering_is_detected_on_replay(tmp_path: Path):
    request = _request(tmp_path)
    publisher = _publisher(tmp_path)
    pointer = publisher.publish(request)
    asset = tmp_path / "runs" / request.run_id / Path(*pointer["root_ref"].split("/"))
    svg = asset.parent / "visualizations" / CHART_TYPES[0] / "chart.svg"
    svg.write_text(_canonical_svg("tampered"), encoding="utf-8")
    with pytest.raises(RuntimeContractError, match="hash does not match"):
        publisher.replay(request)
