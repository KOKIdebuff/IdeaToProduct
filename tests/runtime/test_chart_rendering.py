from __future__ import annotations

from copy import deepcopy
from pathlib import Path
import struct
import zlib

import pytest

from scripts.contract_bundles import ContractBundle, load_bundle_context
from scripts.validate_contracts import load_document, load_schemas, validate_instance
from skillgraph_runtime.chart_renderer import NativeChartRenderer
from skillgraph_runtime.chart_rendering import ChartRenderingCore
from skillgraph_runtime.errors import RuntimeContractError


ROOT = Path(__file__).resolve().parents[2]
BUNDLE_ROOT = ROOT / "contracts" / "0.3.2"


def _artifact(artifact_id: str, artifact_type: str) -> dict:
    return {
        "id": artifact_id,
        "type": artifact_type,
        "schema_version": "0.3.2",
        "version": 1,
        "produced_by": {"skill": "competitor-chart-rendering", "attempt": "ATT-CHART-001"},
        "created_at": "2026-09-12T00:00:00Z",
        "supersedes": None,
        "status": "active",
    }


def _projection() -> dict:
    return load_document(BUNDLE_ROOT / "fixtures" / "valid" / "report-projection.yaml")


def _request(*, png_requested: bool = False) -> dict:
    request = {
        "artifact": _artifact("ART-CHART-001", "chart_bundle"),
        "chart_instance_id": "chart_feature_001",
        "chart_spec": load_document(BUNDLE_ROOT / "fixtures" / "valid" / "chart-spec.yaml"),
        "chart_data": load_document(BUNDLE_ROOT / "fixtures" / "valid" / "chart-data.yaml"),
        "data_ref": "artifacts/02-research/competitors/visualizations/feature-matrix/data.json",
        "chart_spec_ref": "artifacts/02-research/competitors/visualizations/feature-matrix/chart-spec.json",
        "svg_ref": "artifacts/02-research/competitors/visualizations/feature-matrix/chart.svg",
        "insight_ref": "artifacts/02-research/competitors/visualizations/feature-matrix/insight.md",
        "png_requested": png_requested,
        "observation": "Product A has stronger verified feature coverage.",
        "interpretation": "The matrix remains limited to cited observed fields.",
        "product_implication": "Differentiate through workflow depth.",
        "confidence": "MEDIUM",
        "claim_refs": ["CL-001"],
        "evidence_ids": ["EV-001"],
        "limitations": ["Missing data remains explicit."],
    }
    if png_requested:
        request["png_ref"] = "artifacts/02-research/competitors/visualizations/feature-matrix/chart.png"
    return request


