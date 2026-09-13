"""Read-only post-chart Report Publication Projection materialization.

Recovery provenance:
    product_discovery_skillgraph_runtime-0.2.0-py3-none-any.whl
    skillgraph_runtime/publication_projection.py

The recovered implementation is intentionally a pure function.  It consumes
typed, already-materialized inputs and never reads SVG, HTML, URLs, or the
filesystem to discover facts.
"""

from __future__ import annotations

import hashlib
import re
from collections.abc import Mapping, Sequence
from typing import Any

from .errors import RuntimeContractError
from .fact_provenance import canonical_value_hash


_ARTIFACT_ID = re.compile(r"^ART-[A-Za-z0-9_-]+$")
_CLAIM_ID = re.compile(r"^CL-[A-Za-z0-9_-]+$")
_EVIDENCE_ID = re.compile(r"^EV-[A-Za-z0-9_-]+$")
_SOURCE_ID = re.compile(r"^SRC-[A-Za-z0-9_-]+$")
_MACHINE_ID = re.compile(r"^[a-z][a-z0-9]*(?:[_-][a-z0-9]+)*$")


def _fail(message: str, *, rule: str = "publication_projection", code: str = "SCHEMA_INVALID") -> None:
    raise RuntimeContractError(message, code=code, rule=rule)


def _artifact_ref(document: Mapping[str, Any], *, expected_type: str, rule: str) -> str:
    header = document.get("artifact")
    if not isinstance(header, Mapping) or header.get("type") != expected_type:
        _fail(f"Artifact is not typed as {expected_type}", rule=rule)
    artifact_id = header.get("id")
    version = header.get("version")
    if (
        not isinstance(artifact_id, str)
        or _ARTIFACT_ID.fullmatch(artifact_id) is None
        or isinstance(version, bool)
        or not isinstance(version, int)
        or version < 1
    ):
        _fail("Artifact header is malformed", rule=rule)
    return f"{artifact_id}@{version}"


def _string_refs(value: Any, *, pattern: re.Pattern[str], field: str) -> tuple[str, ...]:
    if not isinstance(value, (list, tuple)) or not value:
        _fail(f"{field} must be a non-empty reference list")
    refs = tuple(value)
    if any(not isinstance(item, str) or pattern.fullmatch(item) is None for item in refs):
        _fail(f"{field} contains a malformed reference")
    if len(refs) != len(set(refs)):
        _fail(f"{field} contains duplicate references")
    return refs


def _record_index(
    records: Sequence[Mapping[str, Any]],
    *,
    pattern: re.Pattern[str],
    label: str,
) -> dict[str, Mapping[str, Any]]:
    if isinstance(records, (str, bytes, bytearray)) or not isinstance(records, Sequence):
        _fail(f"{label} records are malformed")
    indexed: dict[str, Mapping[str, Any]] = {}
    for record in records:
        if not isinstance(record, Mapping):
            _fail(f"{label} record is malformed")
        identifier = record.get("id")
        if not isinstance(identifier, str) or pattern.fullmatch(identifier) is None:
            _fail(f"{label} record identity is malformed")
        if identifier in indexed:
            _fail(f"{label} records contain a duplicate identity")
        indexed[identifier] = record
    return indexed


def _source_index(sources: Mapping[str, Mapping[str, Any]]) -> dict[str, Mapping[str, Any]]:
    if not isinstance(sources, Mapping):
        _fail("Source records are malformed")
    indexed: dict[str, Mapping[str, Any]] = {}
    for source_id, record in sources.items():
        if not isinstance(source_id, str) or _SOURCE_ID.fullmatch(source_id) is None or not isinstance(record, Mapping):
            _fail("Source record is malformed")
        if record.get("id") != source_id:
            _fail("Source record identity does not match its index key")
        indexed[source_id] = record
    return indexed


