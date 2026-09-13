"""Pure chart rendering proposal construction for staged Contract 0.3.2.

This module deliberately has no RuntimeKernel or filesystem writer.  It turns
an already materialized report projection plus explicit chart inputs into a
schema-shaped ``chart_bundle_collection`` and contained in-memory assets.  A
Runtime-owned single writer may persist that proposal in a later integration
task.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime
import json
from pathlib import PurePosixPath
import re
import struct
from types import MappingProxyType
from typing import Any
import zlib

from .chart_renderer import NativeChartRenderer
from .errors import RuntimeContractError


_CONTRACT_VERSION = "0.3.2"
_PRODUCER_SKILL = "competitor-chart-rendering"
_ASSET_ROOT = PurePosixPath("artifacts/02-research/competitors/visualizations")
_MACHINE_ID = re.compile(r"^[a-z][a-z0-9]*(?:[_-][a-z0-9]+)*$")
_ARTIFACT_ID = re.compile(r"^ART-[A-Za-z0-9_-]+$")
_ATTEMPT_ID = re.compile(r"^ATT-[A-Za-z0-9_-]+$")
_CLAIM_ID = re.compile(r"^CL-[A-Za-z0-9_-]+$")
_EVIDENCE_ID = re.compile(r"^EV-[A-Za-z0-9_-]+$")
_SOURCE_ID = re.compile(r"^SRC-[A-Za-z0-9_-]+$")
_PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
_CONFIDENCE = frozenset({"HIGH", "MEDIUM", "LOW", "INSUFFICIENT"})
_REQUEST_FIELDS = frozenset(
    {
        "artifact",
        "chart_instance_id",
        "chart_spec",
        "chart_data",
        "data_ref",
        "chart_spec_ref",
        "svg_ref",
        "png_ref",
        "insight_ref",
        "png_requested",
        "observation",
        "interpretation",
        "product_implication",
        "confidence",
        "claim_refs",
        "evidence_ids",
        "limitations",
    }
)
_REQUIRED_REQUEST_FIELDS = _REQUEST_FIELDS - {"png_ref"}


@dataclass(frozen=True)
class ChartRenderingProposal:
    """Immutable, persistence-free result of chart rendering."""

    collection: Mapping[str, Any]
    assets: Mapping[str, bytes]
    input_artifact_refs: tuple[str, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "collection", _freeze(self.collection))
        object.__setattr__(self, "assets", MappingProxyType(dict(self.assets)))
        object.__setattr__(self, "input_artifact_refs", tuple(self.input_artifact_refs))

    def to_wire_document(self) -> dict[str, Any]:
        """Return a detached JSON-compatible collection document."""

        return _thaw(self.collection)


PngExporter = Callable[[str], bytes]


@dataclass(frozen=True)
class ChartRenderingCore:
    """Build deterministic 0.3.2 chart collection proposals in memory."""

    renderer: NativeChartRenderer

    def __post_init__(self) -> None:
        if self.renderer.contract_version != _CONTRACT_VERSION:
            raise RuntimeContractError(
                "Chart Rendering Core requires the staged 0.3.2 Renderer Registry",
                code="SCHEMA_VERSION_UNSUPPORTED",
                rule="chart_rendering_contract_version",
            )

    def build_collection(
        self,
        *,
        report_projection: Mapping[str, Any],
        collection_artifact: Mapping[str, Any],
        charts: Sequence[Mapping[str, Any]],
        png_exporter: PngExporter | None = None,
    ) -> ChartRenderingProposal:
        """Build a collection proposal without writing Runtime or filesystem state.

        Narrative fields and provenance are required caller inputs.  The core
        only validates and carries those values; it never derives facts from
        SVG, labels, URLs, or rendered geometry.
        """

        projection_ref, provenance = _validate_report_projection(report_projection)
        collection_header = _artifact_header(collection_artifact, expected_type="chart_bundle_collection")
        if not isinstance(charts, Sequence) or isinstance(charts, (str, bytes)) or not charts:
            raise RuntimeContractError(
                "Chart Rendering requires at least one chart request",
                code="SCHEMA_INVALID",
                rule="chart_rendering_requests",
            )

        bundles: list[dict[str, Any]] = []
        assets: dict[str, bytes] = {}
        seen_instance_ids: set[str] = set()
        seen_chart_types: set[str] = set()
        for request in charts:
            bundle, payloads = self._build_chart(
                request,
                provenance=provenance,
                expected_attempt=collection_header["produced_by"]["attempt"],
                png_exporter=png_exporter,
            )
            instance_id = bundle["chart"]["id"]
            chart_type = bundle["chart"]["type"]
            if instance_id in seen_instance_ids or chart_type in seen_chart_types:
                raise RuntimeContractError(
                    "Chart Rendering requests must not repeat chart instance IDs or registered chart types",
                    code="SCHEMA_INVALID",
                    rule="chart_rendering_duplicate",
                )
            seen_instance_ids.add(instance_id)
            seen_chart_types.add(chart_type)
            for path, payload in payloads.items():
                if path in assets:
                    raise RuntimeContractError(
                        "Chart Rendering asset paths must be unique",
                        code="SECURITY_POLICY_VIOLATION",
                        rule="chart_asset_collision",
                    )
                assets[path] = payload
            bundles.append(bundle)

        collection = {"artifact": collection_header, "bundles": bundles}
        return ChartRenderingProposal(
            collection=collection,
            assets=assets,
            input_artifact_refs=_stable_unique(
                (projection_ref, *tuple(str(item) for item in report_projection.get("input_artifact_refs", ())))
            ),
        )

    def _build_chart(
        self,
        request: Mapping[str, Any],
        *,
        provenance: "_ProjectionProvenance",
        expected_attempt: str,
        png_exporter: PngExporter | None,
    ) -> tuple[dict[str, Any], dict[str, bytes]]:
        if not isinstance(request, Mapping):
            raise RuntimeContractError("Chart request must be an object", code="SCHEMA_INVALID", rule="chart_rendering_request")
        fields = set(request)
        if not _REQUIRED_REQUEST_FIELDS <= fields or fields - _REQUEST_FIELDS:
            raise RuntimeContractError(
                "Chart request has missing or unsupported fields",
                code="SCHEMA_INVALID",
                rule="chart_rendering_request",
            )
        artifact = _artifact_header(request["artifact"], expected_type="chart_bundle")
        if artifact["produced_by"]["attempt"] != expected_attempt:
            raise RuntimeContractError(
                "Chart Bundle and collection must be produced by the same attempt",
                code="SCHEMA_INVALID",
                rule="chart_rendering_attempt",
            )
        instance_id = _machine_id(request["chart_instance_id"], rule="chart_instance_id")
        spec = _json_object(request["chart_spec"], rule="chart_spec")
        data = _json_object(request["chart_data"], rule="chart_data")
        svg = self.renderer.render_svg(spec, data)

        data_ref = _asset_path(request["data_ref"], filename="data.json")
        spec_ref = _asset_path(request["chart_spec_ref"], filename="chart-spec.json")
        svg_ref = _asset_path(request["svg_ref"], filename="chart.svg")
        insight_ref = _asset_path(request["insight_ref"], filename="insight.md")
        parents = {PurePosixPath(item).parent for item in (data_ref, spec_ref, svg_ref, insight_ref)}
        if len(parents) != 1:
            raise RuntimeContractError(
                "All Chart Bundle assets must share one contained chart directory",
                code="SECURITY_POLICY_VIOLATION",
                rule="chart_asset_scope",
            )

        observation = _text(request["observation"], rule="chart_observation")
        interpretation = _text(request["interpretation"], rule="chart_interpretation")
        implication = _text(request["product_implication"], rule="chart_product_implication")
        confidence = request["confidence"]
        if confidence not in _CONFIDENCE:
            raise RuntimeContractError("Chart confidence is invalid", code="SCHEMA_INVALID", rule="chart_confidence")
        limitations = _text_list(request["limitations"], rule="chart_limitations", allow_empty=True)
        claim_refs = _id_list(request["claim_refs"], _CLAIM_ID, rule="chart_claim_refs", allow_empty=False)
        evidence_ids = _id_list(request["evidence_ids"], _EVIDENCE_ID, rule="chart_evidence_ids", allow_empty=True)
        _validate_chart_provenance(data, claim_refs, evidence_ids, provenance)

        requested = request["png_requested"]
        if not isinstance(requested, bool):
            raise RuntimeContractError("png_requested must be boolean", code="SCHEMA_INVALID", rule="chart_png_request")
        png_input = request.get("png_ref")
        payloads: dict[str, bytes] = {
            data_ref: _canonical_json(data),
            spec_ref: _canonical_json(spec),
            svg_ref: svg.encode("utf-8"),
            insight_ref: _insight_payload(
                observation,
                interpretation,
                implication,
                str(confidence),
                claim_refs,
                evidence_ids,
                limitations,
            ),
        }
        compatibility: dict[str, Any]
        output_png_ref: str | None = None
        if not requested:
            if png_input is not None:
                raise RuntimeContractError(
                    "PNG path is forbidden when compatibility export was not requested",
                    code="SCHEMA_INVALID",
                    rule="chart_png_request",
                )
            compatibility = {"requested": False, "status": "NOT_REQUESTED", "error": None}
        else:
            if png_input is None:
                raise RuntimeContractError(
                    "Explicit PNG export requires a contained target path",
                    code="SCHEMA_INVALID",
                    rule="chart_png_request",
                )
            png_path = _asset_path(png_input, filename="chart.png")
            if PurePosixPath(png_path).parent not in parents:
                raise RuntimeContractError(
                    "PNG target must share the contained chart directory",
                    code="SECURITY_POLICY_VIOLATION",
                    rule="chart_asset_scope",
                )
            png_payload, error = _try_png_export(svg, png_exporter)
            if png_payload is None:
                compatibility = {"requested": True, "status": "PARTIAL", "error": error}
            else:
                output_png_ref = png_path
                payloads[png_path] = png_payload
                compatibility = {"requested": True, "status": "COMPLETE", "error": None}

        bundle: dict[str, Any] = {
            "artifact": artifact,
            "chart": {
                "id": instance_id,
                "type": str(spec["chart_id"]),
                "renderer_kind": str(spec["renderer_kind"]),
            },
            "data_ref": data_ref,
            "chart_spec_ref": spec_ref,
            "svg_ref": svg_ref,
            "insight_ref": insight_ref,
            "compatibility_export": compatibility,
            "observation": observation,
            "interpretation": interpretation,
            "product_implication": implication,
            "confidence": confidence,
            "claim_refs": list(claim_refs),
            "evidence_ids": list(evidence_ids),
            "limitations": list(limitations),
        }
        if output_png_ref is not None:
            bundle["png_ref"] = output_png_ref
        return bundle, payloads


@dataclass(frozen=True)
class _ProjectionProvenance:
    claim_ids: frozenset[str]
    evidence_ids: frozenset[str]
    evidence_to_claims: Mapping[str, frozenset[str]]


def _validate_report_projection(document: Mapping[str, Any]) -> tuple[str, _ProjectionProvenance]:
    if not isinstance(document, Mapping):
        raise RuntimeContractError("Report Projection must be an object", code="SCHEMA_INVALID", rule="chart_report_projection")
    header = _artifact_header(document.get("artifact"), expected_type="report_projection", expected_skill=None)
    if header["status"] != "active":
        raise RuntimeContractError("Report Projection must be active", code="DEPENDENCY_NOT_READY", rule="chart_report_projection")
    if document.get("verification_status") not in {"PENDING", "PASS"}:
        raise RuntimeContractError("Report Projection is not eligible for chart rendering", code="DEPENDENCY_NOT_READY", rule="chart_report_projection")
    input_refs = document.get("input_artifact_refs")
    if not isinstance(input_refs, list) or not input_refs or any(not isinstance(item, str) or not item or any(ch.isspace() for ch in item) for item in input_refs):
        raise RuntimeContractError("Report Projection input refs are invalid", code="SCHEMA_INVALID", rule="chart_report_projection")
    if len(set(input_refs)) != len(input_refs):
        raise RuntimeContractError("Report Projection input refs must be unique", code="SCHEMA_INVALID", rule="chart_report_projection")
    groups = document.get("fact_groups")
    if not isinstance(groups, list) or not groups:
        raise RuntimeContractError("Report Projection must contain fact groups", code="SCHEMA_INVALID", rule="chart_report_projection")

    all_claims: set[str] = set()
    all_evidence: set[str] = set()
    all_sources: set[str] = set()
    evidence_to_claims: dict[str, set[str]] = {}
    for group in groups:
        if not isinstance(group, Mapping):
            raise RuntimeContractError("Fact Group must be an object", code="SCHEMA_INVALID", rule="chart_report_projection")
        facts = group.get("facts")
        if not isinstance(facts, list) or not facts:
            raise RuntimeContractError("Fact Group must contain facts", code="SCHEMA_INVALID", rule="chart_report_projection")
        group_sources: set[str] = set()
        for fact in facts:
            if not isinstance(fact, Mapping):
                raise RuntimeContractError("Projected Fact must be an object", code="SCHEMA_INVALID", rule="chart_report_projection")
            claims = _id_list(fact.get("claim_refs"), _CLAIM_ID, rule="chart_report_projection", allow_empty=False)
            evidence = _id_list(fact.get("evidence_refs"), _EVIDENCE_ID, rule="chart_report_projection", allow_empty=False)
            sources = _id_list(fact.get("source_refs"), _SOURCE_ID, rule="chart_report_projection", allow_empty=False)
            all_claims.update(claims)
            all_evidence.update(evidence)
            all_sources.update(sources)
            group_sources.update(sources)
            for evidence_id in evidence:
                evidence_to_claims.setdefault(evidence_id, set()).update(claims)
        declared_sources = set(_id_list(group.get("citation_source_ids"), _SOURCE_ID, rule="chart_report_projection", allow_empty=False))
        if declared_sources != group_sources:
            raise RuntimeContractError("Fact Group Citation Closure is not minimal", code="SCHEMA_INVALID", rule="chart_projection_closure")

    closure = document.get("citation_closure")
    if not isinstance(closure, Mapping) or set(closure) != {"claim_ids", "evidence_ids", "source_ids"}:
        raise RuntimeContractError("Report Projection Citation Closure is invalid", code="SCHEMA_INVALID", rule="chart_projection_closure")
    declared_claims = set(_id_list(closure.get("claim_ids"), _CLAIM_ID, rule="chart_projection_closure", allow_empty=False))
    declared_evidence = set(_id_list(closure.get("evidence_ids"), _EVIDENCE_ID, rule="chart_projection_closure", allow_empty=False))
    declared_sources = set(_id_list(closure.get("source_ids"), _SOURCE_ID, rule="chart_projection_closure", allow_empty=False))
    if (declared_claims, declared_evidence, declared_sources) != (all_claims, all_evidence, all_sources):
        raise RuntimeContractError("Report Projection Citation Closure is not exact", code="SCHEMA_INVALID", rule="chart_projection_closure")
    provenance = _ProjectionProvenance(
        frozenset(all_claims),
        frozenset(all_evidence),
        MappingProxyType({key: frozenset(value) for key, value in evidence_to_claims.items()}),
    )
    return _artifact_ref(header), provenance


def _validate_chart_provenance(
    data: Mapping[str, Any],
    claim_refs: tuple[str, ...],
    evidence_ids: tuple[str, ...],
    projection: _ProjectionProvenance,
) -> None:
    rows = data.get("rows")
    if not isinstance(rows, list) or not rows:
        raise RuntimeContractError("Chart Data rows are invalid", code="SCHEMA_INVALID", rule="chart_data")
    row_evidence: set[str] = set()
    for row in rows:
        if not isinstance(row, Mapping):
            raise RuntimeContractError("Chart Data row must be an object", code="SCHEMA_INVALID", rule="chart_data")
        row_evidence.update(_id_list(row.get("evidence_refs"), _EVIDENCE_ID, rule="chart_data_evidence", allow_empty=False))
    if row_evidence != set(evidence_ids):
        raise RuntimeContractError(
            "Chart Bundle evidence_ids must exactly match rendered Chart Data evidence",
            code="INSUFFICIENT_EVIDENCE",
            rule="chart_provenance_closure",
        )
    if not row_evidence <= projection.evidence_ids:
        raise RuntimeContractError(
            "Chart Data references Evidence outside the Report Projection",
            code="INSUFFICIENT_EVIDENCE",
            rule="chart_provenance_dangling",
        )
    reachable_claims = {claim for evidence_id in row_evidence for claim in projection.evidence_to_claims[evidence_id]}
    if set(claim_refs) != reachable_claims or not reachable_claims <= projection.claim_ids:
        raise RuntimeContractError(
            "Chart Bundle Claim references must be the exact Projection claims reachable from rendered Evidence",
            code="INSUFFICIENT_EVIDENCE",
            rule="chart_provenance_closure",
        )


def _artifact_header(
    value: Any,
    *,
    expected_type: str,
    expected_skill: str | None = _PRODUCER_SKILL,
) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise RuntimeContractError("Artifact header must be an object", code="SCHEMA_INVALID", rule="chart_artifact_header")
    required = {"id", "type", "schema_version", "version", "produced_by", "created_at", "supersedes", "status"}
    allowed = required | {"content_hash"}
    if not required <= set(value) or set(value) - allowed:
        raise RuntimeContractError("Artifact header has missing or unsupported fields", code="SCHEMA_INVALID", rule="chart_artifact_header")
    if not isinstance(value["id"], str) or _ARTIFACT_ID.fullmatch(value["id"]) is None:
        raise RuntimeContractError("Artifact ID is invalid", code="SCHEMA_INVALID", rule="chart_artifact_header")
    if value["type"] != expected_type or value["schema_version"] != _CONTRACT_VERSION:
        raise RuntimeContractError("Artifact type or schema version is invalid", code="SCHEMA_INVALID", rule="chart_artifact_header")
    if isinstance(value["version"], bool) or not isinstance(value["version"], int) or value["version"] < 1:
        raise RuntimeContractError("Artifact version is invalid", code="SCHEMA_INVALID", rule="chart_artifact_header")
    producer = value["produced_by"]
    if not isinstance(producer, Mapping) or set(producer) != {"skill", "attempt"}:
        raise RuntimeContractError("Artifact producer is invalid", code="SCHEMA_INVALID", rule="chart_artifact_header")
    if not isinstance(producer["skill"], str) or _MACHINE_ID.fullmatch(producer["skill"]) is None:
        raise RuntimeContractError("Artifact producer skill is invalid", code="SCHEMA_INVALID", rule="chart_artifact_header")
    if expected_skill is not None and producer["skill"] != expected_skill:
        raise RuntimeContractError("Chart Artifact producer skill is invalid", code="SCHEMA_INVALID", rule="chart_artifact_header")
    if not isinstance(producer["attempt"], str) or _ATTEMPT_ID.fullmatch(producer["attempt"]) is None:
        raise RuntimeContractError("Artifact producer attempt is invalid", code="SCHEMA_INVALID", rule="chart_artifact_header")
    if not isinstance(value["created_at"], str) or not _is_datetime(value["created_at"]):
        raise RuntimeContractError("Artifact created_at is invalid", code="SCHEMA_INVALID", rule="chart_artifact_header")
    if value["supersedes"] is not None and (not isinstance(value["supersedes"], str) or not value["supersedes"]):
        raise RuntimeContractError("Artifact supersedes ref is invalid", code="SCHEMA_INVALID", rule="chart_artifact_header")
    if value["status"] not in {"active", "superseded", "invalidated"}:
        raise RuntimeContractError("Artifact status is invalid", code="SCHEMA_INVALID", rule="chart_artifact_header")
    if value.get("content_hash") is not None and (
        not isinstance(value["content_hash"], str) or re.fullmatch(r"sha256:[0-9a-fA-F]{64}", value["content_hash"]) is None
    ):
        raise RuntimeContractError("Artifact content hash is invalid", code="SCHEMA_INVALID", rule="chart_artifact_header")
    return deepcopy(dict(value))


def _asset_path(value: Any, *, filename: str) -> str:
    if not isinstance(value, str) or not value or "\\" in value or any(character.isspace() for character in value):
        raise RuntimeContractError("Chart asset path is unsafe", code="SECURITY_POLICY_VIOLATION", rule="chart_asset_path")
    if ":" in value or "?" in value or "#" in value:
        raise RuntimeContractError("Chart asset path must be local and relative", code="SECURITY_POLICY_VIOLATION", rule="chart_asset_path")
    path = PurePosixPath(value)
    if path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
        raise RuntimeContractError("Chart asset path escapes its local bundle", code="SECURITY_POLICY_VIOLATION", rule="chart_asset_path")
    if path.name != filename or path.parent.parent != _ASSET_ROOT or not path.parent.name:
        raise RuntimeContractError("Chart asset path is outside its chart directory", code="SECURITY_POLICY_VIOLATION", rule="chart_asset_scope")
    return path.as_posix()


def _try_png_export(svg: str, exporter: PngExporter | None) -> tuple[bytes | None, str]:
    if exporter is None:
        return None, "PNG exporter unavailable."
    try:
        payload = exporter(svg)
    except Exception:  # The SVG is already valid; PNG compatibility degrades to PARTIAL.
        return None, "PNG compatibility export failed."
    if not isinstance(payload, bytes) or not _valid_png(payload):
        return None, "PNG compatibility exporter returned invalid PNG data."
    return payload, ""


def _valid_png(payload: bytes) -> bool:
    """Validate the PNG container without decoding pixels or loading plugins."""

    if not payload.startswith(_PNG_SIGNATURE):
        return False
    offset = len(_PNG_SIGNATURE)
    chunk_names: list[bytes] = []
    while offset < len(payload):
        if len(payload) - offset < 12:
            return False
        length = struct.unpack(">I", payload[offset : offset + 4])[0]
        chunk_end = offset + 12 + length
        if chunk_end > len(payload):
            return False
        name = payload[offset + 4 : offset + 8]
        data = payload[offset + 8 : offset + 8 + length]
        expected_crc = struct.unpack(">I", payload[offset + 8 + length : chunk_end])[0]
        if zlib.crc32(name + data) & 0xFFFFFFFF != expected_crc:
            return False
        if not chunk_names:
            if name != b"IHDR" or length != 13:
                return False
            width, height = struct.unpack(">II", data[:8])
            if width == 0 or height == 0:
                return False
        chunk_names.append(name)
        offset = chunk_end
        if name == b"IEND":
            break
    return offset == len(payload) and chunk_names[-1:] == [b"IEND"] and b"IDAT" in chunk_names


def _insight_payload(
    observation: str,
    interpretation: str,
    implication: str,
    confidence: str,
    claims: tuple[str, ...],
    evidence: tuple[str, ...],
    limitations: tuple[str, ...],
) -> bytes:
    lines = [
        "# Chart Insight",
        "",
        f"Observation: {observation}",
        f"Interpretation: {interpretation}",
        f"Product implication: {implication}",
        f"Confidence: {confidence}",
        f"Claim refs: {', '.join(claims)}",
        f"Evidence IDs: {', '.join(evidence)}",
    ]
    if limitations:
        lines.extend(("Limitations:", *(f"- {item}" for item in limitations)))
    return ("\n".join(lines) + "\n").encode("utf-8")


def _canonical_json(value: Mapping[str, Any]) -> bytes:
    try:
        return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n").encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise RuntimeContractError("Chart input is not canonical JSON data", code="SCHEMA_INVALID", rule="chart_json") from exc


def _json_object(value: Any, *, rule: str) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise RuntimeContractError("Chart input must be an object", code="SCHEMA_INVALID", rule=rule)
    try:
        return json.loads(json.dumps(value, ensure_ascii=False, allow_nan=False))
    except (TypeError, ValueError) as exc:
        raise RuntimeContractError("Chart input must contain only finite JSON values", code="SCHEMA_INVALID", rule=rule) from exc


def _machine_id(value: Any, *, rule: str) -> str:
    if not isinstance(value, str) or _MACHINE_ID.fullmatch(value) is None:
        raise RuntimeContractError("Machine ID is invalid", code="SCHEMA_INVALID", rule=rule)
    return value


def _text(value: Any, *, rule: str) -> str:
    if not isinstance(value, str) or not value:
        raise RuntimeContractError("Required text is missing", code="SCHEMA_INVALID", rule=rule)
    return value


def _text_list(value: Any, *, rule: str, allow_empty: bool) -> tuple[str, ...]:
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
        raise RuntimeContractError("Text list is invalid", code="SCHEMA_INVALID", rule=rule)
    result = tuple(_text(item, rule=rule) for item in value)
    if not allow_empty and not result:
        raise RuntimeContractError("Text list must not be empty", code="SCHEMA_INVALID", rule=rule)
    return result


def _id_list(value: Any, pattern: re.Pattern[str], *, rule: str, allow_empty: bool) -> tuple[str, ...]:
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
        raise RuntimeContractError("Reference list is invalid", code="SCHEMA_INVALID", rule=rule)
    result = tuple(value)
    if (not allow_empty and not result) or any(not isinstance(item, str) or pattern.fullmatch(item) is None for item in result):
        raise RuntimeContractError("Reference list contains an invalid ID", code="SCHEMA_INVALID", rule=rule)
    if len(set(result)) != len(result):
        raise RuntimeContractError("Reference list must contain unique IDs", code="SCHEMA_INVALID", rule=rule)
    return result


def _artifact_ref(header: Mapping[str, Any]) -> str:
    return f"{header['id']}@{header['version']}"


def _stable_unique(items: Sequence[str]) -> tuple[str, ...]:
    return tuple(dict.fromkeys(items))


def _is_datetime(value: str) -> bool:
    normalized = value[:-1] + "+00:00" if value.endswith("Z") else value
    try:
        return datetime.fromisoformat(normalized).tzinfo is not None
    except ValueError:
        return False


def _freeze(value: Any) -> Any:
    if isinstance(value, Mapping):
        return MappingProxyType({key: _freeze(item) for key, item in value.items()})
    if isinstance(value, list):
        return tuple(_freeze(item) for item in value)
    if isinstance(value, tuple):
        return tuple(_freeze(item) for item in value)
    return value


def _thaw(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {key: _thaw(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [_thaw(item) for item in value]
    return value