def _png_payload() -> bytes:
    def chunk(name: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + name + data + struct.pack(">I", zlib.crc32(name + data) & 0xFFFFFFFF)

    header = struct.pack(">IIBBBBB", 1, 1, 8, 6, 0, 0, 0)
    pixels = zlib.compress(b"\x00\x00\x00\x00\x00")
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", header) + chunk(b"IDAT", pixels) + chunk(b"IEND", b"")


@pytest.fixture(scope="module")
def core() -> ChartRenderingCore:
    return ChartRenderingCore(NativeChartRenderer.from_bundle_root(BUNDLE_ROOT))


def test_builds_schema_valid_deterministic_collection_and_contained_assets(core: ChartRenderingCore):
    projection = _projection()
    request = _request()
    first = core.build_collection(
        report_projection=projection,
        collection_artifact=_artifact("ART-CHART-COLLECTION-001", "chart_bundle_collection"),
        charts=[request],
    )
    second = core.build_collection(
        report_projection=deepcopy(projection),
        collection_artifact=_artifact("ART-CHART-COLLECTION-001", "chart_bundle_collection"),
        charts=[deepcopy(request)],
    )
    assert first.to_wire_document() == second.to_wire_document()
    assert dict(first.assets) == dict(second.assets)
    assert first.input_artifact_refs == ("ART-REPORT-PROJECTION-001@1", "ART-COMPETITOR-001@1")
    assert set(first.assets) == {
        request["data_ref"],
        request["chart_spec_ref"],
        request["svg_ref"],
        request["insight_ref"],
    }
    assert first.assets[request["svg_ref"]].startswith(b'<svg xmlns="http://www.w3.org/2000/svg"')
    assert first.to_wire_document()["bundles"][0]["compatibility_export"] == {
        "requested": False,
        "status": "NOT_REQUESTED",
        "error": None,
    }

    context = load_bundle_context(ContractBundle("0.3.2", BUNDLE_ROOT, "staged", "audit"))
    schemas, registry = load_schemas(context.schema_dir)
    assert validate_instance(
        first.to_wire_document(),
        "chart.schema.json#/$defs/chart_bundle_collection",
        "generated-chart-collection.json",
        schemas,
        registry,
    ) == []


def test_png_request_degrades_to_disclosed_partial_without_exporter(core: ChartRenderingCore):
    proposal = core.build_collection(
        report_projection=_projection(),
        collection_artifact=_artifact("ART-CHART-COLLECTION-001", "chart_bundle_collection"),
        charts=[_request(png_requested=True)],
    )
    bundle = proposal.to_wire_document()["bundles"][0]
    assert bundle["compatibility_export"] == {
        "requested": True,
        "status": "PARTIAL",
        "error": "PNG exporter unavailable.",
    }
    assert "png_ref" not in bundle
    assert all(not path.endswith(".png") for path in proposal.assets)


def test_png_request_records_complete_only_for_valid_png_payload(core: ChartRenderingCore):
    payload = _png_payload()
    proposal = core.build_collection(
        report_projection=_projection(),
        collection_artifact=_artifact("ART-CHART-COLLECTION-001", "chart_bundle_collection"),
        charts=[_request(png_requested=True)],
        png_exporter=lambda _svg: payload,
    )
    bundle = proposal.to_wire_document()["bundles"][0]
    assert bundle["compatibility_export"] == {"requested": True, "status": "COMPLETE", "error": None}
    assert proposal.assets[bundle["png_ref"]] == payload


@pytest.mark.parametrize(
    "exporter",
    [lambda _svg: b"not-png", lambda _svg: (_ for _ in ()).throw(OSError("private detail"))],
)
def test_invalid_or_failed_png_export_is_partial_without_leaking_exception(core: ChartRenderingCore, exporter):
    proposal = core.build_collection(
        report_projection=_projection(),
        collection_artifact=_artifact("ART-CHART-COLLECTION-001", "chart_bundle_collection"),
        charts=[_request(png_requested=True)],
        png_exporter=exporter,
    )
    bundle = proposal.to_wire_document()["bundles"][0]
    assert bundle["compatibility_export"]["status"] == "PARTIAL"
    assert "private detail" not in bundle["compatibility_export"]["error"]
    assert "png_ref" not in bundle


@pytest.mark.parametrize(
    "unsafe_path",
    [
        "../chart.svg",
        "/artifacts/02-research/competitors/visualizations/feature-matrix/chart.svg",
        "C:/chart.svg",
        "https://example.test/chart.svg",
        "artifacts\\02-research\\competitors\\visualizations\\feature-matrix\\chart.svg",
        "artifacts/02-research/competitors/visualizations/feature-matrix/../chart.svg",
    ],
)
def test_rejects_remote_absolute_or_traversing_asset_paths(core: ChartRenderingCore, unsafe_path: str):
    request = _request()
    request["svg_ref"] = unsafe_path
    with pytest.raises(RuntimeContractError) as captured:
        core.build_collection(
            report_projection=_projection(),
            collection_artifact=_artifact("ART-CHART-COLLECTION-001", "chart_bundle_collection"),
            charts=[request],
        )
    assert captured.value.code == "SECURITY_POLICY_VIOLATION"
    assert captured.value.rule in {"chart_asset_path", "chart_asset_scope"}


def test_rejects_dangling_or_non_minimal_chart_provenance(core: ChartRenderingCore):
    dangling = _request()
    dangling["chart_data"]["rows"][0]["evidence_refs"] = ["EV-MISSING"]
    dangling["evidence_ids"] = ["EV-MISSING"]
    with pytest.raises(RuntimeContractError) as captured:
        core.build_collection(
            report_projection=_projection(),
            collection_artifact=_artifact("ART-CHART-COLLECTION-001", "chart_bundle_collection"),
            charts=[dangling],
        )
    assert captured.value.code == "INSUFFICIENT_EVIDENCE"
    assert captured.value.rule == "chart_provenance_dangling"

    extra = _request()
    extra["evidence_ids"].append("EV-EXTRA")
    with pytest.raises(RuntimeContractError) as captured:
        core.build_collection(
            report_projection=_projection(),
            collection_artifact=_artifact("ART-CHART-COLLECTION-001", "chart_bundle_collection"),
            charts=[extra],
        )
    assert captured.value.rule == "chart_provenance_closure"


def test_rejects_duplicate_chart_type_before_returning_proposal(core: ChartRenderingCore):
    first = _request()
    second = deepcopy(first)
    second["artifact"]["id"] = "ART-CHART-002"
    second["chart_instance_id"] = "chart_feature_002"
    directory = "artifacts/02-research/competitors/visualizations/feature-matrix-two"
    second["data_ref"] = f"{directory}/data.json"
    second["chart_spec_ref"] = f"{directory}/chart-spec.json"
    second["svg_ref"] = f"{directory}/chart.svg"
    second["insight_ref"] = f"{directory}/insight.md"
    with pytest.raises(RuntimeContractError) as captured:
        core.build_collection(
            report_projection=_projection(),
            collection_artifact=_artifact("ART-CHART-COLLECTION-001", "chart_bundle_collection"),
            charts=[first, second],
        )
    assert captured.value.rule == "chart_rendering_duplicate"


def test_rejects_non_exact_projection_citation_closure(core: ChartRenderingCore):
    projection = _projection()
    projection["citation_closure"]["evidence_ids"].append("EV-EXTRA")
    with pytest.raises(RuntimeContractError) as captured:
        core.build_collection(
            report_projection=projection,
            collection_artifact=_artifact("ART-CHART-COLLECTION-001", "chart_bundle_collection"),
            charts=[_request()],
        )
    assert captured.value.rule == "chart_projection_closure"


def test_does_not_mutate_caller_documents(core: ChartRenderingCore):
    projection = _projection()
    request = _request()
    before_projection = deepcopy(projection)
    before_request = deepcopy(request)
    core.build_collection(
        report_projection=projection,
        collection_artifact=_artifact("ART-CHART-COLLECTION-001", "chart_bundle_collection"),
        charts=[request],
    )
    assert projection == before_projection
    assert request == before_request