def _closure_from_groups(groups: Sequence[Mapping[str, Any]]) -> dict[str, list[str]]:
    values: dict[str, set[str]] = {"claim_ids": set(), "evidence_ids": set(), "source_ids": set()}
    for group in groups:
        facts = group.get("facts") if isinstance(group, Mapping) else None
        if not isinstance(facts, list) or not facts:
            _fail("Publication Projection Fact Group is malformed")
        for fact in facts:
            if not isinstance(fact, Mapping):
                _fail("Publication Projection Fact is malformed")
            values["claim_ids"].update(_string_refs(fact.get("claim_refs"), pattern=_CLAIM_ID, field="claim_refs"))
            values["evidence_ids"].update(
                _string_refs(fact.get("evidence_refs"), pattern=_EVIDENCE_ID, field="evidence_refs")
            )
            values["source_ids"].update(_string_refs(fact.get("source_refs"), pattern=_SOURCE_ID, field="source_refs"))
    return {key: sorted(entries) for key, entries in values.items()}


def _validate_fact_groups(
    groups: Sequence[Mapping[str, Any]],
    *,
    claims_by_id: Mapping[str, Mapping[str, Any]],
    evidence_by_id: Mapping[str, Mapping[str, Any]],
    sources_by_id: Mapping[str, Mapping[str, Any]],
) -> None:
    seen_group_ids: set[str] = set()
    seen_dom_scopes: set[str] = set()
    seen_fact_ids: set[str] = set()
    for group in groups:
        if not isinstance(group, Mapping):
            _fail("Publication Projection Fact Group is malformed")
        group_id = group.get("id")
        section_id = group.get("section_id")
        dom_scope = group.get("dom_scope_id")
        if not isinstance(group_id, str) or not group_id.startswith("FG-") or group_id in seen_group_ids:
            _fail("Publication Projection Fact Group identity is malformed or duplicated")
        if not isinstance(section_id, str) or _MACHINE_ID.fullmatch(section_id) is None:
            _fail("Publication Projection section identity is malformed")
        if not isinstance(dom_scope, str) or _MACHINE_ID.fullmatch(dom_scope) is None or dom_scope in seen_dom_scopes:
            _fail("Publication Projection DOM scope is malformed or duplicated")
        seen_group_ids.add(group_id)
        seen_dom_scopes.add(dom_scope)

        facts = group.get("facts")
        declared_sources = _string_refs(
            group.get("citation_source_ids"), pattern=_SOURCE_ID, field="citation_source_ids"
        )
        if not isinstance(facts, list) or not facts:
            _fail("Publication Projection Fact Group has no facts")
        provenance: set[tuple[tuple[str, ...], tuple[str, ...]]] = set()
        observed_sources: set[str] = set()
        for fact in facts:
            if not isinstance(fact, Mapping):
                _fail("Publication Projection Fact is malformed")
            fact_id = fact.get("fact_id")
            if not isinstance(fact_id, str) or not fact_id.startswith("FACT-") or fact_id in seen_fact_ids:
                _fail("Publication Projection Fact identity is malformed or duplicated")
            seen_fact_ids.add(fact_id)
            claim_refs = _string_refs(fact.get("claim_refs"), pattern=_CLAIM_ID, field="claim_refs")
            evidence_refs = _string_refs(fact.get("evidence_refs"), pattern=_EVIDENCE_ID, field="evidence_refs")
            source_refs = _string_refs(fact.get("source_refs"), pattern=_SOURCE_ID, field="source_refs")
            provenance.add((tuple(sorted(evidence_refs)), tuple(sorted(source_refs))))
            observed_sources.update(source_refs)
            expected_sources: set[str] = set()
            for claim_id in claim_refs:
                claim = claims_by_id.get(claim_id)
                if claim is None:
                    _fail("Publication Projection contains a dangling Claim reference")
                expected_evidence = _string_refs(
                    claim.get("evidence_ids"), pattern=_EVIDENCE_ID, field="claim.evidence_ids"
                )
                if not set(expected_evidence) <= set(evidence_refs):
                    _fail("Fact Binding does not contain its Claim Evidence closure")
            for evidence_id in evidence_refs:
                evidence_record = evidence_by_id.get(evidence_id)
                if evidence_record is None:
                    _fail("Publication Projection contains a dangling Evidence reference")
                claim_id = evidence_record.get("claim_id")
                source_id = evidence_record.get("source_id")
                if claim_id not in claim_refs:
                    _fail("Evidence does not belong to a referenced Claim")
                if source_id not in source_refs:
                    _fail("Fact Binding does not contain its Evidence Source closure")
                expected_sources.add(str(source_id))
            if set(source_refs) != expected_sources:
                _fail("Fact Binding Source closure is not minimal")
            if any(source_id not in sources_by_id for source_id in source_refs):
                _fail("Publication Projection contains a dangling Source reference")
        if len(provenance) != 1:
            _fail("Facts with different Evidence/Source provenance cannot share a Fact Group")
        if set(declared_sources) != observed_sources:
            _fail("Fact Group Citation Sources do not match its Fact Bindings")


def _validate_declared_closure(groups: Sequence[Mapping[str, Any]], declared: Any) -> None:
    if not isinstance(declared, Mapping):
        _fail("Report Projection Citation Closure is malformed")
    actual = _closure_from_groups(groups)
    for field, pattern in (
        ("claim_ids", _CLAIM_ID),
        ("evidence_ids", _EVIDENCE_ID),
        ("source_ids", _SOURCE_ID),
    ):
        refs = _string_refs(declared.get(field), pattern=pattern, field=f"citation_closure.{field}")
        if list(refs) != actual[field]:
            _fail("Report Projection Citation Closure is not the minimum stable closure")


def materialize_report_publication_projection(
    *,
    artifact: Mapping[str, Any],
    base_projection: Mapping[str, Any],
    chart_bundle_collection: Mapping[str, Any],
    claims: Sequence[Mapping[str, Any]],
    evidence: Sequence[Mapping[str, Any]],
    sources: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    """Combine closed text facts and explicit Chart observations without inference.

    Chart facts use only their declared Claim and Evidence references.  A
    mismatched or incomplete closure is rejected rather than repaired from SVG
    content, labels, URLs, or display text.
    """

    _artifact_ref(
        {"artifact": artifact},
        expected_type="report_publication_projection",
        rule="publication_projection_output",
    )
    base_ref = _artifact_ref(base_projection, expected_type="report_projection", rule="publication_projection")
    collection_ref = _artifact_ref(
        chart_bundle_collection, expected_type="chart_bundle_collection", rule="publication_projection"
    )
    if base_projection.get("verification_status") != "PENDING":
        _fail("Base Report Projection verification status must be PENDING")
    if base_projection.get("scoring_status") != "NOT_PERFORMED":
        _fail("Publication Projection cannot claim a Score without a Score input", code="DEPENDENCY_NOT_READY")

    claims_by_id = _record_index(claims, pattern=_CLAIM_ID, label="Claim")
    evidence_by_id = _record_index(evidence, pattern=_EVIDENCE_ID, label="Evidence")
    sources_by_id = _source_index(sources)
    base_groups = base_projection.get("fact_groups")
    bundles = chart_bundle_collection.get("bundles")
    if not isinstance(base_groups, list) or not base_groups or not isinstance(bundles, list) or not bundles:
        _fail("Publication Projection inputs are incomplete", code="DEPENDENCY_NOT_READY")

    groups = [dict(item) for item in base_groups if isinstance(item, Mapping)]
    if len(groups) != len(base_groups):
        _fail("Base Report Projection has a malformed Fact Group")
    _validate_fact_groups(
        groups,
        claims_by_id=claims_by_id,
        evidence_by_id=evidence_by_id,
        sources_by_id=sources_by_id,
    )
    _validate_declared_closure(base_groups, base_projection.get("citation_closure"))

    seen_chart_types: set[str] = set()
    seen_bundle_refs: set[str] = set()
    for bundle in sorted(
        bundles,
        key=lambda item: str(item.get("chart", {}).get("type", "")) if isinstance(item, Mapping) else "",
    ):
        if not isinstance(bundle, Mapping):
            _fail("Chart Bundle Collection has a malformed entry")
        origin_ref = _artifact_ref(bundle, expected_type="chart_bundle", rule="publication_projection")
        if origin_ref in seen_bundle_refs:
            _fail("Chart Bundle Collection has a duplicate Artifact reference")
        seen_bundle_refs.add(origin_ref)
        chart = bundle.get("chart")
        if not isinstance(chart, Mapping) or not isinstance(chart.get("type"), str):
            _fail("Chart Bundle has no chart type")
        chart_type = chart["type"]
        if _MACHINE_ID.fullmatch(chart_type) is None or chart_type in seen_chart_types:
            _fail("Chart Bundle Collection has a malformed or duplicate chart type")
        seen_chart_types.add(chart_type)

        claim_refs = _string_refs(bundle.get("claim_refs"), pattern=_CLAIM_ID, field="claim_refs")
        evidence_refs = _string_refs(bundle.get("evidence_ids"), pattern=_EVIDENCE_ID, field="evidence_ids")
        expected_evidence: set[str] = set()
        for claim_ref in claim_refs:
            claim = claims_by_id.get(claim_ref)
            if claim is None:
                _fail("Chart Bundle Claim closure is incomplete")
            expected_evidence.update(
                _string_refs(claim.get("evidence_ids"), pattern=_EVIDENCE_ID, field="claim.evidence_ids")
            )
        if set(evidence_refs) != expected_evidence:
            _fail("Chart Bundle Evidence closure is invalid")
        source_refs: set[str] = set()
        for evidence_ref in evidence_refs:
            evidence_record = evidence_by_id.get(evidence_ref)
            if evidence_record is None or evidence_record.get("claim_id") not in claim_refs:
                _fail("Chart Bundle Evidence closure is invalid")
            source_id = evidence_record.get("source_id")
            if not isinstance(source_id, str) or source_id not in sources_by_id:
                _fail("Chart Bundle Source closure is invalid")
            source_refs.add(source_id)

        value = bundle.get("observation")
        if not isinstance(value, str) or not value:
            _fail("Chart Bundle observation is required for Report publication")
        content_hash = canonical_value_hash(value)
        digest = hashlib.sha256(f"{origin_ref}\0/observation\0{content_hash}".encode()).hexdigest()[:20].upper()
        groups.append(
            {
                "id": f"FG-CHART-{chart_type.upper().replace('_', '-')}",
                "section_id": "svg-visualizations",
                "dom_scope_id": f"chart-{chart_type.replace('_', '-')}",
                "facts": [
                    {
                        "fact_id": f"FACT-CHART-{digest}",
                        "origin_artifact_ref": origin_ref,
                        "origin_field_pointer": "/observation",
                        "content_hash": content_hash,
                        "fact_class": "chart",
                        "claim_refs": sorted(claim_refs),
                        "evidence_refs": sorted(evidence_refs),
                        "source_refs": sorted(source_refs),
                    }
                ],
                "citation_source_ids": sorted(source_refs),
            }
        )

    _validate_fact_groups(
        groups,
        claims_by_id=claims_by_id,
        evidence_by_id=evidence_by_id,
        sources_by_id=sources_by_id,
    )
    return {
        "artifact": dict(artifact),
        "report_projection_ref": base_ref,
        "chart_bundle_collection_ref": collection_ref,
        "fact_groups": groups,
        "citation_closure": _closure_from_groups(groups),
        "verification_status": "PENDING",
        "scoring_status": "NOT_PERFORMED",
    }
