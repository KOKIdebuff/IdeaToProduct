"""Validate Product Discovery SkillGraph Step 1 contracts.

This is a static repository validator, not the normative Runtime CLI described by
SPEC v0.1. It never fetches remote schemas and never mutates repository files.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import xml.etree.ElementTree as ET
from dataclasses import dataclass, replace
from decimal import Decimal, InvalidOperation
from html.parser import HTMLParser
from pathlib import Path, PurePosixPath
from typing import Any, Iterable, Mapping
from urllib.parse import unquote, urlparse

import yaml
from jsonschema import Draft202012Validator, FormatChecker
from jsonschema.exceptions import SchemaError
from referencing import Registry, Resource

try:
    from skillgraph_runtime.bundles import (
        BundleContext,
        CompatibilityRule,
        ContractBundle,
        ContractResolutionError,
        VersionEntry,
        VersionRegistry,
        evaluate_legacy_input_ref,
        load_bundle_context,
        load_version_registry,
        resolve_contract_bundle,
        verify_integrity,
    )
except ModuleNotFoundError:  # direct ``python scripts/validate_contracts.py`` before editable install
    from contract_bundles import (  # type: ignore[no-redef]
        BundleContext,
        CompatibilityRule,
        ContractBundle,
        ContractResolutionError,
        VersionEntry,
        VersionRegistry,
        evaluate_legacy_input_ref,
        load_bundle_context,
        load_version_registry,
        resolve_contract_bundle,
        verify_integrity,
    )


ROOT = Path(__file__).resolve().parents[1]
SCHEMA_DIR = ROOT / "schemas"
PROFILE_DIR = ROOT / "profiles"
FIXTURE_MANIFEST = ROOT / "fixtures" / "contracts" / "manifest.json"
MAX_DOCUMENT_BYTES = 5 * 1024 * 1024
CONTRACT_VERSION = "0.1.0"

# These Contract Bundles are deliberately validated without being registered for
# Runtime resolution.  A staged Bundle is declarative-only: it must be locally
# complete and fail closed, but it must not become selectable for new, resumed,
# or audited Runs until a separate promotion task changes the Registry.
STAGED_STATIC_BUNDLE_ROOTS = {
    "0.3.1": "contracts/0.3.1",
    "0.3.2": "contracts/0.3.2",
}

REQUIRED_SCHEMA_NAMES = frozenset({
    "artifact-manifest.schema.json",
    "artifact.schema.json",
    "chart.schema.json",
    "claim.schema.json",
    "common.schema.json",
    "competitor.schema.json",
    "decision.schema.json",
    "evidence.schema.json",
    "executor-request.schema.json",
    "executor-result.schema.json",
    "gate.schema.json",
    "idea.schema.json",
    "profile.schema.json",
    "proof-result.schema.json",
    "readiness-result.schema.json",
    "research.schema.json",
    "run-policy.schema.json",
    "skill.schema.json",
    "source.schema.json",
    "subgraph.schema.json",
    "verification.schema.json",
    "workflow-state.schema.json",
    "workflow.schema.json",
})
REQUIRED_SKILL_IDS = frozenset({
    "idea-intake",
    "research-contract",
    "competitor-discovery",
    "competitor-ranking",
    "competitor-deep-dive",
    "competitor-normalizer",
    "competitor-analysis",
    "competitor-visualization",
    "competitor-verifier",
    "user-evidence",
    "market-landscape",
    "oss-tech-landscape",
    "research-verifier",
    "research-gap",
    "research-synthesis",
    "opportunity-mapping",
    "product-definition",
    "feasibility-review",
    "proof-planner",
    "mvp-scope",
    "prd-generator",
    "prd-consistency-verifier",
    "build-readiness-verifier",
})
REQUIRED_SUBGRAPH_IDS = frozenset({"competitor-research"})
REQUIRED_TEMPLATE_CONTRACTS = {
    "templates/competitor-report.md": "competitor_report",
    "templates/synthesis.md": "research_synthesis",
    "templates/product-definition.md": "product_definition",
    "templates/feasibility.md": "feasibility_review",
    "templates/prd.md": "prd",
}
V03_TEMPLATE_CONTRACTS = {
    "templates/competitor-report.html": "competitor_report",
    "templates/synthesis.md": "research_synthesis",
    "templates/product-definition.md": "product_definition",
    "templates/feasibility.md": "feasibility_review",
    "templates/prd.md": "prd",
}


def template_contracts_for_version(contract_version: str) -> Mapping[str, str]:
    """Return the closed template inventory for one Contract Bundle."""
    return V03_TEMPLATE_CONTRACTS if contract_version in {"0.3.0", "0.3.1", "0.3.2"} else REQUIRED_TEMPLATE_CONTRACTS


V031_EXTRA_SKILL_IDS = frozenset({
    "competitor-fact-provenance",
    "competitor-scoring",
    "competitor-score-verifier",
})

V032_EXTRA_SKILL_IDS = frozenset({
    *V031_EXTRA_SKILL_IDS,
    "competitor-chart-rendering",
    "report-publication-projection",
    "competitor-report-builder",
    "competitor-score-publisher",
}) - frozenset({"competitor-visualization"})


def required_skill_ids_for_version(contract_version: str) -> frozenset[str]:
    if contract_version == "0.3.2":
        return (REQUIRED_SKILL_IDS - frozenset({"competitor-visualization"})) | V032_EXTRA_SKILL_IDS
    return REQUIRED_SKILL_IDS | V031_EXTRA_SKILL_IDS if contract_version == "0.3.1" else REQUIRED_SKILL_IDS
SKILL_MARKDOWN_SECTIONS = (
    "Purpose",
    "Trigger",
    "Inputs",
    "Reads",
    "Tasks",
    "Required Outputs",
    "Evidence Rules",
    "Completion Criteria",
    "Verification",
    "Failure Conditions",
    "Retry Strategy",
    "Forbidden Behavior",
    "Permissions",
    "Budget",
    "Executor Requirements",
    "Next",
)
SKILL_INTERACTION_SECTION = "Interaction Model"
READINESS_SCHEMA_REF = "schemas/readiness-result.schema.json"

CORE_NODE_CONTRACTS: dict[str, tuple[str, str]] = {
    "idea": ("skill", "idea-intake"),
    "contract": ("skill", "research-contract"),
    "gate_research": ("human_gate", "research-scope"),
    "competitor": ("subgraph", "competitor-research"),
    "users": ("skill", "user-evidence"),
    "market": ("skill", "market-landscape"),
    "technology": ("skill", "oss-tech-landscape"),
    "research_verifier": ("verifier", "research-verifier"),
    "research_gap": ("skill", "research-gap"),
    "evidence_waiver": ("human_gate", "evidence-waiver"),
    "research_synthesis": ("skill", "research-synthesis"),
    "opportunity": ("skill", "opportunity-mapping"),
    "gate_direction": ("human_gate", "product-direction"),
    "definition": ("skill", "product-definition"),
    "feasibility": ("skill", "feasibility-review"),
    "proof": ("skill", "proof-planner"),
    "proof_result": ("external_input", "proof-result"),
    "scope": ("skill", "mvp-scope"),
    "gate_scope": ("human_gate", "mvp-scope"),
    "prd": ("skill", "prd-generator"),
    "prd_consistency_verifier": ("verifier", "prd-consistency-verifier"),
    "build_readiness_verifier": ("verifier", "build-readiness-verifier"),
}
COMPETITOR_SUBGRAPH_NODE_CONTRACTS: dict[str, tuple[str, str]] = {
    "discovery": ("skill", "competitor-discovery"),
    "candidate_ranking": ("skill", "competitor-ranking"),
    "deep_dive": ("skill", "competitor-deep-dive"),
    "normalizer": ("skill", "competitor-normalizer"),
    "feature_analysis": ("skill", "competitor-analysis"),
    "traction_analysis": ("skill", "competitor-analysis"),
    "review_analysis": ("skill", "competitor-analysis"),
    "pricing_analysis": ("skill", "competitor-analysis"),
    "visualization": ("skill", "competitor-visualization"),
    "competitor_verifier": ("verifier", "competitor-verifier"),
}
V031_COMPETITOR_SUBGRAPH_NODE_CONTRACTS: dict[str, tuple[str, str]] = {
    **COMPETITOR_SUBGRAPH_NODE_CONTRACTS,
    "fact_provenance": ("skill", "competitor-fact-provenance"),
    "scoring": ("skill", "competitor-scoring"),
    "score_verifier": ("verifier", "competitor-score-verifier"),
}

V032_COMPETITOR_SUBGRAPH_NODE_CONTRACTS: dict[str, tuple[str, str]] = {
    **{node_id: contract for node_id, contract in V031_COMPETITOR_SUBGRAPH_NODE_CONTRACTS.items() if node_id != "visualization"},
    "chart_rendering": ("skill", "competitor-chart-rendering"),
    "report_publication_projection": ("skill", "report-publication-projection"),
    "report_builder": ("skill", "competitor-report-builder"),
    "score_publisher": ("skill", "competitor-score-publisher"),
}


def competitor_subgraph_nodes_for_version(contract_version: str) -> Mapping[str, tuple[str, str]]:
    if contract_version == "0.3.2":
        return V032_COMPETITOR_SUBGRAPH_NODE_CONTRACTS
    return V031_COMPETITOR_SUBGRAPH_NODE_CONTRACTS if contract_version == "0.3.1" else COMPETITOR_SUBGRAPH_NODE_CONTRACTS
RESEARCH_BRANCHES = {"competitor", "users", "market", "technology"}
RESULT_FIELDS = {
    "node_status",
    "verification_result",
    "gate_decision",
    "feasibility_result",
    "proof_outcome",
}
IMPLEMENTATION_FIELDS = {"skill", "subgraph", "gate", "router", "contract"}
KIND_FIELD = {
    "skill": "skill",
    "verifier": "skill",
    "subgraph": "subgraph",
    "human_gate": "gate",
    "router": "router",
    "external_input": "contract",
}
PROFILE_EXPECTATIONS = {
    "developer_tool": {
        "modes": {"competitor": "required", "users": "required", "market": "required", "technology": "required"},
        "required": {"feature_matrix", "positioning_map", "momentum_comparison", "oss_activity"},
    },
    "ai_agent_product": {
        "modes": {"competitor": "required", "users": "required", "market": "required", "technology": "required"},
        "required": {"capability_matrix", "positioning_map", "cost_performance", "ecosystem_momentum"},
    },
    "consumer_app": {
        "modes": {"competitor": "required", "users": "required", "market": "required", "technology": "optional"},
        "required": {"feature_ux_matrix", "positioning_map"},
        "choose_one": {"pricing_comparison", "sentiment_distribution"},
    },
    "b2b_saas": {
        "modes": {"competitor": "required", "users": "required", "market": "required", "technology": "required"},
        "required": {"feature_matrix", "positioning_map", "pricing_comparison", "integration_security_coverage"},
    },
}

V031_RUBRIC_PATHS = {
    "developer_tool": "rubrics/developer-tool-scoring.yaml",
    "ai_agent_product": "rubrics/ai-agent-product-scoring.yaml",
    "consumer_app": "rubrics/consumer-app-scoring.yaml",
    "b2b_saas": "rubrics/b2b-saas-scoring.yaml",
}
V031_RUBRIC_DIMENSIONS = {
    "developer_tool": {"workflow_fit", "developer_experience", "extensibility_integration", "ai_capability", "ecosystem_maturity"},
    "ai_agent_product": {"agent_capability", "reliability_observability", "tool_model_integration", "cost_performance", "ecosystem_momentum"},
    "consumer_app": {"user_experience", "differentiation", "engagement_retention_signal", "trust_safety", "value_monetization"},
    "b2b_saas": {"workflow_fit", "integration_maturity", "security_compliance", "commercial_fit", "differentiation"},
}
V031_CHART_TEMPLATES = {
    "feature_matrix": ("matrix", "competitor_by_dimension_cells"),
    "feature_ux_matrix": ("matrix", "competitor_by_dimension_cells"),
    "capability_matrix": ("matrix", "competitor_by_dimension_cells"),
    "integration_security_coverage": ("matrix", "competitor_by_dimension_cells"),
    "positioning_map": ("scatter", "competitor_xy_points"),
    "momentum_comparison": ("bar", "category_values"),
    "ecosystem_momentum": ("bar", "category_values"),
    "cost_performance": ("bar", "category_values"),
    "pricing_comparison": ("bar", "category_values"),
    "oss_activity": ("line", "time_series_values"),
    "sentiment_distribution": ("distribution", "bucket_counts"),
}


def auxiliary_contract_check_count(contract_version: str) -> int:
    """Return the deterministic count of non-schema staged Contract checks."""
    return 5 if contract_version in {"0.3.1", "0.3.2"} else 0


@dataclass(frozen=True)
class Diagnostic:
    source: str
    path: str
    rule: str
    message: str

    def render(self) -> str:
        location = f"{self.source}:{self.path}" if self.path else self.source
        return f"{location} [{self.rule}] {self.message}"


@dataclass(frozen=True)
class RepositoryCatalog:
    root: Path
    schema_names: frozenset[str]
    skill_ids: frozenset[str]
    subgraph_ids: frozenset[str]
    template_paths: frozenset[str]
    rubric_paths: frozenset[str]
    chart_template_paths: frozenset[str]


class DuplicateKeyError(ValueError):
    """Raised when YAML contains a duplicate mapping key."""


class _UniqueKeySafeLoader(yaml.SafeLoader):
    pass


def _construct_unique_mapping(loader: _UniqueKeySafeLoader, node: yaml.MappingNode, deep: bool = False) -> dict[Any, Any]:
    mapping: dict[Any, Any] = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=deep)
        try:
            duplicate = key in mapping
        except TypeError as exc:
            raise DuplicateKeyError(f"Unhashable YAML mapping key at line {key_node.start_mark.line + 1}") from exc
        if duplicate:
            raise DuplicateKeyError(f"Duplicate YAML key {key!r} at line {key_node.start_mark.line + 1}")
        mapping[key] = loader.construct_object(value_node, deep=deep)
    return mapping


_UniqueKeySafeLoader.add_constructor(
    yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG,
    _construct_unique_mapping,
)


def _safe_load_unique_yaml(text: str) -> Any:
    """Load YAML with SafeLoader semantics while rejecting duplicate keys."""
    loader = _UniqueKeySafeLoader(text)
    try:
        return loader.get_single_data()
    finally:
        loader.dispose()


def _construct_unique_json_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise DuplicateKeyError(f"Duplicate JSON key {key!r}")
        result[key] = value
    return result


def _display_path(path: Path) -> str:
    try:
        return path.resolve().relative_to(ROOT).as_posix()
    except ValueError:
        return str(path)


def _json_path(parts: Iterable[Any]) -> str:
    result = "$"
    for part in parts:
        if isinstance(part, int):
            result += f"[{part}]"
        else:
            result += f".{part}"
    return result


def load_document(path: Path) -> Any:
    size = path.stat().st_size
    if size > MAX_DOCUMENT_BYTES:
        raise ValueError(f"Document exceeds {MAX_DOCUMENT_BYTES} byte limit: {path}")
    text = path.read_text(encoding="utf-8")
    if path.suffix.lower() == ".json":
        return json.loads(text, object_pairs_hook=_construct_unique_json_object)
    return _safe_load_unique_yaml(text)


def _is_within(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
    except (OSError, ValueError):
        return False
    return True


def _contains_symlink(path: Path, root: Path) -> bool:
    try:
        relative = path.absolute().relative_to(root.absolute())
    except ValueError:
        return True
    current = root.absolute()
    for part in relative.parts:
        current = current / part
        if current.is_symlink():
            return True
    return False


def build_repository_catalog(root: Path = ROOT) -> RepositoryCatalog:
    schema_dir = root / "schemas"
    skill_dir = root / "skills"
    subgraph_dir = root / "subgraphs"
    template_dir = root / "templates"
    return RepositoryCatalog(
        root=root,
        schema_names=frozenset(path.name for path in schema_dir.glob("*.schema.json") if path.is_file()),
        skill_ids=frozenset(path.name for path in skill_dir.iterdir() if path.is_dir()) if skill_dir.is_dir() else frozenset(),
        subgraph_ids=frozenset(path.stem for path in subgraph_dir.glob("*.yaml") if path.is_file()),
        template_paths=frozenset(
            path.relative_to(root).as_posix()
            for pattern in ("*.md", "*.html")
            for path in template_dir.glob(pattern)
            if path.is_file()
        ),
        rubric_paths=frozenset(
            path.relative_to(root).as_posix()
            for path in (root / "rubrics").glob("*.yaml")
            if path.is_file()
        ),
        chart_template_paths=frozenset(
            path.relative_to(root).as_posix()
            for path in (root / "chart-templates").glob("*.yaml")
            if path.is_file()
        ),
    )


def _inventory_difference_diagnostics(
    actual: frozenset[str],
    expected: frozenset[str],
    source: str,
    label: str,
    contract_version: str = CONTRACT_VERSION,
) -> list[Diagnostic]:
    diagnostics: list[Diagnostic] = []
    missing = sorted(expected - actual)
    unexpected = sorted(actual - expected)
    if missing:
        diagnostics.append(Diagnostic(source, "$", "missing_contract_asset", f"Missing v{contract_version} {label}: {', '.join(missing)}"))
    if unexpected:
        diagnostics.append(Diagnostic(source, "$", "unexpected_contract_asset", f"Unexpected v{contract_version} {label}: {', '.join(unexpected)}"))
    return diagnostics


def repository_inventory_diagnostics(
    catalog: RepositoryCatalog,
    *,
    contract_version: str = CONTRACT_VERSION,
) -> list[Diagnostic]:
    diagnostics: list[Diagnostic] = []
    diagnostics.extend(_inventory_difference_diagnostics(catalog.schema_names, REQUIRED_SCHEMA_NAMES, "schemas", "schemas", contract_version))
    required_skill_ids = required_skill_ids_for_version(contract_version)
    diagnostics.extend(_inventory_difference_diagnostics(catalog.skill_ids, required_skill_ids, "skills", "skills", contract_version))
    diagnostics.extend(_inventory_difference_diagnostics(catalog.subgraph_ids, REQUIRED_SUBGRAPH_IDS, "subgraphs", "subgraphs", contract_version))
    diagnostics.extend(_inventory_difference_diagnostics(
        catalog.template_paths,
        frozenset(template_contracts_for_version(contract_version)),
        "templates",
        "templates",
        contract_version,
    ))

    if contract_version in {"0.3.1", "0.3.2"}:
        diagnostics.extend(_inventory_difference_diagnostics(
            catalog.rubric_paths,
            frozenset({
                "rubrics/developer-tool-scoring.yaml",
                "rubrics/ai-agent-product-scoring.yaml",
                "rubrics/consumer-app-scoring.yaml",
                "rubrics/b2b-saas-scoring.yaml",
            }),
            "rubrics",
            "rubrics",
            contract_version,
        ))
        diagnostics.extend(_inventory_difference_diagnostics(
            catalog.chart_template_paths,
            frozenset({"chart-templates/registry.yaml"}),
            "chart-templates",
            "chart template registries",
            contract_version,
        ))

    for skill_id in sorted(required_skill_ids & catalog.skill_ids):
        for filename in ("SKILL.md", "skill.yaml"):
            path = catalog.root / "skills" / skill_id / filename
            source = path.relative_to(catalog.root).as_posix()
            if not path.is_file():
                diagnostics.append(Diagnostic(source, "$", "missing_contract_asset", f"Skill {skill_id} must contain {filename}"))

    expected_paths = [
        *(catalog.root / "schemas" / name for name in REQUIRED_SCHEMA_NAMES & catalog.schema_names),
        *(catalog.root / "subgraphs" / f"{name}.yaml" for name in REQUIRED_SUBGRAPH_IDS & catalog.subgraph_ids),
        *(catalog.root / path for path in set(template_contracts_for_version(contract_version)) & catalog.template_paths),
    ]
    for skill_id in required_skill_ids & catalog.skill_ids:
        expected_paths.extend([
            catalog.root / "skills" / skill_id / "skill.yaml",
            catalog.root / "skills" / skill_id / "SKILL.md",
        ])
    if contract_version in {"0.3.1", "0.3.2"}:
        expected_paths.extend(catalog.root / path for path in catalog.rubric_paths)
        expected_paths.extend(catalog.root / path for path in catalog.chart_template_paths)
    for path in expected_paths:
        if path.exists() and (_contains_symlink(path, catalog.root) or not _is_within(path, catalog.root)):
            diagnostics.append(Diagnostic(_display_path(path), "$", "unsafe_contract_path", "Contract assets may not use symbolic links or escape the repository"))
    return diagnostics


def load_schemas(schema_dir: Path = SCHEMA_DIR) -> tuple[dict[str, dict[str, Any]], Registry]:
    schemas: dict[str, dict[str, Any]] = {}
    resources: list[tuple[str, Resource[Any]]] = []
    for path in sorted(schema_dir.glob("*.schema.json")):
        schema = load_document(path)
        if not isinstance(schema, dict):
            raise TypeError(f"Schema must be an object: {path}")
        schema = dict(schema)
        schema.setdefault("$id", path.resolve().as_uri())
        schemas[path.name] = schema
        resources.append((path.resolve().as_uri(), Resource.from_contents(schema)))
    return schemas, Registry().with_resources(resources)


def schema_diagnostics(schemas: dict[str, dict[str, Any]]) -> list[Diagnostic]:
    diagnostics: list[Diagnostic] = []
    for name, schema in schemas.items():
        try:
            Draft202012Validator.check_schema(schema)
        except SchemaError as exc:
            diagnostics.append(Diagnostic(f"schemas/{name}", _json_path(exc.path), "meta_schema", exc.message))
    diagnostics.extend(reference_diagnostics(schemas))
    diagnostics.extend(artifact_schema_diagnostics(schemas))
    diagnostics.extend(competitor_verification_contract_diagnostics(schemas))
    return diagnostics


def _walk_refs(value: Any, path: tuple[Any, ...] = ()) -> Iterable[tuple[tuple[Any, ...], str]]:
    if isinstance(value, dict):
        for key, child in value.items():
            child_path = path + (key,)
            if key == "$ref" and isinstance(child, str):
                yield child_path, child
            else:
                yield from _walk_refs(child, child_path)
    elif isinstance(value, list):
        for index, child in enumerate(value):
            yield from _walk_refs(child, path + (index,))


def _resolve_pointer(document: Any, fragment: str) -> bool:
    if fragment in ("", "#"):
        return True
    if not fragment.startswith("#/"):
        return False
    current = document
    for raw in fragment[2:].split("/"):
        token = unquote(raw).replace("~1", "/").replace("~0", "~")
        if isinstance(current, dict) and token in current:
            current = current[token]
        elif isinstance(current, list) and token.isdigit() and int(token) < len(current):
            current = current[int(token)]
        else:
            return False
    return True


def _pointer_value(document: Any, fragment: str) -> Any | None:
    if fragment in ("", "#"):
        return document
    if not fragment.startswith("#/"):
        return None
    current = document
    for raw in fragment[2:].split("/"):
        token = unquote(raw).replace("~1", "/").replace("~0", "~")
        if isinstance(current, dict) and token in current:
            current = current[token]
        elif isinstance(current, list) and token.isdigit() and int(token) < len(current):
            current = current[int(token)]
        else:
            return None
    return current


def reference_diagnostics(schemas: dict[str, dict[str, Any]]) -> list[Diagnostic]:
    diagnostics: list[Diagnostic] = []
    for owner, schema in schemas.items():
        for path, reference in _walk_refs(schema):
            parsed = urlparse(reference)
            if parsed.scheme or parsed.netloc or parsed.path.startswith(("/", "\\")):
                diagnostics.append(Diagnostic(f"schemas/{owner}", _json_path(path), "external_ref", "Only repository-local relative $ref values are allowed"))
                continue
            normalized_path = parsed.path.replace("\\", "/")
            path_parts = PurePosixPath(normalized_path).parts if normalized_path else ()
            if normalized_path and (len(path_parts) != 1 or ".." in path_parts or "." in path_parts):
                diagnostics.append(Diagnostic(f"schemas/{owner}", _json_path(path), "unsafe_ref", "Schema $ref must name a file in the local schemas directory without traversal"))
                continue
            target_name = parsed.path or owner
            target = schemas.get(Path(target_name).name)
            if target is None:
                diagnostics.append(Diagnostic(f"schemas/{owner}", _json_path(path), "dangling_ref", f"Referenced schema does not exist: {target_name}"))
                continue
            fragment = f"#{parsed.fragment}" if parsed.fragment else ""
            if not _resolve_pointer(target, fragment):
                diagnostics.append(Diagnostic(f"schemas/{owner}", _json_path(path), "dangling_ref", f"Referenced fragment does not exist: {reference}"))
    return diagnostics


def _parse_output_schema_ref(reference: Any) -> tuple[str, str] | None:
    if not isinstance(reference, str):
        return None
    parsed = urlparse(reference)
    if parsed.scheme or parsed.netloc or parsed.params or parsed.query:
        return None
    normalized = parsed.path.replace("\\", "/")
    parts = PurePosixPath(normalized).parts
    if len(parts) != 2 or parts[0] != "schemas" or parts[1] in {".", ".."}:
        return None
    fragment = f"#{parsed.fragment}" if parsed.fragment else ""
    if fragment and not fragment.startswith("#/"):
        return None
    return parts[1], fragment


def resolve_output_schema_reference(reference: Any, schemas: Mapping[str, dict[str, Any]]) -> tuple[str, Any] | None:
    parsed = _parse_output_schema_ref(reference)
    if parsed is None:
        return None
    schema_name, fragment = parsed
    schema = schemas.get(schema_name)
    if schema is None:
        return None
    value = _pointer_value(schema, fragment)
    if value is None:
        return None
    return schema_name, value


def _artifact_type_consts(
    value: Any,
    schemas: Mapping[str, dict[str, Any]],
    owner: str,
    seen: set[tuple[str, str]] | None = None,
) -> set[str]:
    if seen is None:
        seen = set()
    found: set[str] = set()
    if isinstance(value, dict):
        artifact_type = value.get("properties", {}).get("artifact", {}).get("properties", {}).get("type", {}).get("const")
        if isinstance(artifact_type, str):
            found.add(artifact_type)
        reference = value.get("$ref")
        if isinstance(reference, str):
            parsed = urlparse(reference)
            target_name = Path(parsed.path).name if parsed.path else owner
            fragment = f"#{parsed.fragment}" if parsed.fragment else ""
            marker = (target_name, fragment)
            target = schemas.get(target_name)
            if target is not None and marker not in seen:
                target_value = _pointer_value(target, fragment)
                if target_value is not None:
                    seen.add(marker)
                    found.update(_artifact_type_consts(target_value, schemas, target_name, seen))
        for key, child in value.items():
            if key not in {"$ref", "$defs"}:
                found.update(_artifact_type_consts(child, schemas, owner, seen))
    elif isinstance(value, list):
        for child in value:
            found.update(_artifact_type_consts(child, schemas, owner, seen))
    return found


def artifact_schema_diagnostics(schemas: Mapping[str, dict[str, Any]]) -> list[Diagnostic]:
    diagnostics: list[Diagnostic] = []
    for schema_name in ("idea.schema.json", "competitor.schema.json", "research.schema.json", "chart.schema.json"):
        schema = schemas.get(schema_name)
        if schema is None:
            continue
        references = {reference for _, reference in _walk_refs(schema)}
        if not any(urlparse(reference).path == "artifact.schema.json" for reference in references):
            diagnostics.append(Diagnostic(f"schemas/{schema_name}", "$", "artifact_schema_contract", "Business Artifact Schema must compose artifact.schema.json"))
        if not isinstance(schema.get("$ref"), str):
            diagnostics.append(Diagnostic(f"schemas/{schema_name}", "$.$ref", "artifact_schema_contract", "Business Artifact Schema must expose a top-level primary Artifact contract"))
        elif not _artifact_type_consts(schema, schemas, schema_name):
            diagnostics.append(Diagnostic(f"schemas/{schema_name}", "$", "artifact_schema_contract", "Business Artifact Schema must lock at least one artifact.type"))
    return diagnostics


def competitor_verification_contract_diagnostics(schemas: Mapping[str, dict[str, Any]]) -> list[Diagnostic]:
    schema = schemas.get("verification.schema.json")
    if schema is None:
        return []
    issue = schema.get("$defs", {}).get("competitor_issue", {})
    required = set(issue.get("required", [])) if isinstance(issue, dict) else set()
    return_to = issue.get("properties", {}).get("return_to", {}) if isinstance(issue, dict) else {}
    if {"retry_targets", "return_to"}.issubset(required) and return_to.get("const") == "competitor_verifier":
        return []
    return [Diagnostic(
        "schemas/verification.schema.json",
        "$.$defs.competitor_issue",
        "competitor_verification_contract",
        "Competitor verification issues must require retry_targets and return_to=competitor_verifier",
    )]


def validate_instance(
    instance: Any,
    schema_name: str,
    source: str,
    schemas: dict[str, dict[str, Any]],
    registry: Registry,
) -> list[Diagnostic]:
    parsed = urlparse(schema_name) if isinstance(schema_name, str) else None
    if (
        parsed is None
        or parsed.scheme
        or parsed.netloc
        or parsed.params
        or parsed.query
        or not parsed.path
        or len(PurePosixPath(parsed.path.replace("\\", "/")).parts) != 1
    ):
        return [Diagnostic(source, "$", "missing_schema", f"Schema not found: {schema_name}")]
    base_name = PurePosixPath(parsed.path.replace("\\", "/")).name
    fragment = f"#{parsed.fragment}" if parsed.fragment else ""
    if fragment and not fragment.startswith("#/"):
        return [Diagnostic(source, "$", "missing_schema", f"Schema not found: {schema_name}")]
    schema = schemas.get(base_name)
    if schema is None or _pointer_value(schema, fragment) is None:
        return [Diagnostic(source, "$", "missing_schema", f"Schema not found: {schema_name}")]
    schema_id = schema.get("$id")
    target: dict[str, Any]
    if fragment:
        if not isinstance(schema_id, str):
            return [Diagnostic(source, "$", "missing_schema", f"Schema not found: {schema_name}")]
        target = {"$ref": f"{schema_id}{fragment}"}
    else:
        target = schema
    validator = Draft202012Validator(target, registry=registry, format_checker=FormatChecker())
    return [
        Diagnostic(source, _json_path(error.absolute_path), str(error.validator or "schema"), error.message)
        for error in sorted(validator.iter_errors(instance), key=lambda item: list(item.absolute_path))
    ]


def _predicates(when: dict[str, Any] | None) -> list[dict[str, Any]]:
    if not when:
        return []
    if "any_of" in when:
        return list(when["any_of"])
    return [when]


def _cycle(nodes: dict[str, dict[str, Any]]) -> list[str] | None:
    visiting: list[str] = []
    states: dict[str, int] = {}

    def visit(node_id: str) -> list[str] | None:
        state = states.get(node_id, 0)
        if state == 1:
            index = visiting.index(node_id)
            return visiting[index:] + [node_id]
        if state == 2:
            return None
        states[node_id] = 1
        visiting.append(node_id)
        for dependency in nodes.get(node_id, {}).get("depends_on", []):
            if dependency in nodes:
                found = visit(dependency)
                if found:
                    return found
        visiting.pop()
        states[node_id] = 2
        return None

    for node_id in nodes:
        found = visit(node_id)
        if found:
            return found
    return None


def graph_semantics(
    nodes: dict[str, dict[str, Any]],
    source: str,
    *,
    path_prefix: str = "$.nodes",
    cycle_rule: str = "dag_cycle",
) -> list[Diagnostic]:
    diagnostics: list[Diagnostic] = []
    for node_id, node in nodes.items():
        if not isinstance(node, dict):
            continue
        dependencies = node.get("depends_on", [])
        if not isinstance(dependencies, list):
            continue
        if node_id in dependencies:
            diagnostics.append(Diagnostic(source, f"{path_prefix}.{node_id}.depends_on", "self_dependency", "Node cannot depend on itself"))
        for dependency in dependencies:
            if dependency not in nodes:
                diagnostics.append(Diagnostic(source, f"{path_prefix}.{node_id}.depends_on", "missing_dependency", f"Unknown dependency: {dependency}"))
    cycle = _cycle(nodes)
    if cycle:
        diagnostics.append(Diagnostic(source, path_prefix, cycle_rule, "Dependency cycle: " + " -> ".join(cycle)))
    return diagnostics


def workflow_semantics(
    document: dict[str, Any],
    source: str,
    catalog: RepositoryCatalog | None = None,
    *,
    contract_version: str = CONTRACT_VERSION,
) -> list[Diagnostic]:
    diagnostics: list[Diagnostic] = []
    workflow_metadata = document.get("workflow", {})
    if isinstance(workflow_metadata, dict):
        for field in ("version", "schema_version"):
            if workflow_metadata.get(field) != contract_version:
                diagnostics.append(Diagnostic(source, f"$.workflow.{field}", "contract_version", f"Workflow {field} must be {contract_version}"))
    nodes = document.get("nodes", {})
    if not isinstance(nodes, dict):
        return diagnostics

    missing_core = sorted(set(CORE_NODE_CONTRACTS) - set(nodes))
    if missing_core:
        diagnostics.append(Diagnostic(source, "$.nodes", "missing_core_nodes", f"Missing core nodes: {', '.join(missing_core)}"))
    diagnostics.extend(graph_semantics(nodes, source))

    for node_id, node in nodes.items():
        if not isinstance(node, dict):
            continue
        dependencies = node.get("depends_on", [])

        expected_field = KIND_FIELD.get(node.get("kind"))
        present_fields = IMPLEMENTATION_FIELDS.intersection(node)
        if expected_field and present_fields != {expected_field}:
            diagnostics.append(Diagnostic(source, f"$.nodes.{node_id}", "kind_contract", f"Kind {node.get('kind')} must use exactly {expected_field}; found {sorted(present_fields)}"))

        if catalog is not None and node.get("kind") in {"skill", "verifier"}:
            skill_id = node.get("skill")
            if isinstance(skill_id, str) and skill_id not in catalog.skill_ids:
                diagnostics.append(Diagnostic(source, f"$.nodes.{node_id}.skill", "missing_skill_reference", f"Referenced Skill Contract does not exist: {skill_id}"))
        if catalog is not None and node.get("kind") == "subgraph":
            subgraph_id = node.get("subgraph")
            if isinstance(subgraph_id, str) and subgraph_id not in catalog.subgraph_ids:
                diagnostics.append(Diagnostic(source, f"$.nodes.{node_id}.subgraph", "missing_subgraph_reference", f"Referenced Subgraph Contract does not exist: {subgraph_id}"))

        core_contract = CORE_NODE_CONTRACTS.get(node_id)
        if core_contract:
            expected_kind, expected_implementation = core_contract
            if node.get("kind") != expected_kind:
                diagnostics.append(Diagnostic(source, f"$.nodes.{node_id}.kind", "core_node_mapping", f"Core node {node_id} must keep kind {expected_kind}; found {node.get('kind')}"))
            else:
                implementation_field = KIND_FIELD[expected_kind]
                actual_implementation = node.get(implementation_field)
                if actual_implementation != expected_implementation:
                    diagnostics.append(Diagnostic(source, f"$.nodes.{node_id}.{implementation_field}", "core_node_mapping", f"Core node {node_id} must keep {implementation_field} {expected_implementation}; found {actual_implementation}"))

        for predicate in _predicates(node.get("when")):
            upstream_id = predicate.get("node")
            if upstream_id not in dependencies:
                diagnostics.append(Diagnostic(source, f"$.nodes.{node_id}.when", "condition_dependency", f"Condition node {upstream_id} must appear in depends_on"))
            upstream = nodes.get(upstream_id, {})
            result_fields = RESULT_FIELDS.intersection(predicate)
            if len(result_fields) != 1:
                diagnostics.append(Diagnostic(source, f"$.nodes.{node_id}.when", "condition_result_field", "Predicate must contain exactly one result field"))
                continue
            result_field = next(iter(result_fields))
            compatible = (
                result_field == "node_status"
                or (result_field == "verification_result" and upstream.get("kind") == "verifier")
                or (result_field == "gate_decision" and upstream.get("kind") == "human_gate")
                or (result_field == "feasibility_result" and upstream.get("skill") == "feasibility-review")
                or (result_field == "proof_outcome" and upstream.get("kind") == "external_input")
            )
            if not compatible:
                diagnostics.append(Diagnostic(source, f"$.nodes.{node_id}.when", "condition_type", f"{result_field} is incompatible with upstream node {upstream_id}"))

        loop = node.get("loop")
        if isinstance(loop, dict):
            for target in [*loop.get("always_invalidate", []), loop.get("return_to")]:
                if target and target not in nodes:
                    diagnostics.append(Diagnostic(source, f"$.nodes.{node_id}.loop", "missing_loop_target", f"Unknown loop target: {target}"))

        on_submit = node.get("on_submit")
        if isinstance(on_submit, dict):
            for target in [*on_submit.get("invalidate", []), on_submit.get("return_to")]:
                if target and target not in nodes:
                    diagnostics.append(Diagnostic(source, f"$.nodes.{node_id}.on_submit", "missing_submit_target", f"Unknown submit target: {target}"))
            schema_ref = on_submit.get("validate")
            selected_schema_dir = catalog.root / "schemas" if catalog is not None else SCHEMA_DIR
            if schema_ref and not (selected_schema_dir / schema_ref).is_file():
                diagnostics.append(Diagnostic(source, f"$.nodes.{node_id}.on_submit.validate", "missing_schema", f"Schema does not exist: {schema_ref}"))

        if "trigger_on_terminal_events" in node and node_id != "build_readiness_verifier":
            diagnostics.append(Diagnostic(source, f"$.nodes.{node_id}.trigger_on_terminal_events", "terminal_trigger_owner", "Only build_readiness_verifier may declare terminal triggers"))

        if node_id in RESEARCH_BRANCHES and node.get("configurable_by_profile") is not True:
            diagnostics.append(Diagnostic(source, f"$.nodes.{node_id}", "profile_branch", "Research branch must be configurable_by_profile"))
        if node_id not in RESEARCH_BRANCHES and node.get("configurable_by_profile"):
            diagnostics.append(Diagnostic(source, f"$.nodes.{node_id}", "profile_branch", "Only the four research branches may be profile-configurable"))

    readiness = nodes.get("build_readiness_verifier", {})
    readiness_writers = [node_id for node_id, node in nodes.items() if node.get("skill") == "build-readiness-verifier"]
    if readiness.get("kind") != "verifier" or readiness_writers != ["build_readiness_verifier"]:
        diagnostics.append(Diagnostic(source, "$.nodes.build_readiness_verifier", "readiness_writer", "Build Readiness Verifier must remain the unique readiness writer"))
    return diagnostics


def subgraph_semantics(
    document: dict[str, Any],
    source: str,
    catalog: RepositoryCatalog,
    skill_output_types: Mapping[str, set[str]] | None = None,
    *,
    contract_version: str = CONTRACT_VERSION,
) -> list[Diagnostic]:
    diagnostics: list[Diagnostic] = []
    metadata = document.get("subgraph", {})
    subgraph_id = metadata.get("id") if isinstance(metadata, dict) else None
    if source.startswith("subgraphs/") and source.endswith(".yaml"):
        expected_id = PurePosixPath(source).stem
        if subgraph_id != expected_id:
            diagnostics.append(Diagnostic(source, "$.subgraph.id", "contract_identity", f"Subgraph ID must match filename {expected_id}"))
    if isinstance(metadata, dict):
        for field in ("version", "schema_version"):
            if metadata.get(field) != contract_version:
                diagnostics.append(Diagnostic(source, f"$.subgraph.{field}", "contract_version", f"Subgraph {field} must be {contract_version}"))

    nodes = document.get("nodes", {})
    if not isinstance(nodes, dict):
        return diagnostics
    diagnostics.extend(graph_semantics(nodes, source, cycle_rule="subgraph_dag_cycle"))

    if subgraph_id == "competitor-research":
        expected_nodes = competitor_subgraph_nodes_for_version(contract_version)
        missing = sorted(set(expected_nodes) - set(nodes))
        if missing:
            diagnostics.append(Diagnostic(source, "$.nodes", "missing_subgraph_nodes", f"Missing competitor subgraph nodes: {', '.join(missing)}"))
        for node_id, (expected_kind, expected_skill) in expected_nodes.items():
            node = nodes.get(node_id)
            if not isinstance(node, dict):
                continue
            if node.get("kind") != expected_kind:
                diagnostics.append(Diagnostic(source, f"$.nodes.{node_id}.kind", "subgraph_node_mapping", f"Subgraph node {node_id} must keep kind {expected_kind}"))
            elif node.get("skill") != expected_skill:
                diagnostics.append(Diagnostic(source, f"$.nodes.{node_id}.skill", "subgraph_node_mapping", f"Subgraph node {node_id} must keep skill {expected_skill}"))

    for node_id, node in nodes.items():
        if not isinstance(node, dict) or node.get("kind") not in {"skill", "verifier"}:
            continue
        skill_id = node.get("skill")
        if isinstance(skill_id, str) and skill_id not in catalog.skill_ids:
            diagnostics.append(Diagnostic(source, f"$.nodes.{node_id}.skill", "missing_skill_reference", f"Referenced Skill Contract does not exist: {skill_id}"))
        if skill_id == "build-readiness-verifier":
            diagnostics.append(Diagnostic(source, f"$.nodes.{node_id}.skill", "readiness_writer", "Subgraphs cannot invoke the unique Build Readiness writer"))

    dependency_targets = {
        dependency
        for node in nodes.values()
        if isinstance(node, dict)
        for dependency in node.get("depends_on", [])
        if isinstance(dependency, str)
    }
    terminal_nodes = sorted(set(nodes) - dependency_targets)
    if subgraph_id == "competitor-research":
        expected_terminals = ["competitor_verifier"] if contract_version == "0.3.2" else (["competitor_verifier", "score_verifier"] if contract_version == "0.3.1" else ["competitor_verifier"])
        if terminal_nodes != expected_terminals:
            expectation = " and ".join(expected_terminals)
            diagnostics.append(Diagnostic(source, "$.nodes", "subgraph_terminal", f"Competitor Research terminal nodes must be exactly {expectation}"))
        if contract_version == "0.3.2":
            expected_optional = {
                "scoring": (["fact_provenance"], False),
                "score_verifier": (["scoring"], False),
                "score_publisher": (["report_builder", "score_verifier"], False),
                "competitor_verifier": (["report_builder", "score_publisher"], True),
            }
            for node_id, (dependencies, required) in expected_optional.items():
                node = nodes.get(node_id, {})
                if node.get("depends_on") != dependencies or node.get("required") is not required:
                    diagnostics.append(Diagnostic(source, f"$.nodes.{node_id}", "subgraph_optional_scoring", "v0.3.2 scoring path must preserve its optional dependencies and final Verifier gate"))

    for index, output in enumerate(document.get("output_contracts", [])):
        if not isinstance(output, dict):
            continue
        producer = output.get("producer")
        artifact_type = output.get("artifact_type")
        if producer not in nodes:
            diagnostics.append(Diagnostic(source, f"$.output_contracts[{index}].producer", "output_contract_producer", f"Unknown output producer: {producer}"))
            continue
        if skill_output_types is not None:
            producer_skill = nodes[producer].get("skill") if isinstance(nodes[producer], dict) else None
            if not isinstance(producer_skill, str) or artifact_type not in skill_output_types.get(producer_skill, set()):
                diagnostics.append(Diagnostic(source, f"$.output_contracts[{index}].artifact_type", "output_contract_producer", f"Producer {producer} does not declare output Artifact type {artifact_type}"))
    return diagnostics


def profile_semantics(
    document: dict[str, Any],
    source: str,
    workflow: dict[str, Any],
    catalog: RepositoryCatalog | None = None,
    *,
    contract_version: str = CONTRACT_VERSION,
) -> list[Diagnostic]:
    diagnostics: list[Diagnostic] = []
    profile_id = document.get("profile", {}).get("id")
    profile_version = document.get("profile", {}).get("version")
    if profile_version != contract_version:
        diagnostics.append(Diagnostic(source, "$.profile.version", "contract_version", f"Profile version must be {contract_version}"))
    if source.startswith("profiles/") and source.endswith(".yaml"):
        expected_id = PurePosixPath(source).stem.replace("-", "_")
        if profile_id != expected_id:
            diagnostics.append(Diagnostic(source, "$.profile.id", "contract_identity", f"Profile ID must match filename {expected_id}"))
    expected = PROFILE_EXPECTATIONS.get(profile_id)
    if expected:
        actual_modes = {key: value.get("mode") for key, value in document.get("research_nodes", {}).items()}
        if actual_modes != expected["modes"]:
            diagnostics.append(Diagnostic(source, "$.research_nodes", "profile_modes", f"Unexpected modes for {profile_id}: {actual_modes}"))
        actual_required = set(document.get("competitor_visualizations", {}).get("required", []))
        if actual_required != expected["required"]:
            diagnostics.append(Diagnostic(source, "$.competitor_visualizations.required", "profile_visualizations", f"Unexpected required visualizations for {profile_id}"))
        choose_one = document.get("competitor_visualizations", {}).get("choose_one")
        if "choose_one" in expected:
            if not choose_one or set(choose_one.get("options", [])) != expected["choose_one"]:
                diagnostics.append(Diagnostic(source, "$.competitor_visualizations.choose_one", "profile_choose_one", "Consumer profile must declare the Pricing/Sentiment choice"))
        elif choose_one is not None:
            diagnostics.append(Diagnostic(source, "$.competitor_visualizations.choose_one", "profile_choose_one", "Only consumer_app declares a visualization choice group in v0.1"))

    base_nodes = workflow.get("nodes", {})
    composed = {node_id: dict(node) for node_id, node in base_nodes.items()}
    for index, extension in enumerate(document.get("extensions", [])):
        extension_id = extension.get("id")
        if extension_id in composed:
            diagnostics.append(Diagnostic(source, f"$.extensions[{index}].id", "extension_collision", f"Extension ID collides with an existing node: {extension_id}"))
            continue
        after = extension.get("insert_after")
        before = extension.get("before")
        if after not in composed or before not in composed:
            diagnostics.append(Diagnostic(source, f"$.extensions[{index}]", "extension_anchor", "Extension anchors must reference existing nodes"))
            continue
        node = dict(extension.get("node", {}))
        extension_config = extension.get("config", {})
        if isinstance(extension_config, dict) and {"interaction", "max_rounds", "idea_shaping"}.intersection(extension_config):
            diagnostics.append(Diagnostic(source, f"$.extensions[{index}].config", "profile_interaction_override", "Profile extensions cannot override Idea Shaping interaction policy"))
        if catalog is not None and node.get("kind") in {"skill", "verifier"}:
            skill_id = node.get("skill")
            if isinstance(skill_id, str) and skill_id not in catalog.skill_ids:
                diagnostics.append(Diagnostic(source, f"$.extensions[{index}].node.skill", "missing_skill_reference", f"Referenced Skill Contract does not exist: {skill_id}"))
        if catalog is not None and node.get("kind") == "subgraph":
            subgraph_id = node.get("subgraph")
            if isinstance(subgraph_id, str) and subgraph_id not in catalog.subgraph_ids:
                diagnostics.append(Diagnostic(source, f"$.extensions[{index}].node.subgraph", "missing_subgraph_reference", f"Referenced Subgraph Contract does not exist: {subgraph_id}"))
        if node.get("skill") == "build-readiness-verifier" or "trigger_on_terminal_events" in node:
            diagnostics.append(Diagnostic(source, f"$.extensions[{index}].node", "readiness_writer", "Profile extensions cannot add a Readiness writer or terminal trigger"))
        if node.get("kind") == "human_gate" and not extension.get("config", {}).get("rationale"):
            diagnostics.append(Diagnostic(source, f"$.extensions[{index}].config", "extension_gate_rationale", "A profile-added Human Gate requires an explicit rationale"))
        node["depends_on"] = sorted(set(node.get("depends_on", [])) | {after})
        composed[extension_id] = node
        before_node = dict(composed[before])
        before_node["depends_on"] = sorted(set(before_node.get("depends_on", [])) | {extension_id})
        composed[before] = before_node
    cycle = _cycle(composed)
    if cycle:
        diagnostics.append(Diagnostic(source, "$.extensions", "extension_cycle", "Profile extension creates a cycle: " + " -> ".join(cycle)))
    return diagnostics


def v031_auxiliary_contract_diagnostics(
    catalog: RepositoryCatalog,
    *,
    contract_version: str = "0.3.1",
) -> list[Diagnostic]:
    """Validate Bundle-local Rubrics and the closed native Chart Registry."""
    diagnostics: list[Diagnostic] = []
    profile_documents: dict[str, dict[str, Any]] = {}

    for profile_id, expected_rubric_ref in V031_RUBRIC_PATHS.items():
        profile_path = catalog.root / "profiles" / f"{profile_id.replace('_', '-')}.yaml"
        source = profile_path.relative_to(catalog.root).as_posix()
        try:
            profile = load_document(profile_path)
        except (OSError, ValueError, TypeError, json.JSONDecodeError, yaml.YAMLError) as exc:
            diagnostics.append(Diagnostic(source, "$", "contract_load", str(exc)))
            continue
        if not isinstance(profile, dict):
            diagnostics.append(Diagnostic(source, "$", "contract_type", "Profile Contract must be an object"))
            continue
        profile_documents[profile_id] = profile
        if profile.get("scoring_rubric_ref") != expected_rubric_ref:
            diagnostics.append(Diagnostic(source, "$.scoring_rubric_ref", "scoring_rubric_reference", f"Profile {profile_id} must reference {expected_rubric_ref}"))

        rubric_path = catalog.root / expected_rubric_ref
        rubric_source = rubric_path.relative_to(catalog.root).as_posix()
        try:
            rubric_document = load_document(rubric_path)
        except (OSError, ValueError, TypeError, json.JSONDecodeError, yaml.YAMLError) as exc:
            diagnostics.append(Diagnostic(rubric_source, "$", "contract_load", str(exc)))
            continue
        if not isinstance(rubric_document, dict):
            diagnostics.append(Diagnostic(rubric_source, "$", "contract_type", "Scoring Rubric must be an object"))
            continue

        rubric = rubric_document.get("rubric")
        dimensions = rubric_document.get("dimensions")
        bands = rubric_document.get("score_bands")
        expected_ref = f"{profile_id}@{contract_version}"
        valid_header = (
            isinstance(rubric, dict)
            and rubric.get("id") == f"{profile_id}_scoring"
            and rubric.get("version") == "1.0.0"
            and rubric.get("profile_ref") == expected_ref
            and rubric.get("integer_only") is True
            and rubric.get("minimum") == 1
            and rubric.get("maximum") == 10
            and rubric.get("aggregation") == "weighted_arithmetic_mean"
            and rubric.get("minimum_weight_coverage") == 0.8
            and rubric.get("missing_evidence") == "renormalize_available_weights_partial"
            and rubric.get("tie_break") == "evidence_coverage_then_shared_rank"
            and isinstance(rubric.get("changelog"), list)
            and bool(rubric["changelog"])
        )
        if not valid_header:
            diagnostics.append(Diagnostic(rubric_source, "$.rubric", "scoring_rubric_contract", "Rubric header must lock the approved staged scoring policy"))

        if not isinstance(dimensions, list) or len(dimensions) != 5:
            diagnostics.append(Diagnostic(rubric_source, "$.dimensions", "scoring_rubric_contract", "Rubric must define exactly five dimensions"))
        else:
            dimension_ids = {item.get("id") for item in dimensions if isinstance(item, dict)}
            weights = [item.get("weight") for item in dimensions if isinstance(item, dict)]
            if (
                len(dimension_ids) != 5
                or dimension_ids != V031_RUBRIC_DIMENSIONS[profile_id]
                or len(weights) != 5
                or any(weight != 0.2 for weight in weights)
                or sum(weights) != 1.0
            ):
                diagnostics.append(Diagnostic(rubric_source, "$.dimensions", "scoring_rubric_contract", "Rubric dimensions must match the approved equal-weight Profile catalog"))

        expected_bands = [(1, 2), (3, 4), (5, 6), (7, 8), (9, 10)]
        actual_bands = [
            (item.get("minimum"), item.get("maximum"))
            for item in bands
            if isinstance(item, dict)
        ] if isinstance(bands, list) else []
        if actual_bands != expected_bands:
            diagnostics.append(Diagnostic(rubric_source, "$.score_bands", "scoring_rubric_contract", "Rubric score bands must cover the approved integer 1..10 range"))

    registry_path = catalog.root / "chart-templates" / "registry.yaml"
    registry_source = registry_path.relative_to(catalog.root).as_posix()
    try:
        registry_document = load_document(registry_path)
    except (OSError, ValueError, TypeError, json.JSONDecodeError, yaml.YAMLError) as exc:
        diagnostics.append(Diagnostic(registry_source, "$", "contract_load", str(exc)))
        return diagnostics
    if not isinstance(registry_document, dict):
        diagnostics.append(Diagnostic(registry_source, "$", "contract_type", "Chart Template Registry must be an object"))
        return diagnostics
    templates = registry_document.get("templates")
    if registry_document.get("contract_version") != contract_version or not isinstance(templates, dict):
        diagnostics.append(Diagnostic(registry_source, "$", "chart_template_registry", "Chart Template Registry must be versioned and contain templates"))
        return diagnostics
    if set(templates) != set(V031_CHART_TEMPLATES):
        diagnostics.append(Diagnostic(registry_source, "$.templates", "chart_template_registry", "Chart Template Registry must be closed to the approved chart IDs"))
    for chart_id, expected in V031_CHART_TEMPLATES.items():
        actual = templates.get(chart_id)
        if not isinstance(actual, dict) or (actual.get("renderer_kind"), actual.get("data_contract")) != expected:
            diagnostics.append(Diagnostic(registry_source, f"$.templates.{chart_id}", "chart_template_registry", "Chart template must preserve its registered renderer and data contract"))

    registered_chart_ids = set(templates) if isinstance(templates, dict) else set()
    for profile_id, profile in profile_documents.items():
        visualizations = profile.get("competitor_visualizations", {})
        required = visualizations.get("required", []) if isinstance(visualizations, dict) else []
        choose_one = visualizations.get("choose_one", {}) if isinstance(visualizations, dict) else {}
        optional = choose_one.get("options", []) if isinstance(choose_one, dict) else []
        declared = set(required) | set(optional) if isinstance(required, list) and isinstance(optional, list) else set()
        if not declared or not declared <= registered_chart_ids:
            diagnostics.append(Diagnostic(f"profiles/{profile_id.replace('_', '-')}.yaml", "$.competitor_visualizations", "chart_template_registry", "Every Profile visualization must exist in the closed Chart Template Registry"))

    svg_contract = registry_document.get("svg_contract")
    png_compatibility = registry_document.get("png_compatibility")
    if not isinstance(svg_contract, dict) or svg_contract.get("required_attributes") != ["viewBox", "role"] or svg_contract.get("required_elements") != ["title", "desc"] or svg_contract.get("external_references") != "forbidden" or svg_contract.get("network_dependency") != "forbidden":
        diagnostics.append(Diagnostic(registry_source, "$.svg_contract", "chart_template_registry", "SVG Contract must preserve the approved static, local, accessible constraints"))
    if not isinstance(png_compatibility, dict) or png_compatibility.get("canonical") is not False or png_compatibility.get("explicit_request_only") is not True or png_compatibility.get("failure_after_valid_svg") != "PARTIAL" or png_compatibility.get("svg_fallback") != "forbidden":
        diagnostics.append(Diagnostic(registry_source, "$.png_compatibility", "chart_template_registry", "PNG compatibility must remain optional PARTIAL output and never replace SVG"))
    return diagnostics


def _is_safe_relative_path(value: str) -> bool:
    if not isinstance(value, str) or not value or value.startswith(("/", "\\")) or re.match(r"^[A-Za-z]:", value):
        return False
    if "\\" in value or urlparse(value).scheme or urlparse(value).netloc:
        return False
    parts = PurePosixPath(value.rstrip("/")).parts
    return bool(parts) and "." not in parts and ".." not in parts


def path_semantics(document: dict[str, Any], source: str) -> list[Diagnostic]:
    candidates: list[tuple[str, Any]] = []
    if "skill" in document:
        candidates.extend(("$.reads", value) for value in document.get("reads", []))
        candidates.extend(("$.writes", value) for value in document.get("writes", []))
        candidates.extend(("$.permissions.workspace_write", value) for value in document.get("permissions", {}).get("workspace_write", []))
    if "executor_request" in document:
        candidates.extend(("$.executor_request.permissions.workspace_write_paths", value) for value in document["executor_request"].get("permissions", {}).get("workspace_write_paths", []))
    return [Diagnostic(source, path, "unsafe_path", f"Path must stay relative to the discovery workspace: {value}") for path, value in candidates if not isinstance(value, str) or not _is_safe_relative_path(value)]


def skill_markdown_diagnostics(
    text: str,
    source: str,
    expected_id: str,
    *,
    interaction_required: bool = False,
) -> list[Diagnostic]:
    diagnostics: list[Diagnostic] = []
    lines = text.splitlines()
    h1 = [(index, match.group(1).strip()) for index, line in enumerate(lines) if (match := re.fullmatch(r"#\s+(.+?)\s*", line))]
    expected_title = f"Skill: {expected_id}"
    if len(h1) != 1 or h1[0][1] != expected_title:
        diagnostics.append(Diagnostic(source, "$", "contract_identity", f"SKILL.md must declare exactly '# {expected_title}'"))

    h2 = [(index, match.group(1).strip()) for index, line in enumerate(lines) if (match := re.fullmatch(r"##\s+(.+?)\s*", line))]
    actual_sections = tuple(title for _, title in h2)
    expected_sections = list(SKILL_MARKDOWN_SECTIONS)
    if interaction_required:
        expected_sections.insert(expected_sections.index("Tasks") + 1, SKILL_INTERACTION_SECTION)
    expected_tuple = tuple(expected_sections)
    if actual_sections != expected_tuple:
        diagnostics.append(Diagnostic(source, "$", "skill_markdown_contract", f"Expected ordered sections: {', '.join(expected_tuple)}"))
        return diagnostics

    for position, (line_index, title) in enumerate(h2):
        end = h2[position + 1][0] if position + 1 < len(h2) else len(lines)
        content = [line.strip() for line in lines[line_index + 1:end] if line.strip() and not line.lstrip().startswith("#")]
        if not content:
            diagnostics.append(Diagnostic(source, f"$.sections.{title}", "skill_markdown_contract", f"Section {title} must not be empty"))
    if expected_id == "competitor-report-builder":
        forbidden_claims = (
            "generate the profile-required chart bundles",
            "generate renderer-independent data and chart specs",
            "write a `chart_bundle` collection",
        )
        lowered = text.lower()
        if any(claim in lowered for claim in forbidden_claims):
            diagnostics.append(Diagnostic(source, "$", "report_builder_ownership", "Report Builder must consume Chart outputs and must not claim Chart generation ownership"))
    return diagnostics


class _StaticHtmlTemplateParser(HTMLParser):
    """Collect the small, security-relevant HTML surface of a report template."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.tags: list[str] = []
        self.meta_values: dict[str, list[str]] = {}
        self.asset_references: list[tuple[str, str, str]] = []
        self.style_chunks: list[str] = []
        self.event_attributes: list[tuple[str, str]] = []
        self.has_doctype = False
        self.has_script = False
        self.has_base = False
        self.has_refresh = False
        self._style_depth = 0

    def handle_decl(self, decl: str) -> None:
        if decl.strip().lower() == "doctype html":
            self.has_doctype = True

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        normalized_tag = tag.lower()
        self.tags.append(normalized_tag)
        attributes = {name.lower(): value for name, value in attrs}
        if normalized_tag == "script":
            self.has_script = True
        if normalized_tag == "base":
            self.has_base = True
        if normalized_tag == "style":
            self._style_depth += 1
        if normalized_tag == "meta":
            name = attributes.get("name")
            content = attributes.get("content")
            if isinstance(name, str) and isinstance(content, str):
                self.meta_values.setdefault(name.lower(), []).append(content)
            if str(attributes.get("http-equiv", "")).lower() == "refresh":
                self.has_refresh = True
        for name, value in attrs:
            normalized_name = name.lower()
            if normalized_name.startswith("on"):
                self.event_attributes.append((normalized_tag, normalized_name))
            if normalized_name == "style" and isinstance(value, str):
                self.style_chunks.append(value)
        for attribute in ("href", "src", "srcset", "poster", "action", "formaction"):
            value = attributes.get(attribute)
            if isinstance(value, str):
                self.asset_references.append((normalized_tag, attribute, value))

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.handle_starttag(tag, attrs)
        self.handle_endtag(tag)

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() == "style" and self._style_depth:
            self._style_depth -= 1

    def handle_data(self, data: str) -> None:
        if self._style_depth:
            self.style_chunks.append(data)


def _is_safe_static_asset_reference(value: str, *, allow_anchor: bool = False) -> bool:
    if not isinstance(value, str) or not value or value.strip() != value:
        return False
    if allow_anchor and value.startswith("#"):
        return len(value) > 1
    parsed = urlparse(value)
    if parsed.scheme or parsed.netloc or parsed.query or value.startswith("//"):
        return False
    local_path = parsed.path
    return bool(local_path) and _is_safe_relative_path(local_path)


def _is_safe_passive_citation_reference(value: str) -> bool:
    """Allow a static source link without allowing it to become a loaded asset."""
    if not isinstance(value, str) or not value or value.strip() != value:
        return False
    parsed = urlparse(value)
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


def _html_template_contract_diagnostics(
    text: str,
    source: str,
    expected_artifact_type: str,
    *,
    contract_version: str,
) -> list[Diagnostic]:
    diagnostics: list[Diagnostic] = []
    parser = _StaticHtmlTemplateParser()
    try:
        parser.feed(text)
        parser.close()
    except (ValueError, TypeError) as exc:
        return [Diagnostic(source, "$", "template_contract", f"Invalid HTML template: {exc}")]
    if not parser.has_doctype or not {"html", "head", "body"}.issubset(parser.tags):
        diagnostics.append(Diagnostic(source, "$", "template_contract", "HTML template must contain <!doctype html>, <html>, <head>, and <body>"))

    expected = {
        "template-id": Path(source).stem,
        "template-version": contract_version,
        "artifact-type": expected_artifact_type,
    }
    actual = {name: values for name, values in parser.meta_values.items() if name in expected}
    if any(actual.get(name) != [value] for name, value in expected.items()):
        diagnostics.append(Diagnostic(source, "$.head.meta", "template_contract", f"Expected HTML identity metadata {expected}; found {actual}"))
    if parser.has_script:
        diagnostics.append(Diagnostic(source, "$.script", "static_html", "HTML competitor report templates must not contain script tags"))
    if parser.has_base:
        diagnostics.append(Diagnostic(source, "$.base", "static_html", "HTML competitor report templates must not contain a base URL"))
    if parser.has_refresh:
        diagnostics.append(Diagnostic(source, "$.meta.http-equiv", "static_html", "HTML competitor report templates must not refresh or navigate"))
    for tag, attribute in parser.event_attributes:
        diagnostics.append(Diagnostic(source, f"$.{tag}.{attribute}", "static_html", "HTML competitor report templates must not contain event-handler JavaScript"))

    for tag, attribute, value in parser.asset_references:
        values = value.split(",") if attribute == "srcset" else [value]
        for item in values:
            candidate = item.strip().split(maxsplit=1)[0]
            if tag == "a" and attribute == "href" and _is_safe_passive_citation_reference(candidate):
                continue
            if not _is_safe_static_asset_reference(candidate, allow_anchor=attribute == "href"):
                diagnostics.append(Diagnostic(
                    source,
                    f"$.{tag}.{attribute}",
                    "static_html_asset",
                    f"HTML report asset reference must be a safe local relative path: {value}",
                ))

    style_text = "\n".join(parser.style_chunks)
    css_references = [
        *re.findall(r"url\(\s*['\"]?([^'\")\s]+)", style_text, flags=re.IGNORECASE),
        *re.findall(r"@import\s+(?:url\(\s*)?['\"]?([^'\"\)\s;]+)", style_text, flags=re.IGNORECASE),
    ]
    for value in css_references:
        if not _is_safe_static_asset_reference(value):
            diagnostics.append(Diagnostic(
                source,
                "$.style",
                "static_html_asset",
                f"HTML report stylesheet reference must be a safe local relative path: {value}",
            ))
    if re.search(r"(?:expression\s*\(|behavior\s*:)", style_text, flags=re.IGNORECASE):
        diagnostics.append(Diagnostic(source, "$.style", "static_html", "HTML report styles must not contain executable behavior"))
    return diagnostics


def template_contract_diagnostics(
    text: str,
    source: str,
    expected_artifact_type: str,
    *,
    contract_version: str = CONTRACT_VERSION,
) -> list[Diagnostic]:
    if Path(source).suffix.lower() == ".html":
        return _html_template_contract_diagnostics(
            text,
            source,
            expected_artifact_type,
            contract_version=contract_version,
        )
    diagnostics: list[Diagnostic] = []
    match = re.match(r"\A---\s*\r?\n(.*?)\r?\n---\s*(?:\r?\n|\Z)", text, flags=re.DOTALL)
    if match is None:
        return [Diagnostic(source, "$", "template_contract", "Template must begin with YAML front matter")]
    try:
        front_matter = _safe_load_unique_yaml(match.group(1))
    except (yaml.YAMLError, DuplicateKeyError, TypeError, ValueError) as exc:
        return [Diagnostic(source, "$", "template_contract", f"Invalid template front matter: {exc}")]
    expected_id = Path(source).stem
    expected = {"id": expected_id, "version": contract_version, "artifact_type": expected_artifact_type}
    actual = front_matter.get("template") if isinstance(front_matter, dict) else None
    if actual != expected:
        diagnostics.append(Diagnostic(source, "$.template", "template_contract", f"Expected template metadata {expected}; found {actual}"))
    if not text[match.end():].strip():
        diagnostics.append(Diagnostic(source, "$", "template_contract", "Template body must not be empty"))
    return diagnostics


def _workspace_write_allows(write: str, grants: list[Any]) -> bool:
    normalized_write = write.rstrip("/")
    for grant in grants:
        if not isinstance(grant, str) or not _is_safe_relative_path(grant):
            continue
        normalized_grant = grant.rstrip("/")
        if normalized_write == normalized_grant or (grant.endswith("/") and normalized_write.startswith(normalized_grant + "/")):
            return True
    return False


def skill_contract_diagnostics(
    document: dict[str, Any],
    source: str,
    expected_id: str,
    catalog: RepositoryCatalog,
    schemas: Mapping[str, dict[str, Any]],
    *,
    contract_version: str = CONTRACT_VERSION,
) -> list[Diagnostic]:
    diagnostics = path_semantics(document, source)
    skill = document.get("skill", {})
    if skill.get("id") != expected_id:
        diagnostics.append(Diagnostic(source, "$.skill.id", "contract_identity", f"Skill ID must match directory name {expected_id}"))
    if skill.get("version") != contract_version:
        diagnostics.append(Diagnostic(source, "$.skill.version", "contract_version", f"Skill version must be {contract_version}"))

    interaction = document.get("interaction")
    if contract_version != "0.1.0" and expected_id == "idea-intake" and not isinstance(interaction, dict):
        diagnostics.append(Diagnostic(source, "$.interaction", "interaction_contract", "v0.2+ idea-intake must declare the adaptive Interaction Model"))
    if isinstance(interaction, dict) and expected_id != "idea-intake":
        diagnostics.append(Diagnostic(source, "$.interaction", "interaction_contract", "Only idea-intake may declare an Interaction Model in v0.2+"))

    writes = document.get("writes", [])
    output_contracts = document.get("output_contracts", [])
    declared_output_writes = [item.get("write") for item in output_contracts if isinstance(item, dict)]
    if isinstance(writes, list) and set(writes) != set(declared_output_writes):
        diagnostics.append(Diagnostic(source, "$.writes", "output_contract_write", "writes must equal the unique output_contracts write paths"))

    workspace_grants = document.get("permissions", {}).get("workspace_write", [])
    for index, output in enumerate(output_contracts):
        if not isinstance(output, dict):
            continue
        base_path = f"$.output_contracts[{index}]"
        artifact_type = output.get("artifact_type")
        write = output.get("write")
        if isinstance(write, str) and not _workspace_write_allows(write, workspace_grants):
            diagnostics.append(Diagnostic(source, f"{base_path}.write", "output_write_permission", f"Output path is not covered by permissions.workspace_write: {write}"))

        schema_ref = output.get("schema_ref")
        resolved = resolve_output_schema_reference(schema_ref, schemas)
        if resolved is None:
            diagnostics.append(Diagnostic(source, f"{base_path}.schema_ref", "output_schema_reference", f"Output Schema reference is unsafe or unresolved: {schema_ref}"))
        else:
            schema_name, fragment = resolved
            template_ref = output.get("template_ref")
            if schema_ref == "schemas/artifact.schema.json" and isinstance(template_ref, str):
                expected_template_type = template_contracts_for_version(contract_version).get(template_ref)
                if artifact_type != expected_template_type:
                    diagnostics.append(Diagnostic(source, f"{base_path}.artifact_type", "output_artifact_type", f"Artifact type {artifact_type} does not match Template contract {expected_template_type}"))
            else:
                artifact_types = _artifact_type_consts(fragment, schemas, schema_name)
                if artifact_type not in artifact_types:
                    diagnostics.append(Diagnostic(source, f"{base_path}.artifact_type", "output_artifact_type", f"Artifact type {artifact_type} is not locked by {schema_ref}"))

        template_ref = output.get("template_ref")
        if template_ref is not None:
            safe_template = isinstance(template_ref, str) and _is_safe_relative_path(template_ref) and template_ref.startswith("templates/")
            template_path = catalog.root / template_ref if safe_template else None
            if (
                not safe_template
                or template_ref not in catalog.template_paths
                or template_path is None
                or _contains_symlink(template_path, catalog.root)
                or not _is_within(template_path, catalog.root)
            ):
                diagnostics.append(Diagnostic(source, f"{base_path}.template_ref", "template_reference", f"Template reference is unsafe or unresolved: {template_ref}"))
    return diagnostics


def gate_semantics(document: dict[str, Any], source: str) -> list[Diagnostic]:
    gate = document.get("gate", {})
    gate_type = gate.get("gate_type")
    expected_actions = {
        "research_scope": {"APPROVE", "MODIFY", "CANCEL"},
        "mvp_scope": {"APPROVE", "MODIFY", "CANCEL"},
        "product_direction": {"APPROVE", "MODIFY", "CANCEL", "SELECT_OTHER", "REQUEST_MORE_RESEARCH"},
        "evidence_waiver": {"PARTIAL_ACCEPTED", "REQUEST_MORE_RESEARCH", "CANCEL"},
    }.get(gate_type)
    diagnostics: list[Diagnostic] = []
    if expected_actions is not None and set(document.get("allowed_actions", [])) != expected_actions:
        diagnostics.append(Diagnostic(source, "$.allowed_actions", "gate_actions", f"Gate {gate_type} must expose its complete v0.1 action set"))
    option_ids = {option.get("id") for option in document.get("options", [])}
    recommendation = document.get("recommendation", {}).get("option")
    if recommendation is not None and recommendation not in option_ids:
        diagnostics.append(Diagnostic(source, "$.recommendation.option", "gate_recommendation", "Recommendation must reference an existing option"))
    return diagnostics


def interaction_semantics(document: dict[str, Any], source: str) -> list[Diagnostic]:
    """Validate cross-field Interaction invariants that JSON Schema cannot express."""
    diagnostics: list[Diagnostic] = []
    result = document.get("executor_result")
    if isinstance(result, dict) and result.get("status") == "WAITING_FOR_USER":
        request = result.get("interaction_request", {})
        checkpoint = result.get("interaction_checkpoint", {})
        if isinstance(request, dict) and isinstance(checkpoint, dict):
            if request.get("method") != checkpoint.get("current_method"):
                diagnostics.append(Diagnostic(
                    source,
                    "$.executor_result.interaction_checkpoint.current_method",
                    "interaction_method_mismatch",
                    "Interaction Request method must match Checkpoint current_method",
                ))
            options = request.get("options", [])
            option_ids = {option.get("id") for option in options if isinstance(option, dict)} if isinstance(options, list) else set()
            recommendation = request.get("recommendation")
            if isinstance(recommendation, dict) and recommendation.get("option_id") not in option_ids:
                diagnostics.append(Diagnostic(
                    source,
                    "$.executor_result.interaction_request.recommendation.option_id",
                    "interaction_recommendation",
                    "Recommendation must reference an Interaction option",
                ))

    request = document.get("executor_request")
    if isinstance(request, dict) and isinstance(request.get("interaction_resume"), dict):
        checkpoint_ref = request["interaction_resume"].get("checkpoint_ref", "")
        attempt_id = request.get("attempt_id")
        expected_fragment = f"runtime/attempts/{attempt_id}/checkpoints/" if isinstance(attempt_id, str) else ""
        if not expected_fragment or not isinstance(checkpoint_ref, str) or not checkpoint_ref.startswith(expected_fragment):
            diagnostics.append(Diagnostic(
                source,
                "$.executor_request.interaction_resume.checkpoint_ref",
                "interaction_attempt_mismatch",
                "Interaction Resume checkpoint must belong to the same Attempt",
            ))

    current = document.get("current_interaction")
    nodes = document.get("nodes")
    if isinstance(current, dict) and isinstance(nodes, dict):
        node_id = current.get("node_id")
        node = nodes.get(node_id)
        if not isinstance(node, dict):
            diagnostics.append(Diagnostic(source, "$.current_interaction.node_id", "interaction_node", "Current Interaction node must exist in State"))
        else:
            if node.get("active_attempt_id") != current.get("attempt_id"):
                diagnostics.append(Diagnostic(source, "$.current_interaction.attempt_id", "interaction_attempt_mismatch", "State and Node must reference the same active Attempt"))
            if node.get("interaction_checkpoint_ref") != current.get("checkpoint_ref"):
                diagnostics.append(Diagnostic(source, "$.current_interaction.checkpoint_ref", "interaction_checkpoint_mismatch", "State and Node must reference the same Interaction Checkpoint"))
    return diagnostics


def research_origin_diagnostics(
    idea_definition: dict[str, Any],
    research_contract: dict[str, Any],
    source: str = "fixtures",
) -> list[Diagnostic]:
    """Validate Idea Assumption/Unknown/Seed to Research Question traceability."""
    diagnostics: list[Diagnostic] = []
    assumptions = idea_definition.get("assumptions", [])
    unknowns = idea_definition.get("unknowns", [])
    seeds = idea_definition.get("research_seeds", {})

    assumption_ids = {
        item.get("id")
        for item in assumptions
        if isinstance(item, dict) and isinstance(item.get("id"), str)
    }
    critical_assumptions = {
        item.get("id")
        for item in assumptions
        if isinstance(item, dict) and item.get("criticality") == "high" and isinstance(item.get("id"), str)
    }
    unknown_ids = {
        item.get("id")
        for item in unknowns
        if isinstance(item, dict) and isinstance(item.get("id"), str)
    }
    researchable_unknowns = {
        item.get("id")
        for item in unknowns
        if isinstance(item, dict) and item.get("researchable") is True and isinstance(item.get("id"), str)
    }
    seed_refs: set[str] = set()
    if isinstance(seeds, dict):
        for field in ("competitor_questions", "user_questions", "market_questions", "technology_questions"):
            values = seeds.get(field, [])
            if isinstance(values, list):
                seed_refs.update(f"research_seeds.{field}[{index}]" for index in range(len(values)))
    available_origins = assumption_ids | unknown_ids | seed_refs

    questions = research_contract.get("research_questions", {})
    used_origins: set[str] = set()
    question_ids: dict[str, str] = {}
    question_count = 0
    if isinstance(questions, dict):
        for branch, items in questions.items():
            if not isinstance(items, list):
                continue
            for index, question in enumerate(items):
                if not isinstance(question, dict):
                    continue
                question_count += 1
                question_id = question.get("id")
                if isinstance(question_id, str):
                    previous = question_ids.get(question_id)
                    if previous is not None:
                        diagnostics.append(Diagnostic(source, f"$.research_questions.{branch}[{index}].id", "duplicate_research_question", f"Research Question ID {question_id} is already used at {previous}"))
                    else:
                        question_ids[question_id] = f"{branch}[{index}]"
                for origin in question.get("origin_refs", []):
                    if not isinstance(origin, str) or origin not in available_origins:
                        diagnostics.append(Diagnostic(source, f"$.research_questions.{branch}[{index}].origin_refs", "unresolved_origin_ref", f"Unknown Idea origin: {origin}"))
                    else:
                        used_origins.add(origin)

    exceptions = research_contract.get("origin_exceptions", [])
    exception_origins: set[str] = set()
    if isinstance(exceptions, list):
        for index, item in enumerate(exceptions):
            if not isinstance(item, dict):
                continue
            origin = item.get("origin_ref")
            if origin not in available_origins:
                diagnostics.append(Diagnostic(source, f"$.origin_exceptions[{index}].origin_ref", "unresolved_origin_ref", f"Unknown Idea origin exception: {origin}"))
            elif isinstance(origin, str):
                exception_origins.add(origin)

    required_origins = critical_assumptions | researchable_unknowns
    missing_required = sorted(required_origins - used_origins - exception_origins)
    if missing_required:
        diagnostics.append(Diagnostic(source, "$.research_questions", "missing_origin_mapping", "Critical or researchable Idea origins are unmapped: " + ", ".join(missing_required)))

    completion = idea_definition.get("shaping", {}).get("completion_outcome")
    if completion == "PARTIAL_RESEARCHABLE" and question_count == 0:
        diagnostics.append(Diagnostic(source, "$.research_questions", "partial_researchable_without_question", "PARTIAL_RESEARCHABLE requires at least one derived Research Question"))
    return diagnostics


def reference_integrity(
    document: dict[str, Any],
    source: str,
    source_ids: set[str],
    claim_ids: set[str],
    evidence_ids: set[str],
    decision_ids: set[str],
) -> list[Diagnostic]:
    diagnostics: list[Diagnostic] = []
    if "evidence" in document:
        evidence = document["evidence"]
        if evidence.get("source_id") not in source_ids:
            diagnostics.append(Diagnostic(source, "$.evidence.source_id", "unresolved_source", "Evidence source_id is not present in the validated fixture set"))
        if evidence.get("claim_id") not in claim_ids:
            diagnostics.append(Diagnostic(source, "$.evidence.claim_id", "unresolved_claim", "Evidence claim_id is not present in the validated fixture set"))
    if "claim" in document:
        for field in ("evidence_ids", "contradiction_ids"):
            for evidence_id in document["claim"].get(field, []):
                if evidence_id not in evidence_ids:
                    diagnostics.append(Diagnostic(source, f"$.claim.{field}", "unresolved_evidence", f"Unknown evidence ID: {evidence_id}"))
    if "decision" in document:
        for evidence_id in document["decision"].get("evidence_ids", []):
            if evidence_id not in evidence_ids:
                diagnostics.append(Diagnostic(source, "$.decision.evidence_ids", "unresolved_evidence", f"Unknown evidence ID: {evidence_id}"))
    if "proof_result" in document:
        for evidence_id in document["proof_result"].get("evidence_ids", []):
            if evidence_id not in evidence_ids:
                diagnostics.append(Diagnostic(source, "$.proof_result.evidence_ids", "unresolved_evidence", f"Unknown evidence ID: {evidence_id}"))
    if "readiness" in document:
        for decision_id in document["readiness"].get("accepted_risk_decision_ids", []):
            if decision_id not in decision_ids:
                diagnostics.append(Diagnostic(source, "$.readiness.accepted_risk_decision_ids", "unresolved_decision", f"Unknown decision ID: {decision_id}"))
    return diagnostics


def citation_closure_diagnostics(
    projection: dict[str, Any],
    source: str,
    source_records: Mapping[str, dict[str, Any]],
) -> list[Diagnostic]:
    """Validate the minimum local Citation Closure required by a Projection."""
    diagnostics: list[Diagnostic] = []
    closure = projection.get("citation_closure")
    fact_groups = projection.get("fact_groups")
    if not isinstance(closure, dict) or not isinstance(fact_groups, list):
        return diagnostics

    fact_claim_ids: set[str] = set()
    fact_evidence_ids: set[str] = set()
    fact_source_ids: set[str] = set()
    for group_index, group in enumerate(fact_groups):
        if not isinstance(group, dict):
            continue
        citation_ids = group.get("citation_source_ids", [])
        if isinstance(citation_ids, list):
            fact_source_ids.update(item for item in citation_ids if isinstance(item, str))
        facts = group.get("facts", [])
        if not isinstance(facts, list):
            continue
        for fact_index, fact in enumerate(facts):
            if not isinstance(fact, dict):
                continue
            for field, destination in (
                ("claim_refs", fact_claim_ids),
                ("evidence_refs", fact_evidence_ids),
                ("source_refs", fact_source_ids),
            ):
                values = fact.get(field, [])
                if isinstance(values, list):
                    destination.update(item for item in values if isinstance(item, str))
            if not isinstance(fact.get("origin_field_pointer"), str) or not fact["origin_field_pointer"].startswith("/"):
                diagnostics.append(Diagnostic(source, f"$.fact_groups[{group_index}].facts[{fact_index}].origin_field_pointer", "citation_closure", "Fact bindings must retain an origin JSON Pointer"))

    closure_sets = {
        "claim_ids": {item for item in closure.get("claim_ids", []) if isinstance(item, str)},
        "evidence_ids": {item for item in closure.get("evidence_ids", []) if isinstance(item, str)},
        "source_ids": {item for item in closure.get("source_ids", []) if isinstance(item, str)},
    }
    fact_sets = {
        "claim_ids": fact_claim_ids,
        "evidence_ids": fact_evidence_ids,
        "source_ids": fact_source_ids,
    }
    for field, expected in fact_sets.items():
        if closure_sets[field] != expected:
            diagnostics.append(Diagnostic(source, f"$.citation_closure.{field}", "citation_closure", "Citation Closure must contain exactly the referenced Fact bindings"))

    for source_id in closure_sets["source_ids"]:
        source_record = source_records.get(source_id)
        if source_record is None:
            diagnostics.append(Diagnostic(source, "$.citation_closure.source_ids", "unresolved_source", f"Citation Source is not present in the validated fixture set: {source_id}"))
            continue
        canonical_url = source_record.get("canonical_url")
        parsed_url = urlparse(canonical_url) if isinstance(canonical_url, str) else None
        if not isinstance(canonical_url, str) or parsed_url is None or parsed_url.scheme not in {"http", "https"} or not parsed_url.netloc:
            diagnostics.append(Diagnostic(source, "$.citation_closure.source_ids", "citation_metadata", f"Citation Source {source_id} must have a canonical HTTP(S) URL"))
        for field in ("publisher", "title", "excerpt_or_summary"):
            if not isinstance(source_record.get(field), str) or not source_record[field].strip():
                diagnostics.append(Diagnostic(source, "$.citation_closure.source_ids", "citation_metadata", f"Citation Source {source_id} must provide {field}"))
        metadata = source_record.get("citation_metadata")
        if not isinstance(metadata, dict):
            diagnostics.append(Diagnostic(source, "$.citation_closure.source_ids", "citation_metadata", f"Citation Source {source_id} must provide citation_metadata"))
            continue
        for field in ("publisher_short_name", "excerpt"):
            if not isinstance(metadata.get(field), str) or not metadata[field].strip():
                diagnostics.append(Diagnostic(source, "$.citation_closure.source_ids", "citation_metadata", f"Citation Source {source_id} metadata must provide {field}"))
        favicon_ref = metadata.get("local_favicon_ref")
        if favicon_ref is not None and (not isinstance(favicon_ref, str) or not _is_safe_relative_path(favicon_ref)):
            diagnostics.append(Diagnostic(source, "$.citation_closure.source_ids", "citation_metadata", f"Citation Source {source_id} favicon must be a safe local reference or null"))
    return diagnostics


def chart_template_diagnostics(
    chart_spec: dict[str, Any],
    source: str,
    catalog: RepositoryCatalog | None,
) -> list[Diagnostic]:
    """Validate one Chart Spec against the v0.3.1 closed Template Registry."""
    if catalog is None:
        return []
    chart_id = chart_spec.get("chart_id")
    expected = V031_CHART_TEMPLATES.get(chart_id)
    if expected is None:
        return [Diagnostic(source, "$.chart_id", "chart_template_mismatch", "Chart Spec must select a registered v0.3.1 chart template")]
    actual = (chart_spec.get("renderer_kind"), chart_spec.get("data_contract"))
    if actual != expected:
        return [Diagnostic(source, "$", "chart_template_mismatch", "Chart Spec renderer_kind and data_contract must match the selected Template Registry entry")]
    return []


def chart_data_diagnostics(
    chart_data: dict[str, Any],
    chart_spec: dict[str, Any],
    source: str,
) -> list[Diagnostic]:
    """Require Chart Data to use exactly the data contract selected by its Spec."""
    if chart_data.get("data_contract") != chart_spec.get("data_contract"):
        return [Diagnostic(source, "$.data_contract", "chart_template_mismatch", "Chart Data contract must match the selected Chart Spec")]
    return []


def svg_static_diagnostics(document: dict[str, Any], source: str) -> list[Diagnostic]:
    """Enforce the native SVG-first static safety and accessibility minimum."""
    svg = document.get("svg")
    if not isinstance(svg, str):
        return [Diagnostic(source, "$.svg", "unsafe_svg", "SVG fixture must contain a string SVG document")]
    try:
        root = ET.fromstring(svg)
    except ET.ParseError as exc:
        return [Diagnostic(source, "$.svg", "unsafe_svg", f"SVG fixture is malformed: {exc}")]
    local_name = lambda value: value.rsplit("}", 1)[-1]
    diagnostics: list[Diagnostic] = []
    if local_name(root.tag) != "svg" or root.get("viewBox") is None or root.get("role") != "img":
        diagnostics.append(Diagnostic(source, "$.svg", "unsafe_svg", "Canonical SVG must declare svg, viewBox, and role=img"))
    child_names = {local_name(child.tag) for child in root}
    if not {"title", "desc"} <= child_names:
        diagnostics.append(Diagnostic(source, "$.svg", "unsafe_svg", "Canonical SVG must include title and desc"))
    for element in root.iter():
        tag = local_name(element.tag)
        if tag in {"script", "foreignObject"}:
            diagnostics.append(Diagnostic(source, "$.svg", "unsafe_svg", f"Canonical SVG must not contain {tag}"))
        for name, value in element.attrib.items():
            attribute = local_name(name)
            if attribute.lower().startswith("on"):
                diagnostics.append(Diagnostic(source, "$.svg", "unsafe_svg", "Canonical SVG must not contain event handlers"))
            if attribute in {"href", "src"} and isinstance(value, str):
                parsed = urlparse(value)
                if parsed.scheme or parsed.netloc or value.startswith("//"):
                    diagnostics.append(Diagnostic(source, "$.svg", "unsafe_svg", "Canonical SVG must not reference remote assets"))
    return diagnostics


def _artifact_document_ref(document: Mapping[str, Any]) -> str | None:
    artifact = document.get("artifact")
    if not isinstance(artifact, Mapping):
        return None
    identifier, version = artifact.get("id"), artifact.get("version")
    if not isinstance(identifier, str) or not isinstance(version, int) or isinstance(version, bool) or version < 1:
        return None
    return f"{identifier}@{version}"


def report_successor_diagnostics(
    successor: Mapping[str, Any],
    source: str,
    base_report: Mapping[str, Any] | None = None,
) -> list[Diagnostic]:
    """Validate append-only Report lineage and section-only successor ownership."""

    diagnostics: list[Diagnostic] = []
    kind = successor.get("publication_kind")
    artifact = successor.get("artifact") if isinstance(successor.get("artifact"), Mapping) else {}
    successor_ref = _artifact_document_ref(successor)
    expected_root = f"artifacts/02-research/competitors/report-bundles/{successor_ref}/" if successor_ref else None
    if expected_root is None:
        diagnostics.append(Diagnostic(source, "$.artifact", "report_bundle_identity", "Report Bundle requires a versioned Artifact identity"))
    else:
        expected_files = {"report_root_ref": "competitor-report.html", "inventory_ref": "inventory.json"}
        for field, filename in expected_files.items():
            if successor.get(field) != expected_root + filename:
                diagnostics.append(Diagnostic(source, f"$.{field}", "report_bundle_identity", f"{field} must identify {filename} inside the versioned Report Bundle {expected_root}"))
    if kind == "INITIAL":
        if successor.get("base_report_ref") is not None or artifact.get("supersedes") is not None:
            diagnostics.append(Diagnostic(source, "$.base_report_ref", "report_successor_base", "Initial Report must not reference or supersede a base Report"))
        return diagnostics
    if kind not in {"SCORE_SUCCESSOR", "VERIFICATION_SUCCESSOR"}:
        return diagnostics
    if not isinstance(base_report, Mapping):
        return [Diagnostic(source, "$.base_report_ref", "report_successor_base", "Report successor semantics require its explicit base Report fixture")]
    base_ref = _artifact_document_ref(base_report)
    for field in ("report_root_ref", "inventory_ref"):
        if successor.get(field) == base_report.get(field):
            diagnostics.append(Diagnostic(source, f"$.{field}", "report_bundle_reuse", "Report successor must publish a new immutable Bundle, not reuse the base Bundle ref"))
    if base_ref is None or successor.get("base_report_ref") != base_ref or artifact.get("supersedes") != base_ref:
        diagnostics.append(Diagnostic(source, "$.base_report_ref", "report_successor_base", "Report successor base_report_ref and artifact.supersedes must identify the direct base Report"))
    base_artifact = base_report.get("artifact") if isinstance(base_report.get("artifact"), Mapping) else {}
    if artifact.get("id") != base_artifact.get("id") or artifact.get("version") != base_artifact.get("version", 0) + 1:
        diagnostics.append(Diagnostic(source, "$.artifact", "report_successor_version", "Report successor must increment the same Artifact identity by exactly one version"))
    preserved = (
        ["verification", "report_publication_projection_ref", "chart_bundle_collection_ref"]
        if kind == "SCORE_SUCCESSOR"
        else ["scoring", "report_publication_projection_ref", "chart_bundle_collection_ref"]
    )
    changed = [field for field in preserved if successor.get(field) != base_report.get(field)]
    if changed:
        diagnostics.append(Diagnostic(source, "$", "report_section_ownership", f"{kind} changed fields outside its owned section: {', '.join(changed)}"))
    return diagnostics


def _decimal_value(value: Any) -> Decimal | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None


def transparent_score_aggregation_diagnostics(
    score: Mapping[str, Any],
    judgment_documents: Iterable[Mapping[str, Any]],
    verification_documents: Iterable[Mapping[str, Any]],
    scoring_rubric: Mapping[str, Any],
    source: str,
) -> tuple[list[Diagnostic], str | None]:
    """Recompute one staged Transparent Score only from Rubric-approved accepted Judgments."""

    diagnostics: list[Diagnostic] = []
    rubric_header = scoring_rubric.get("rubric") if isinstance(scoring_rubric.get("rubric"), Mapping) else {}
    dimension_rows = scoring_rubric.get("dimensions") if isinstance(scoring_rubric.get("dimensions"), list) else []
    dimensions = {
        row.get("id"): row
        for row in dimension_rows
        if isinstance(row, Mapping) and isinstance(row.get("id"), str)
    }
    dimension_order = [row.get("id") for row in dimension_rows if isinstance(row, Mapping) and isinstance(row.get("id"), str)]
    expected_configured = {dimension_id: _decimal_value(row.get("weight")) for dimension_id, row in dimensions.items()}
    if not dimensions or any(weight is None for weight in expected_configured.values()):
        return [Diagnostic(source, "$.rubric", "score_aggregate_rubric", "Scoring Rubric dimensions and weights must be complete")], None
    if score.get("profile_ref") != rubric_header.get("profile_ref") or score.get("rubric_version") != rubric_header.get("version"):
        diagnostics.append(Diagnostic(source, "$", "score_aggregate_identity", "Transparent Score Profile and Rubric version must match the selected Rubric"))

    judgments_by_ref = {reference: document for document in judgment_documents if (reference := _artifact_document_ref(document)) is not None}
    verifications_by_ref = {reference: document for document in verification_documents if (reference := _artifact_document_ref(document)) is not None}
    judgment_refs = score.get("dimension_judgment_refs")
    verification_refs = score.get("score_verification_refs")
    if not isinstance(judgment_refs, list) or not isinstance(verification_refs, list) or not judgment_refs or len(judgment_refs) != len(verification_refs):
        return [Diagnostic(source, "$", "score_aggregate_binding", "Transparent Score requires one Verification ref per Judgment ref")], None

    accepted_by_judgment: dict[str, Mapping[str, Any]] = {}
    for verification_ref in verification_refs:
        verification = verifications_by_ref.get(verification_ref)
        header = verification.get("artifact", {}) if isinstance(verification, Mapping) else {}
        if not isinstance(header, Mapping) or header.get("type") != "score_verification" or header.get("status") != "active" or header.get("produced_by", {}).get("skill") != "competitor-score-verifier":
            diagnostics.append(Diagnostic(source, "$.score_verification_refs", "score_aggregate_verification_ref", f"Verification ref is missing, inactive, or not independently produced: {verification_ref}"))
            continue
        if verification.get("result") != "ACCEPT" or verification.get("next_action") != "AGGREGATE" or verification.get("retry_exhausted") is not False or verification.get("issues") != []:
            diagnostics.append(Diagnostic(source, "$.score_verification_refs", "score_aggregate_verification_accept", f"Verification must be ACCEPT/AGGREGATE without issues: {verification_ref}"))
            continue
        judgment_ref = verification.get("judgment_ref")
        if judgment_ref not in judgment_refs or judgment_ref in accepted_by_judgment:
            diagnostics.append(Diagnostic(source, "$.score_verification_refs", "score_aggregate_binding", f"Verification must bind one unique Judgment in this Score: {verification_ref}"))
            continue
        accepted_by_judgment[judgment_ref] = verification

    scored_dimensions: dict[str, tuple[Decimal, Decimal]] = {}
    for judgment_ref in judgment_refs:
        judgment = judgments_by_ref.get(judgment_ref)
        header = judgment.get("artifact", {}) if isinstance(judgment, Mapping) else {}
        if not isinstance(header, Mapping) or header.get("type") != "dimension_judgment" or header.get("status") != "active" or header.get("produced_by", {}).get("skill") != "competitor-scoring":
            diagnostics.append(Diagnostic(source, "$.dimension_judgment_refs", "score_aggregate_judgment_ref", f"Judgment ref is missing, inactive, or of the wrong producer: {judgment_ref}"))
            continue
        dimension_id = judgment.get("dimension_id")
        dimension = dimensions.get(dimension_id)
        if dimension is None:
            diagnostics.append(Diagnostic(source, "$.dimension_judgment_refs", "score_aggregate_dimension", f"Judgment dimension is not in the selected Rubric: {dimension_id}"))
            continue
        if dimension_id in scored_dimensions:
            diagnostics.append(Diagnostic(source, "$.dimension_judgment_refs", "score_aggregate_duplicate_dimension", f"Transparent Score contains duplicate scored dimension: {dimension_id}"))
            continue
        if judgment.get("competitor_id") != score.get("competitor_id") or judgment.get("rubric_ref") != score.get("rubric_ref") or judgment.get("rubric_version") != score.get("rubric_version"):
            diagnostics.append(Diagnostic(source, "$.dimension_judgment_refs", "score_aggregate_identity", f"Judgment does not bind this competitor and Rubric: {judgment_ref}"))
            continue
        if judgment.get("judgment_status") != "SCORED" or not isinstance(judgment.get("score"), int) or isinstance(judgment.get("score"), bool):
            diagnostics.append(Diagnostic(source, "$.dimension_judgment_refs", "score_aggregate_dimension", f"Only integer SCORED Judgments contribute covered weight: {judgment_ref}"))
            continue
        minimum_evidence = dimension.get("minimum_evidence_count")
        if not isinstance(judgment.get("claim_refs"), list) or not isinstance(judgment.get("evidence_refs"), list) or len(judgment["evidence_refs"]) < minimum_evidence:
            diagnostics.append(Diagnostic(source, "$.dimension_judgment_refs", "score_aggregate_evidence", f"Judgment lacks Rubric-required evidence: {judgment_ref}"))
            continue
        if judgment_ref not in accepted_by_judgment:
            diagnostics.append(Diagnostic(source, "$.dimension_judgment_refs", "score_aggregate_binding", f"Judgment lacks one accepted independent Verification: {judgment_ref}"))
            continue
        weight = expected_configured[dimension_id]
        scored_dimensions[dimension_id] = (Decimal(judgment["score"]), weight)

    covered_weight = sum((weight for _, weight in scored_dimensions.values()), Decimal(0))
    missing_dimensions = [dimension_id for dimension_id in dimension_order if dimension_id not in scored_dimensions]
    minimum_coverage = _decimal_value(rubric_header.get("minimum_weight_coverage"))
    eligible = minimum_coverage is not None and covered_weight >= minimum_coverage
    expected_status = "COMPLETE" if covered_weight == Decimal(1) else ("PARTIAL" if eligible else "NOT_PERFORMED")
    expected_effective = {
        dimension_id: weight / covered_weight
        for dimension_id, (_, weight) in scored_dimensions.items()
    } if covered_weight else {}
    expected_final = (
        sum((value * weight for value, weight in scored_dimensions.values()), Decimal(0)) / covered_weight
        if eligible and covered_weight
        else None
    )

    configured = score.get("configured_weights") if isinstance(score.get("configured_weights"), Mapping) else {}
    configured_decimal = {key: _decimal_value(value) for key, value in configured.items()}
    if configured_decimal != expected_configured:
        diagnostics.append(Diagnostic(source, "$.configured_weights", "score_aggregate_configured_weights", "Configured weights must exactly match the selected Rubric"))
    if _decimal_value(score.get("coverage")) != covered_weight:
        diagnostics.append(Diagnostic(source, "$.coverage", "score_aggregate_coverage", f"Coverage must equal recomputed covered weight {covered_weight}"))
    if score.get("missing_dimension_ids") != missing_dimensions:
        diagnostics.append(Diagnostic(source, "$.missing_dimension_ids", "score_aggregate_missing_dimensions", f"Missing dimensions must equal {missing_dimensions}"))
    effective = score.get("effective_weights") if isinstance(score.get("effective_weights"), Mapping) else {}
    effective_decimal = {key: _decimal_value(value) for key, value in effective.items()}
    if effective_decimal != expected_effective:
        diagnostics.append(Diagnostic(source, "$.effective_weights", "score_aggregate_effective_weights", "Effective weights must be the normalized weights of accepted covered dimensions"))
    if score.get("status") != expected_status:
        diagnostics.append(Diagnostic(source, "$.status", "score_aggregate_status", f"Score status must be {expected_status}"))
    if _decimal_value(score.get("final_score")) != expected_final:
        diagnostics.append(Diagnostic(source, "$.final_score", "score_aggregate_final_score", f"Final score must equal deterministic aggregate {expected_final}"))
    if not eligible and (score.get("final_score") is not None or score.get("rank") is not None or score.get("tie_status") != "NOT_RANKED"):
        diagnostics.append(Diagnostic(source, "$", "score_aggregate_threshold", "Coverage below the Rubric threshold cannot have a final score or rank"))
    return diagnostics, expected_status


def transparent_score_collection_diagnostics(
    collection: Mapping[str, Any],
    score_documents: Iterable[Mapping[str, Any]],
    candidate_ranking: Mapping[str, Any],
    source: str,
    judgment_documents: Iterable[Mapping[str, Any]] = (),
    verification_documents: Iterable[Mapping[str, Any]] = (),
    scoring_rubric: Mapping[str, Any] | None = None,
) -> list[Diagnostic]:
    """Validate the deterministic Runtime-owned Current Score collection envelope."""

    diagnostics: list[Diagnostic] = []
    entries = collection.get("score_refs")
    if not isinstance(entries, list):
        return diagnostics
    competitor_ids = [entry.get("competitor_id") for entry in entries if isinstance(entry, Mapping)]
    artifact_refs = [entry.get("artifact_ref") for entry in entries if isinstance(entry, Mapping)]
    if len(competitor_ids) != len(set(competitor_ids)):
        diagnostics.append(Diagnostic(source, "$.score_refs", "score_collection_duplicate_competitor", "Score collection competitor IDs must be unique"))
    if len(artifact_refs) != len(set(artifact_refs)):
        diagnostics.append(Diagnostic(source, "$.score_refs", "score_collection_duplicate_ref", "Score collection Artifact refs must be unique"))

    by_ref: dict[str, Mapping[str, Any]] = {}
    for score in score_documents:
        reference = _artifact_document_ref(score)
        if reference is not None:
            by_ref[reference] = score
    judgments_by_ref = {
        reference: document
        for document in judgment_documents
        if (reference := _artifact_document_ref(document)) is not None
    }
    verifications_by_ref = {
        reference: document
        for document in verification_documents
        if (reference := _artifact_document_ref(document)) is not None
    }
    verification_owners: dict[str, str] = {}
    resolved: list[Mapping[str, Any]] = []
    for index, entry in enumerate(entries):
        if not isinstance(entry, Mapping):
            continue
        reference = entry.get("artifact_ref")
        score = by_ref.get(reference) if isinstance(reference, str) else None
        if score is None:
            diagnostics.append(Diagnostic(source, f"$.score_refs[{index}].artifact_ref", "score_collection_unknown_ref", f"Unknown immutable Transparent Score ref: {reference}"))
            continue
        resolved.append(score)
        if score.get("artifact", {}).get("type") != "transparent_score" or score.get("artifact", {}).get("status") != "active" or entry.get("competitor_id") != score.get("competitor_id"):
            diagnostics.append(Diagnostic(source, f"$.score_refs[{index}]", "score_collection_identity", "Score entry must bind its competitor to one active immutable transparent_score"))
        for field in ("candidate_ranking_ref", "profile_ref", "rubric_ref", "rubric_version"):
            if collection.get(field) != score.get(field):
                diagnostics.append(Diagnostic(source, f"$.score_refs[{index}]", "score_collection_identity", f"Score collection and member disagree on {field}"))
        if isinstance(scoring_rubric, Mapping):
            aggregate_diagnostics, aggregate_status = transparent_score_aggregation_diagnostics(score, judgments_by_ref.values(), verifications_by_ref.values(), scoring_rubric, source)
            diagnostics.extend(aggregate_diagnostics)
            if aggregate_status == "NOT_PERFORMED":
                diagnostics.append(Diagnostic(source, f"$.score_refs[{index}]", "score_collection_ineligible_score", "Collection cannot include a Score below the Rubric coverage threshold"))
        judgment_refs = score.get("dimension_judgment_refs")
        verification_refs = score.get("score_verification_refs")
        if not isinstance(judgment_refs, list) or not isinstance(verification_refs, list) or not judgment_refs or len(judgment_refs) != len(verification_refs):
            diagnostics.append(Diagnostic(source, f"$.score_refs[{index}]", "score_collection_verification_binding", "Each Score must have a one-to-one non-empty Judgment and Verification ref set"))
            continue
        judgment_set = set(judgment_refs)
        bound_judgments: set[str] = set()
        for judgment_ref in judgment_refs:
            judgment = judgments_by_ref.get(judgment_ref)
            header = judgment.get("artifact", {}) if isinstance(judgment, Mapping) else {}
            if not isinstance(header, Mapping) or header.get("type") != "dimension_judgment" or header.get("status") != "active" or header.get("produced_by", {}).get("skill") != "competitor-scoring":
                diagnostics.append(Diagnostic(source, f"$.score_refs[{index}]", "score_collection_judgment_ref", f"Judgment ref is missing, inactive, or of the wrong type/producer: {judgment_ref}"))
                continue
            if judgment.get("competitor_id") != score.get("competitor_id") or judgment.get("rubric_ref") != score.get("rubric_ref") or judgment.get("rubric_version") != score.get("rubric_version"):
                diagnostics.append(Diagnostic(source, f"$.score_refs[{index}]", "score_collection_verification_binding", f"Judgment does not bind this competitor and Rubric: {judgment_ref}"))
        for verification_ref in verification_refs:
            verification = verifications_by_ref.get(verification_ref)
            header = verification.get("artifact", {}) if isinstance(verification, Mapping) else {}
            if not isinstance(header, Mapping) or header.get("type") != "score_verification" or header.get("status") != "active" or header.get("produced_by", {}).get("skill") != "competitor-score-verifier":
                diagnostics.append(Diagnostic(source, f"$.score_refs[{index}]", "score_collection_verification_ref", f"Independent Score Verification ref is missing, inactive, or of the wrong type/producer: {verification_ref}"))
                continue
            if verification.get("result") != "ACCEPT" or verification.get("next_action") != "AGGREGATE" or verification.get("retry_exhausted") is not False or verification.get("issues") != []:
                diagnostics.append(Diagnostic(source, f"$.score_refs[{index}]", "score_collection_verification_accept", f"Verification must be ACCEPT/AGGREGATE without issues or retry exhaustion: {verification_ref}"))
            bound_ref = verification.get("judgment_ref")
            if bound_ref not in judgment_set or bound_ref in bound_judgments:
                diagnostics.append(Diagnostic(source, f"$.score_refs[{index}]", "score_collection_verification_binding", f"Verification does not bind one unique Judgment in this Score: {verification_ref}"))
            else:
                bound_judgments.add(bound_ref)
            prior_competitor = verification_owners.setdefault(verification_ref, str(score.get("competitor_id")))
            if prior_competitor != score.get("competitor_id"):
                diagnostics.append(Diagnostic(source, f"$.score_refs[{index}]", "score_collection_verification_binding", f"Verification ref is reused across competitors: {verification_ref}"))
        if bound_judgments != judgment_set:
            diagnostics.append(Diagnostic(source, f"$.score_refs[{index}]", "score_collection_verification_binding", "Accepted Verification refs must cover exactly the Score Judgment refs"))

    ranking_ref = _artifact_document_ref(candidate_ranking)
    if collection.get("candidate_ranking_ref") != ranking_ref:
        diagnostics.append(Diagnostic(source, "$.candidate_ranking_ref", "score_collection_identity", "Score collection must identify the supplied Candidate Ranking"))
    ranking_rows = candidate_ranking.get("ranking") if isinstance(candidate_ranking, Mapping) else None
    ranked_competitors = {
        row.get("competitor_id")
        for row in ranking_rows or []
        if isinstance(row, Mapping) and isinstance(row.get("competitor_id"), str)
    }
    if set(competitor_ids) != ranked_competitors:
        diagnostics.append(Diagnostic(source, "$.score_refs", "score_collection_coverage", "Score collection must cover the Candidate Ranking scope exactly once"))

    eligible_rows: list[tuple[Mapping[str, Any], Decimal, Decimal, str]] = []
    unranked: list[Mapping[str, Any]] = []
    for score in resolved:
        final_score = _decimal_value(score.get("final_score"))
        coverage = _decimal_value(score.get("coverage"))
        reference = _artifact_document_ref(score)
        if final_score is None:
            unranked.append(score)
        elif coverage is None or reference is None:
            diagnostics.append(Diagnostic(source, "$.score_refs", "score_collection_identity", "Ranked Transparent Score must have numeric coverage and an immutable Artifact ref"))
        else:
            eligible_rows.append((score, final_score, coverage, reference))
    eligible_rows.sort(key=lambda row: (-row[1], -row[2], str(row[0].get("competitor_id"))))
    eligible = [row[0] for row in eligible_rows]
    unranked.sort(key=lambda score: str(score.get("competitor_id")))
    expected_rank: dict[str, int] = {}
    for position, score in enumerate(eligible, start=1):
        reference = _artifact_document_ref(score)
        previous = eligible[position - 2] if position > 1 else None
        peer = (score.get("final_score"), score.get("coverage"))
        if previous is not None and (previous.get("final_score"), previous.get("coverage")) == peer:
            previous_ref = _artifact_document_ref(previous)
            if reference is not None and previous_ref is not None:
                expected_rank[reference] = expected_rank[previous_ref]
        elif reference is not None:
            expected_rank[reference] = position
        tied = sum(1 for item in eligible if (item.get("final_score"), item.get("coverage")) == peer) > 1
        if reference is not None and (score.get("rank") != expected_rank.get(reference) or score.get("tie_status") != ("TIED" if tied else "UNIQUE")):
            diagnostics.append(Diagnostic(source, "$.score_refs", "score_collection_rank_tie", "Transparent Score rank/tie values do not match deterministic competition ranking"))
    for score in unranked:
        if score.get("rank") is not None or score.get("tie_status") != "NOT_RANKED":
            diagnostics.append(Diagnostic(source, "$.score_refs", "score_collection_rank_tie", "Unranked Transparent Scores must use null rank and NOT_RANKED"))
    expected_order = [_artifact_document_ref(score) for score in [*eligible, *unranked]]
    if artifact_refs != expected_order:
        diagnostics.append(Diagnostic(source, "$.score_refs", "score_collection_order", "Score refs are not in the deterministic score/coverage/competitor order"))
    return diagnostics


def _collect_ids(cases: list[dict[str, Any]]) -> tuple[set[str], set[str], set[str], set[str], dict[str, dict[str, Any]]]:
    source_ids: set[str] = set()
    claim_ids: set[str] = set()
    evidence_ids: set[str] = set()
    decision_ids: set[str] = set()
    source_records: dict[str, dict[str, Any]] = {}
    for case in cases:
        if not case["spec"].get("expected_valid", False):
            continue
        document = case["document"]
        if "source" in document:
            source_id = document["source"].get("id")
            source_ids.add(source_id)
            if isinstance(source_id, str) and isinstance(document["source"], dict):
                source_records[source_id] = document["source"]
        if "claim" in document:
            claim_ids.add(document["claim"].get("id"))
        if "evidence" in document:
            evidence_ids.add(document["evidence"].get("id"))
        if "decision" in document:
            decision_ids.add(document["decision"].get("id"))
    return source_ids, claim_ids, evidence_ids, decision_ids, source_records


def resolve_repo_path(
    relative_path: str,
    *,
    root: Path = ROOT,
    allowed_root: str | None = None,
    must_exist: bool = False,
    reject_symlinks: bool = False,
) -> Path:
    if not isinstance(relative_path, str) or not _is_safe_relative_path(relative_path):
        raise ValueError(f"Unsafe repository-relative path: {relative_path!r}")
    candidate = root / relative_path
    resolved = candidate.resolve()
    try:
        resolved.relative_to(root.resolve())
    except ValueError as exc:
        raise ValueError(f"Path escapes repository root: {relative_path}") from exc
    if allowed_root is not None:
        allowed = (root / allowed_root).resolve()
        try:
            resolved.relative_to(allowed)
        except ValueError as exc:
            raise ValueError(f"Path must stay within {allowed_root}: {relative_path}") from exc
    if reject_symlinks and _contains_symlink(candidate, root):
        raise ValueError(f"Symbolic links are not allowed for contract references: {relative_path}")
    if must_exist and not resolved.is_file():
        raise ValueError(f"Referenced contract file does not exist: {relative_path}")
    return resolved


def _load_contract_document(path: Path, source: str) -> tuple[Any | None, list[Diagnostic]]:
    try:
        return load_document(path), []
    except DuplicateKeyError as exc:
        return None, [Diagnostic(source, "$", "duplicate_key", str(exc))]
    except (OSError, ValueError, TypeError, json.JSONDecodeError, yaml.YAMLError) as exc:
        return None, [Diagnostic(source, "$", "contract_load", str(exc))]


def skill_repository_diagnostics(
    catalog: RepositoryCatalog,
    schemas: dict[str, dict[str, Any]],
    registry: Registry,
    *,
    contract_version: str = CONTRACT_VERSION,
) -> tuple[list[Diagnostic], int, dict[str, dict[str, Any]], dict[str, set[str]]]:
    diagnostics: list[Diagnostic] = []
    checked = 0
    documents: dict[str, dict[str, Any]] = {}
    declared_ids: dict[str, str] = {}
    output_types: dict[str, set[str]] = {}
    for skill_id in sorted(required_skill_ids_for_version(contract_version) & catalog.skill_ids):
        directory = catalog.root / "skills" / skill_id
        yaml_path = directory / "skill.yaml"
        yaml_source = yaml_path.relative_to(catalog.root).as_posix()
        if yaml_path.is_file():
            document, load_errors = _load_contract_document(yaml_path, yaml_source)
            diagnostics.extend(load_errors)
            if document is not None:
                checked += 1
                if not isinstance(document, dict):
                    diagnostics.append(Diagnostic(yaml_source, "$", "contract_type", "Skill Contract must be an object"))
                else:
                    documents[skill_id] = document
                    schema_errors = validate_instance(document, "skill.schema.json", yaml_source, schemas, registry)
                    diagnostics.extend(schema_errors)
                    if not schema_errors:
                        diagnostics.extend(skill_contract_diagnostics(document, yaml_source, skill_id, catalog, schemas, contract_version=contract_version))
                    public_id = document.get("skill", {}).get("id")
                    if isinstance(public_id, str):
                        previous = declared_ids.get(public_id)
                        if previous is not None:
                            diagnostics.append(Diagnostic(yaml_source, "$.skill.id", "duplicate_contract_id", f"Skill ID {public_id} is already declared by {previous}"))
                        else:
                            declared_ids[public_id] = yaml_source
                    output_types[skill_id] = {
                        output.get("artifact_type")
                        for output in document.get("output_contracts", [])
                        if isinstance(output, dict) and isinstance(output.get("artifact_type"), str)
                    }

        markdown_path = directory / "SKILL.md"
        markdown_source = markdown_path.relative_to(catalog.root).as_posix()
        if markdown_path.is_file():
            try:
                if markdown_path.stat().st_size > MAX_DOCUMENT_BYTES:
                    raise ValueError(f"Document exceeds {MAX_DOCUMENT_BYTES} byte limit: {markdown_path}")
                markdown = markdown_path.read_text(encoding="utf-8")
            except (OSError, ValueError) as exc:
                diagnostics.append(Diagnostic(markdown_source, "$", "contract_load", str(exc)))
            else:
                checked += 1
                interaction_required = isinstance(documents.get(skill_id, {}).get("interaction"), dict)
                diagnostics.extend(skill_markdown_diagnostics(markdown, markdown_source, skill_id, interaction_required=interaction_required))

    diagnostics.extend(readiness_writer_diagnostics(documents))
    diagnostics.extend(publisher_contract_diagnostics(documents, contract_version=contract_version))
    return diagnostics, checked, documents, output_types


def publisher_contract_diagnostics(
    documents: Mapping[str, dict[str, Any]],
    *,
    contract_version: str = CONTRACT_VERSION,
) -> list[Diagnostic]:
    """Lock the staged v0.3.2 Report publisher roles without widening skill.schema.json."""

    if contract_version != "0.3.2":
        return []
    common = {
        "owner": "runtime",
        "compare_and_swap": "current_report_ref",
        "stale_base_action": "reject",
        "idempotent_replay": "same_base_kind_and_section_ref",
        "history": "append_only",
        "bundle_identity": "successor_artifact_ref",
        "bundle_root": "artifacts/02-research/competitors/report-bundles/",
        "root_filename": "competitor-report.html",
        "inventory_filename": "inventory.json",
        "new_bundle_required": True,
    }
    expectations: dict[str, dict[str, Any]] = {
        "competitor-report-builder": {
            "publication": {
                **common,
                "role": "initial_builder",
                "publication_kind": "INITIAL",
                "base_report_rule": "must_be_null",
                "mutation_scope": ["initial_presentation"],
                "preserve_fields": [],
            },
            "required_inputs": {"report_publication_projection", "chart_bundle_collection", "product_profile"},
            "writes": {"artifacts/02-research/competitors/report-publication.json"},
            "grants": {
                "artifacts/02-research/competitors/report-publication.json",
                "artifacts/02-research/competitors/report-bundles/",
            },
            "outputs": {"competitor_report"},
            "required_reads": {
                "artifacts/02-research/competitors/report-publication-projection.json",
                "artifacts/02-research/competitors/visualizations/",
                "templates/competitor-report.html",
            },
        },
        "competitor-score-publisher": {
            "publication": {
                **common,
                "role": "score_publisher",
                "publication_kind": "SCORE_SUCCESSOR",
                "base_report_rule": "current_required",
                "mutation_scope": ["scoring"],
                "preserve_fields": [
                    "verification",
                    "report_publication_projection_ref",
                    "chart_bundle_collection_ref",
                ],
            },
            "required_inputs": {"competitor_ranking", "product_profile", "scoring_rubric", "dimension_judgment", "transparent_score", "score_verification", "competitor_report"},
            "writes": {
                "artifacts/02-research/competitors/scoring/score-collection.json",
                "artifacts/02-research/competitors/report-publication.json",
            },
            "grants": {
                "artifacts/02-research/competitors/scoring/score-collection.json",
                "artifacts/02-research/competitors/report-publication.json",
                "artifacts/02-research/competitors/report-bundles/",
            },
            "outputs": {"transparent_score_collection", "competitor_report"},
            "required_reads": {
                "artifacts/02-research/competitors/ranking.yaml",
                "artifacts/02-research/competitors/report-publication.json",
                "artifacts/02-research/competitors/scoring/judgments/",
                "artifacts/02-research/competitors/scoring/scores/",
                "artifacts/02-research/competitors/scoring/verifications/",
                "profiles/",
                "rubrics/",
            },
        },
        "competitor-verifier": {
            "publication": {
                **common,
                "role": "verification_publisher",
                "publication_kind": "VERIFICATION_SUCCESSOR",
                "base_report_rule": "current_required",
                "mutation_scope": ["verification"],
                "preserve_fields": [
                    "scoring",
                    "report_publication_projection_ref",
                    "chart_bundle_collection_ref",
                ],
            },
            "required_inputs": {"competitor_report"},
            "writes": {
                "artifacts/02-research/competitors/competitor-verification.yaml",
                "artifacts/02-research/competitors/report-publication.json",
            },
            "grants": {
                "artifacts/02-research/competitors/competitor-verification.yaml",
                "artifacts/02-research/competitors/report-publication.json",
                "artifacts/02-research/competitors/report-bundles/",
            },
            "outputs": {"competitor_verification", "competitor_report"},
            "required_reads": {
                "artifacts/02-research/competitors/report-publication.json",
                "artifacts/02-research/competitors/scoring/score-collection.json",
            },
        },
    }
    diagnostics: list[Diagnostic] = []
    for skill_id, expected in expectations.items():
        document = documents.get(skill_id)
        source = f"skills/{skill_id}/skill.yaml"
        if not isinstance(document, dict):
            diagnostics.append(Diagnostic(source, "$", "publisher_contract", "Required v0.3.2 Report publisher Skill Contract is missing"))
            continue
        publication = document.get("completion", {}).get("report_publication")
        if publication != expected["publication"]:
            diagnostics.append(Diagnostic(source, "$.completion.report_publication", "publisher_contract", f"Report publication ownership must equal {expected['publication']}"))
        required_inputs = set(document.get("inputs", {}).get("required", []))
        if not expected["required_inputs"] <= required_inputs:
            diagnostics.append(Diagnostic(source, "$.inputs.required", "publisher_contract", "Report publisher is missing required typed inputs"))
        writes = set(document.get("writes", []))
        if writes != expected["writes"]:
            diagnostics.append(Diagnostic(source, "$.writes", "publisher_contract", f"Report publisher writes must equal {sorted(expected['writes'])}"))
        outputs = {
            item.get("artifact_type")
            for item in document.get("output_contracts", [])
            if isinstance(item, dict)
        }
        if outputs != expected["outputs"]:
            diagnostics.append(Diagnostic(source, "$.output_contracts", "publisher_contract", f"Report publisher outputs must equal {sorted(expected['outputs'])}"))
        reads = set(document.get("reads", []))
        if not expected["required_reads"] <= reads:
            diagnostics.append(Diagnostic(source, "$.reads", "publisher_contract", "Report publisher is missing required base or section input reads"))
        grants = set(document.get("permissions", {}).get("workspace_write", []))
        if grants != expected["grants"]:
            diagnostics.append(Diagnostic(source, "$.permissions.workspace_write", "publisher_contract", "Report publisher workspace grants must exactly match its declared publisher outputs and immutable assets"))
    builder = documents.get("competitor-report-builder", {})
    builder_inputs = set(builder.get("inputs", {}).get("optional", [])) | set(builder.get("inputs", {}).get("required", []))
    builder_outputs = {
        item.get("artifact_type")
        for item in builder.get("output_contracts", [])
        if isinstance(item, dict)
    }
    if "transparent_score" in builder_inputs or builder_outputs.intersection({"chart_bundle", "chart_bundle_collection", "chart_spec", "chart_data"}):
        diagnostics.append(Diagnostic("skills/competitor-report-builder/skill.yaml", "$", "report_builder_ownership", "Initial Report Builder must consume Chart outputs and cannot own scoring or Chart generation"))
    verifier_optional_path = documents.get("competitor-verifier", {}).get("completion", {}).get("optional_scoring_path")
    expected_optional_path = {
        "nodes": ["scoring", "score_verifier", "score_publisher"],
        "absent_terminal_status": "SKIPPED",
        "base_when_absent": "INITIAL",
        "base_when_present": "SCORE_SUCCESSOR",
        "outcomes": {
            "SCORING_DISABLED": {
                "node_statuses": {"scoring": "SKIPPED", "score_verifier": "SKIPPED", "score_publisher": "SKIPPED"},
                "collection": "absent", "score_successor": "absent", "current_report_kind": "INITIAL",
                "scoring_status": "NOT_PERFORMED", "verifier_base_kind": "INITIAL", "research_gap": "none", "verifier_action": "continue",
            },
            "SCORING_AVAILABLE": {
                "node_statuses": {"scoring": "VERIFIED", "score_verifier": "VERIFIED", "score_publisher": "VERIFIED"},
                "collection": "current", "score_successor": "current", "current_report_kind": "SCORE_SUCCESSOR",
                "scoring_status": "AVAILABLE", "verifier_base_kind": "SCORE_SUCCESSOR", "research_gap": "none", "verifier_action": "continue",
            },
            "SCORING_UNAVAILABLE_AFTER_RETRY": {
                "node_statuses": {"scoring": "VERIFIED", "score_verifier": "VERIFIED", "score_publisher": "SKIPPED"},
                "collection": "absent", "score_successor": "absent", "current_report_kind": "INITIAL",
                "scoring_status": "NOT_PERFORMED", "verifier_base_kind": "INITIAL", "research_gap": "targeted_opened", "verifier_action": "continue",
            },
        },
    }
    if verifier_optional_path != expected_optional_path:
        diagnostics.append(Diagnostic("skills/competitor-verifier/skill.yaml", "$.completion.optional_scoring_path", "publisher_contract", "Competitor Verifier must declare the complete optional scoring path and its absent/present base semantics"))
    expected_gate = {
        "only_when": "SCORING_AVAILABLE",
        "disabled_status": "SKIPPED",
        "unavailable_after_retry_status": "SKIPPED",
        "no_collection_no_successor": True,
    }
    if documents.get("competitor-score-publisher", {}).get("completion", {}).get("publication_gate") != expected_gate:
        diagnostics.append(Diagnostic("skills/competitor-score-publisher/skill.yaml", "$.completion.publication_gate", "publisher_contract", "Score Publisher must publish only when a legal collection is available"))
    expected_retry = {
        "targeted_research_gap_required": True,
        "legal_collection_allowed": False,
        "score_successor_allowed": False,
    }
    if documents.get("competitor-score-verifier", {}).get("completion", {}).get("retry_exhaustion_closure") != expected_retry:
        diagnostics.append(Diagnostic("skills/competitor-score-verifier/skill.yaml", "$.completion.retry_exhaustion_closure", "publisher_contract", "Retry exhaustion must open a targeted gap and forbid collection/successor publication"))
    return diagnostics


def readiness_writer_diagnostics(documents: Mapping[str, dict[str, Any]]) -> list[Diagnostic]:
    readiness_writers = sorted(
        skill_id
        for skill_id, document in documents.items()
        if any(
            isinstance(output, dict)
            and isinstance(output.get("schema_ref"), str)
            and output["schema_ref"].split("#", 1)[0] == READINESS_SCHEMA_REF
            for output in document.get("output_contracts", [])
        )
    )
    if readiness_writers != ["build-readiness-verifier"]:
        return [Diagnostic("skills", "$", "readiness_writer", f"build-readiness-verifier must be the unique Readiness writer; found {readiness_writers}")]
    return []


def template_repository_diagnostics(
    catalog: RepositoryCatalog,
    *,
    contract_version: str = CONTRACT_VERSION,
) -> tuple[list[Diagnostic], int]:
    diagnostics: list[Diagnostic] = []
    checked = 0
    for relative_path, artifact_type in template_contracts_for_version(contract_version).items():
        path = catalog.root / relative_path
        if not path.is_file():
            continue
        try:
            if path.stat().st_size > MAX_DOCUMENT_BYTES:
                raise ValueError(f"Document exceeds {MAX_DOCUMENT_BYTES} byte limit: {path}")
            text = path.read_text(encoding="utf-8")
        except (OSError, ValueError) as exc:
            diagnostics.append(Diagnostic(relative_path, "$", "contract_load", str(exc)))
            continue
        checked += 1
        diagnostics.extend(template_contract_diagnostics(text, relative_path, artifact_type, contract_version=contract_version))
    return diagnostics, checked


def subgraph_repository_diagnostics(
    catalog: RepositoryCatalog,
    schemas: dict[str, dict[str, Any]],
    registry: Registry,
    skill_output_types: Mapping[str, set[str]],
    *,
    contract_version: str = CONTRACT_VERSION,
) -> tuple[list[Diagnostic], int]:
    diagnostics: list[Diagnostic] = []
    checked = 0
    for subgraph_id in sorted(REQUIRED_SUBGRAPH_IDS & catalog.subgraph_ids):
        path = catalog.root / "subgraphs" / f"{subgraph_id}.yaml"
        source = path.relative_to(catalog.root).as_posix()
        document, load_errors = _load_contract_document(path, source)
        diagnostics.extend(load_errors)
        if document is None:
            continue
        checked += 1
        if not isinstance(document, dict):
            diagnostics.append(Diagnostic(source, "$", "contract_type", "Subgraph Contract must be an object"))
            continue
        schema_errors = validate_instance(document, "subgraph.schema.json", source, schemas, registry)
        diagnostics.extend(schema_errors)
        if not schema_errors:
            diagnostics.extend(subgraph_semantics(document, source, catalog, skill_output_types, contract_version=contract_version))
    return diagnostics, checked


def fixture_diagnostics(
    schemas: dict[str, dict[str, Any]],
    registry: Registry,
    workflow: dict[str, Any],
    *,
    bundle_root: Path = ROOT,
    fixture_manifest_path: Path = FIXTURE_MANIFEST,
    contract_version: str = CONTRACT_VERSION,
    catalog: RepositoryCatalog | None = None,
) -> tuple[list[Diagnostic], int]:
    manifest = load_document(fixture_manifest_path)
    loaded_cases: list[dict[str, Any]] = []
    diagnostics: list[Diagnostic] = []
    if not isinstance(manifest, dict) or not isinstance(manifest.get("cases"), list):
        return [Diagnostic(_display_path(fixture_manifest_path), "$", "fixture_manifest", "Fixture Manifest must contain a cases array")], 0
    manifest_version = manifest.get("contract_version")
    if manifest_version is not None and manifest_version != contract_version:
        diagnostics.append(Diagnostic(_display_path(fixture_manifest_path), "$.contract_version", "contract_version", f"Fixture Manifest version must be {contract_version}"))
    if contract_version != "0.1.0" and manifest.get("path_resolution") != "bundle_root_relative":
        diagnostics.append(Diagnostic(_display_path(fixture_manifest_path), "$.path_resolution", "fixture_manifest", "v0.2+ Fixture paths must be Bundle-root-relative"))

    legacy_cases = manifest.get("legacy_cases", [])
    if contract_version != "0.1.0" and not isinstance(legacy_cases, list):
        diagnostics.append(Diagnostic(_display_path(fixture_manifest_path), "$.legacy_cases", "fixture_manifest", "v0.2+ Fixture Manifest legacy_cases must be an array"))
        legacy_cases = []
    listed_paths = [
        spec.get("path")
        for spec in [*manifest["cases"], *legacy_cases]
        if isinstance(spec, dict)
    ]
    duplicate_paths = sorted({path for path in listed_paths if isinstance(path, str) and listed_paths.count(path) > 1})
    if duplicate_paths:
        diagnostics.append(Diagnostic(_display_path(fixture_manifest_path), "$.cases", "duplicate_fixture", "Duplicate Fixture paths: " + ", ".join(duplicate_paths)))
    fixture_root = bundle_root / ("fixtures/contracts" if contract_version == "0.1.0" else "fixtures")
    actual_paths = {
        path.relative_to(bundle_root).as_posix()
        for category in ("valid", "invalid", "legacy")
        for path in (fixture_root / category).glob("*")
        if path.is_file()
    }
    listed_set = {path for path in listed_paths if isinstance(path, str)}
    missing_from_manifest = sorted(actual_paths - listed_set)
    missing_from_disk = sorted(listed_set - actual_paths)
    if missing_from_manifest:
        diagnostics.append(Diagnostic(_display_path(fixture_manifest_path), "$.cases", "unregistered_fixture", "Unregistered Fixture files: " + ", ".join(missing_from_manifest)))
    if missing_from_disk:
        diagnostics.append(Diagnostic(_display_path(fixture_manifest_path), "$.cases", "missing_fixture", "Fixture files missing from Bundle: " + ", ".join(missing_from_disk)))

    for spec in manifest.get("cases", []):
        if not isinstance(spec, dict) or not isinstance(spec.get("path"), str):
            diagnostics.append(Diagnostic(_display_path(fixture_manifest_path), "$.cases", "fixture_manifest", "Each Fixture case must declare a string path"))
            continue
        try:
            path = resolve_repo_path(
                spec["path"],
                root=bundle_root,
                allowed_root="fixtures",
                must_exist=True,
                reject_symlinks=True,
            )
        except ValueError as exc:
            diagnostics.append(Diagnostic(str(spec.get("path", "<missing>")), "$", "unsafe_fixture_path", str(exc)))
            continue
        try:
            document = load_document(path)
        except Exception as exc:  # deterministic fixture load failure
            diagnostics.append(Diagnostic(spec["path"], "$", "fixture_load", str(exc)))
            continue
        loaded_cases.append({"spec": spec, "document": document})

    source_ids, claim_ids, evidence_ids, decision_ids, source_records = _collect_ids(loaded_cases)
    for case in loaded_cases:
        spec = case["spec"]
        document = case["document"]
        source = spec["path"]
        case_diagnostics = validate_instance(document, spec["schema"], source, schemas, registry)
        if not case_diagnostics:
            semantics = set(spec.get("semantics", []))
            if "workflow" in semantics:
                case_diagnostics.extend(workflow_semantics(document, source, catalog, contract_version=contract_version))
            if "profile" in semantics:
                case_diagnostics.extend(profile_semantics(document, source, workflow, catalog, contract_version=contract_version))
            if "paths" in semantics:
                case_diagnostics.extend(path_semantics(document, source))
            if "gate" in semantics:
                case_diagnostics.extend(gate_semantics(document, source))
            if "references" in semantics:
                case_diagnostics.extend(reference_integrity(document, source, source_ids, claim_ids, evidence_ids, decision_ids))
            if "interaction" in semantics:
                case_diagnostics.extend(interaction_semantics(document, source))
            if "research_origins" in semantics:
                idea_fixture = spec.get("idea_fixture")
                if not isinstance(idea_fixture, str):
                    case_diagnostics.append(Diagnostic(source, "$.idea_fixture", "fixture_manifest", "research_origins requires idea_fixture"))
                else:
                    try:
                        idea_path = resolve_repo_path(
                            idea_fixture,
                            root=bundle_root,
                            allowed_root="fixtures",
                            must_exist=True,
                            reject_symlinks=True,
                        )
                        idea_document = load_document(idea_path)
                    except (OSError, ValueError, TypeError, json.JSONDecodeError, yaml.YAMLError) as exc:
                        case_diagnostics.append(Diagnostic(source, "$.idea_fixture", "fixture_load", str(exc)))
                    else:
                        case_diagnostics.extend(research_origin_diagnostics(idea_document, document, source))
            if "projection_references" in semantics and isinstance(document, dict):
                case_diagnostics.extend(citation_closure_diagnostics(document, source, source_records))
            if contract_version == "0.3.2" and "score_aggregate" in semantics and isinstance(document, dict):
                judgment_fixtures = spec.get("judgment_fixtures")
                verification_fixtures = spec.get("verification_fixtures")
                if any(not isinstance(items, list) or not items or not all(isinstance(item, str) for item in items) for items in (judgment_fixtures, verification_fixtures)):
                    case_diagnostics.append(Diagnostic(source, "$", "fixture_manifest", "score_aggregate semantics require Judgment and Verification fixture refs"))
                else:
                    related_documents: dict[str, list[dict[str, Any]]] = {"judgments": [], "verifications": []}
                    for group_name, group_paths, artifact_type in (
                        ("judgments", judgment_fixtures, "dimension_judgment"),
                        ("verifications", verification_fixtures, "score_verification"),
                    ):
                        for related in group_paths:
                            try:
                                related_path = resolve_repo_path(related, root=bundle_root, allowed_root="fixtures", must_exist=True, reject_symlinks=True)
                                related_document = load_document(related_path)
                            except (OSError, ValueError, TypeError, json.JSONDecodeError, yaml.YAMLError) as exc:
                                case_diagnostics.append(Diagnostic(source, f"$.{group_name}", "fixture_load", str(exc)))
                                continue
                            if not isinstance(related_document, dict):
                                case_diagnostics.append(Diagnostic(source, f"$.{group_name}", "fixture_load", "Related aggregate fixture must be an object"))
                                continue
                            case_diagnostics.extend(validate_instance(related_document, f"competitor.schema.json#/$defs/{artifact_type}", related, schemas, registry))
                            related_documents[group_name].append(related_document)
                    rubric_ref = document.get("rubric_ref")
                    if not isinstance(rubric_ref, str):
                        case_diagnostics.append(Diagnostic(source, "$.rubric_ref", "fixture_load", "Transparent Score must declare its bundle-local Rubric ref"))
                    else:
                        try:
                            rubric_path = resolve_repo_path(rubric_ref, root=bundle_root, allowed_root="rubrics", must_exist=True, reject_symlinks=True)
                            rubric_document = load_document(rubric_path)
                        except (OSError, ValueError, TypeError, json.JSONDecodeError, yaml.YAMLError) as exc:
                            case_diagnostics.append(Diagnostic(source, "$.rubric_ref", "fixture_load", str(exc)))
                        else:
                            if isinstance(rubric_document, dict):
                                case_diagnostics.extend(validate_instance(rubric_document, "competitor.schema.json#/$defs/scoring_rubric", rubric_ref, schemas, registry))
                                aggregate_diagnostics, _ = transparent_score_aggregation_diagnostics(
                                    document,
                                    related_documents["judgments"],
                                    related_documents["verifications"],
                                    rubric_document,
                                    source,
                                )
                                case_diagnostics.extend(aggregate_diagnostics)
                            else:
                                case_diagnostics.append(Diagnostic(source, "$.rubric_ref", "fixture_load", "Scoring Rubric must be an object"))
            if contract_version == "0.3.2" and "report_successor" in semantics and isinstance(document, dict):
                base_report = None
                base_fixture = spec.get("base_report_fixture")
                if isinstance(base_fixture, str):
                    try:
                        base_path = resolve_repo_path(base_fixture, root=bundle_root, allowed_root="fixtures", must_exist=True, reject_symlinks=True)
                        loaded_base = load_document(base_path)
                    except (OSError, ValueError, TypeError, json.JSONDecodeError, yaml.YAMLError) as exc:
                        case_diagnostics.append(Diagnostic(source, "$.base_report_fixture", "fixture_load", str(exc)))
                    else:
                        if isinstance(loaded_base, dict):
                            base_report = loaded_base
                        else:
                            case_diagnostics.append(Diagnostic(source, "$.base_report_fixture", "fixture_load", "Base Report fixture must be an object"))
                case_diagnostics.extend(report_successor_diagnostics(document, source, base_report))
            if contract_version == "0.3.2" and "score_collection" in semantics and isinstance(document, dict):
                score_fixtures = spec.get("score_fixtures")
                judgment_fixtures = spec.get("judgment_fixtures")
                verification_fixtures = spec.get("verification_fixtures")
                ranking_fixture = spec.get("candidate_ranking_fixture")
                related_groups = (
                    ("score_fixtures", score_fixtures, "transparent_score"),
                    ("judgment_fixtures", judgment_fixtures, "dimension_judgment"),
                    ("verification_fixtures", verification_fixtures, "score_verification"),
                )
                if not isinstance(ranking_fixture, str) or any(not isinstance(items, list) or not items or not all(isinstance(item, str) for item in items) for _, items, _ in related_groups):
                    case_diagnostics.append(Diagnostic(source, "$", "fixture_manifest", "score_collection semantics require ranking, score, Judgment, and Verification fixture refs"))
                else:
                    related_documents: dict[str, list[dict[str, Any]]] = {}
                    candidate_ranking: dict[str, Any] | None = None
                    scoring_rubric: dict[str, Any] | None = None
                    for group_name, group_paths, artifact_type in related_groups:
                        related_documents[group_name] = []
                        for related in group_paths:
                            try:
                                related_path = resolve_repo_path(related, root=bundle_root, allowed_root="fixtures", must_exist=True, reject_symlinks=True)
                                related_document = load_document(related_path)
                            except (OSError, ValueError, TypeError, json.JSONDecodeError, yaml.YAMLError) as exc:
                                case_diagnostics.append(Diagnostic(source, f"$.{group_name}", "fixture_load", str(exc)))
                                continue
                            if not isinstance(related_document, dict):
                                case_diagnostics.append(Diagnostic(source, f"$.{group_name}", "fixture_load", "Related Artifact fixture must be an object"))
                                continue
                            case_diagnostics.extend(validate_instance(related_document, f"competitor.schema.json#/$defs/{artifact_type}", related, schemas, registry))
                            related_documents[group_name].append(related_document)
                    try:
                        ranking_path = resolve_repo_path(ranking_fixture, root=bundle_root, allowed_root="fixtures", must_exist=True, reject_symlinks=True)
                        ranking_document = load_document(ranking_path)
                    except (OSError, ValueError, TypeError, json.JSONDecodeError, yaml.YAMLError) as exc:
                        case_diagnostics.append(Diagnostic(source, "$.candidate_ranking_fixture", "fixture_load", str(exc)))
                    else:
                        if isinstance(ranking_document, dict):
                            candidate_ranking = ranking_document
                        else:
                            case_diagnostics.append(Diagnostic(source, "$.candidate_ranking_fixture", "fixture_load", "Candidate Ranking fixture must be an object"))
                    rubric_ref = document.get("rubric_ref")
                    if not isinstance(rubric_ref, str):
                        case_diagnostics.append(Diagnostic(source, "$.rubric_ref", "fixture_load", "Score collection must declare its bundle-local Rubric ref"))
                    else:
                        try:
                            rubric_path = resolve_repo_path(rubric_ref, root=bundle_root, allowed_root="rubrics", must_exist=True, reject_symlinks=True)
                            rubric_document = load_document(rubric_path)
                        except (OSError, ValueError, TypeError, json.JSONDecodeError, yaml.YAMLError) as exc:
                            case_diagnostics.append(Diagnostic(source, "$.rubric_ref", "fixture_load", str(exc)))
                        else:
                            if isinstance(rubric_document, dict):
                                scoring_rubric = rubric_document
                                case_diagnostics.extend(validate_instance(rubric_document, "competitor.schema.json#/$defs/scoring_rubric", rubric_ref, schemas, registry))
                            else:
                                case_diagnostics.append(Diagnostic(source, "$.rubric_ref", "fixture_load", "Scoring Rubric must be an object"))
                    if candidate_ranking is not None and scoring_rubric is not None:
                        case_diagnostics.extend(transparent_score_collection_diagnostics(
                            document,
                            related_documents["score_fixtures"],
                            candidate_ranking,
                            source,
                            related_documents["judgment_fixtures"],
                            related_documents["verification_fixtures"],
                            scoring_rubric,
                        ))
            if contract_version in {"0.3.1", "0.3.2"} and "chart_template" in semantics and isinstance(document, dict):
                case_diagnostics.extend(chart_template_diagnostics(document, source, catalog))
            if contract_version in {"0.3.1", "0.3.2"} and "chart_data" in semantics and isinstance(document, dict):
                chart_spec_fixture = spec.get("chart_spec_fixture")
                if not isinstance(chart_spec_fixture, str):
                    case_diagnostics.append(Diagnostic(source, "$.chart_spec_fixture", "fixture_manifest", "chart_data requires chart_spec_fixture"))
                else:
                    try:
                        chart_spec_path = resolve_repo_path(
                            chart_spec_fixture,
                            root=bundle_root,
                            allowed_root="fixtures",
                            must_exist=True,
                            reject_symlinks=True,
                        )
                        chart_spec = load_document(chart_spec_path)
                    except (OSError, ValueError, TypeError, json.JSONDecodeError, yaml.YAMLError) as exc:
                        case_diagnostics.append(Diagnostic(source, "$.chart_spec_fixture", "fixture_load", str(exc)))
                    else:
                        if not isinstance(chart_spec, dict):
                            case_diagnostics.append(Diagnostic(source, "$.chart_spec_fixture", "fixture_load", "Chart Spec fixture must be an object"))
                        else:
                            case_diagnostics.extend(chart_data_diagnostics(document, chart_spec, source))
            if contract_version in {"0.3.1", "0.3.2"} and "svg_static" in semantics and isinstance(document, dict):
                case_diagnostics.extend(svg_static_diagnostics(document, source))

        if spec.get("expected_valid", False):
            diagnostics.extend(case_diagnostics)
        elif not case_diagnostics:
            diagnostics.append(Diagnostic(source, "$", "unexpected_valid", "Negative fixture unexpectedly passed"))
        else:
            expected_rule = spec.get("expected_rule")
            if expected_rule and not any(item.rule == expected_rule for item in case_diagnostics):
                actual = ", ".join(sorted({item.rule for item in case_diagnostics}))
                diagnostics.append(Diagnostic(source, "$", "unexpected_failure", f"Expected rule {expected_rule}, got: {actual}"))
    return diagnostics, len(loaded_cases)


def registry_contract_diagnostics() -> tuple[list[Diagnostic], int]:
    """Validate the Registry's own Schema and instance before resolving Bundles."""
    schema_path = ROOT / "contracts" / "registry.schema.json"
    registry_path = ROOT / "contracts" / "registry.yaml"
    schema = load_document(schema_path)
    document = load_document(registry_path)
    diagnostics: list[Diagnostic] = []
    checked = 2
    if not isinstance(schema, dict):
        diagnostics.append(Diagnostic(_display_path(schema_path), "$", "contract_type", "Registry Schema must be an object"))
        return diagnostics, checked
    try:
        Draft202012Validator.check_schema(schema)
    except SchemaError as exc:
        diagnostics.append(Diagnostic(_display_path(schema_path), _json_path(exc.path), "meta_schema", exc.message))
        return diagnostics, checked
    if not isinstance(document, dict):
        diagnostics.append(Diagnostic(_display_path(registry_path), "$", "contract_type", "Version Registry must be an object"))
        return diagnostics, checked
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    for error in sorted(validator.iter_errors(document), key=lambda item: (_json_path(item.absolute_path), item.validator or "", item.message)):
        diagnostics.append(Diagnostic(_display_path(registry_path), _json_path(error.absolute_path), error.validator or "schema", error.message))
    return diagnostics, checked


def legacy_fixture_diagnostics(
    context: BundleContext,
    version_registry: VersionRegistry,
) -> tuple[list[Diagnostic], int]:
    """Evaluate explicit Legacy input references without materializing current artifacts."""
    manifest = load_document(context.fixture_manifest_path)
    if not isinstance(manifest, dict):
        return [Diagnostic(_display_path(context.fixture_manifest_path), "$", "fixture_manifest", "Fixture Manifest must be an object")], 0
    cases = manifest.get("legacy_cases", [])
    if not isinstance(cases, list):
        return [Diagnostic(_display_path(context.fixture_manifest_path), "$.legacy_cases", "fixture_manifest", "legacy_cases must be an array")], 0
    diagnostics: list[Diagnostic] = []
    checked = 0
    for index, spec in enumerate(cases):
        if not isinstance(spec, dict) or not isinstance(spec.get("path"), str):
            diagnostics.append(Diagnostic(_display_path(context.fixture_manifest_path), f"$.legacy_cases[{index}]", "fixture_manifest", "Legacy Fixture case must declare a string path"))
            continue
        source = spec["path"]
        try:
            path = resolve_repo_path(
                source,
                root=context.bundle.root,
                allowed_root="fixtures",
                must_exist=True,
                reject_symlinks=True,
            )
            reference = load_document(path)
        except (OSError, ValueError, TypeError, json.JSONDecodeError, yaml.YAMLError) as exc:
            diagnostics.append(Diagnostic(source, "$", "legacy_fixture_load", str(exc)))
            continue
        checked += 1
        if not isinstance(reference, dict):
            diagnostics.append(Diagnostic(source, "$", "legacy_fixture_shape", "Legacy input reference must be an object"))
            continue
        decision = evaluate_legacy_input_ref(
            reference,
            spec.get("target_contract_version"),
            repository_root=version_registry.path.parents[1],
            registry=version_registry,
        )
        expected_accepted = spec.get("expected_accepted")
        expected_reason = spec.get("expected_reason")
        expected_rule = spec.get("expected_rule")
        if decision.accepted is not expected_accepted:
            diagnostics.append(Diagnostic(source, "$", "unexpected_legacy_decision", f"Expected accepted={expected_accepted}; got {decision.accepted}"))
        if decision.reason != expected_reason:
            diagnostics.append(Diagnostic(source, "$", "unexpected_legacy_reason", f"Expected reason {expected_reason}; got {decision.reason}"))
        if decision.rule_id != expected_rule:
            diagnostics.append(Diagnostic(source, "$", "unexpected_legacy_rule", f"Expected rule {expected_rule}; got {decision.rule_id}"))
    return diagnostics, checked


def staged_validation_registry(context: BundleContext, version_registry: VersionRegistry) -> VersionRegistry:
    """Add an in-memory-only target entry for one staged static Bundle.

    The resulting Registry exists only during static validation.  It allows the
    staged Bundle's explicit legacy fixtures to exercise default-deny behavior
    without making that version resolvable by Runtime code.
    """
    contract_version = context.bundle.contract_version
    expected_root_ref = STAGED_STATIC_BUNDLE_ROOTS.get(contract_version)
    if expected_root_ref is None:
        return version_registry
    expected_root = (ROOT / expected_root_ref).resolve()
    if context.bundle.root.resolve() != expected_root:
        raise ContractResolutionError(
            f"Staged Bundle root does not match {expected_root_ref}",
            code="INPUT_INVALID",
            rule="staged_bundle_root",
        )
    if contract_version in version_registry.versions:
        raise ContractResolutionError(
            f"Staged Bundle {contract_version} must not be registered before promotion",
            code="INPUT_INVALID",
            rule="staged_bundle_registered",
        )
    entry = VersionEntry(
        contract_version=contract_version,
        status="staged",
        bundle_root_ref=expected_root_ref,
        bundle_root=expected_root,
        new_runs_allowed=False,
        resume_allowed=False,
        audit_allowed=False,
    )
    revalidation = (
        "source_schema",
        "content_hash",
        "freshness",
        "provenance",
        "security",
        "verification",
    )
    rules = tuple(
        CompatibilityRule(
            id=f"{ref_type}_seed_v1_to_v031",
            source_contract_version="0.1.0",
            target_contract_version=contract_version,
            ref_type=ref_type,
            purpose="seed_current_research",
            access="read_only",
            current_manifest_allowed=False,
            state_driving_allowed=False,
            required_revalidation=revalidation,
        )
        for ref_type in ("source", "evidence", "claim")
    )
    return replace(
        version_registry,
        versions={**version_registry.versions, contract_version: entry},
        compatibility_rules=(*version_registry.compatibility_rules, *rules),
    )


def _scope_bundle_diagnostics(
    diagnostics: Iterable[Diagnostic],
    context: BundleContext,
    *,
    repository_root: Path = ROOT,
) -> list[Diagnostic]:
    try:
        prefix = context.bundle.root.resolve().relative_to(repository_root.resolve()).as_posix()
    except ValueError:
        prefix = context.bundle.root.resolve().as_posix()
    if prefix in {"", "."}:
        return list(diagnostics)
    scoped: list[Diagnostic] = []
    for diagnostic in diagnostics:
        source = diagnostic.source
        if source != prefix and not source.startswith(prefix + "/"):
            source = f"{prefix}/{source}"
        scoped.append(Diagnostic(source, diagnostic.path, diagnostic.rule, diagnostic.message))
    return scoped


def validate_bundle(
    context: BundleContext,
    *,
    version_registry: VersionRegistry | None = None,
) -> tuple[list[Diagnostic], int]:
    """Validate one selected Contract Bundle without consulting another Bundle tree."""
    contract_version = context.bundle.contract_version
    catalog = build_repository_catalog(context.bundle.root)
    schemas, schema_registry = load_schemas(context.schema_dir)
    diagnostics = repository_inventory_diagnostics(catalog, contract_version=contract_version)
    diagnostics.extend(schema_diagnostics(schemas))
    checked = len(schemas)

    skill_errors, skill_count, _, skill_output_types = skill_repository_diagnostics(
        catalog,
        schemas,
        schema_registry,
        contract_version=contract_version,
    )
    diagnostics.extend(skill_errors)
    checked += skill_count

    template_errors, template_count = template_repository_diagnostics(catalog, contract_version=contract_version)
    diagnostics.extend(template_errors)
    checked += template_count

    subgraph_errors, subgraph_count = subgraph_repository_diagnostics(
        catalog,
        schemas,
        schema_registry,
        skill_output_types,
        contract_version=contract_version,
    )
    diagnostics.extend(subgraph_errors)
    checked += subgraph_count

    workflow = load_document(context.workflow_path)
    workflow_source = context.workflow_path.relative_to(context.bundle.root).as_posix()
    workflow_errors = validate_instance(workflow, "workflow.schema.json", workflow_source, schemas, schema_registry)
    diagnostics.extend(workflow_errors)
    if not workflow_errors:
        diagnostics.extend(workflow_semantics(workflow, workflow_source, catalog, contract_version=contract_version))
    checked += 1

    for profile_path in sorted(context.profile_dir.glob("*.yaml")):
        profile = load_document(profile_path)
        source = profile_path.relative_to(context.bundle.root).as_posix()
        profile_errors = validate_instance(profile, "profile.schema.json", source, schemas, schema_registry)
        diagnostics.extend(profile_errors)
        if not profile_errors:
            diagnostics.extend(profile_semantics(profile, source, workflow, catalog, contract_version=contract_version))
        checked += 1

    fixture_errors, fixture_count = fixture_diagnostics(
        schemas,
        schema_registry,
        workflow,
        bundle_root=context.bundle.root,
        fixture_manifest_path=context.fixture_manifest_path,
        contract_version=contract_version,
        catalog=catalog,
    )
    diagnostics.extend(fixture_errors)
    checked += fixture_count

    if contract_version != "0.1.0":
        selected_registry = version_registry or load_version_registry(repository_root=ROOT)
        selected_registry = staged_validation_registry(context, selected_registry)
        legacy_errors, legacy_count = legacy_fixture_diagnostics(context, selected_registry)
        diagnostics.extend(legacy_errors)
        checked += legacy_count

    if contract_version in {"0.3.1", "0.3.2"}:
        diagnostics.extend(v031_auxiliary_contract_diagnostics(catalog, contract_version=contract_version))
        checked += auxiliary_contract_check_count(contract_version)

    scope_root = version_registry.path.parents[1] if version_registry is not None else ROOT
    scoped = _scope_bundle_diagnostics(diagnostics, context, repository_root=scope_root)
    return sorted(scoped, key=lambda item: (item.source, item.path, item.rule, item.message)), checked


def validate_repository() -> tuple[list[Diagnostic], int]:
    """Validate Registry, immutable v0.1 audit, and every complete bundle closure."""
    diagnostics, checked = registry_contract_diagnostics()
    try:
        version_registry = load_version_registry(repository_root=ROOT)
    except ContractResolutionError as exc:
        diagnostics.append(Diagnostic("contracts/registry.yaml", "$", exc.rule, str(exc)))
        return sorted(diagnostics, key=lambda item: (item.source, item.path, item.rule, item.message)), checked

    checked += 1
    for failure in verify_integrity(version_registry, repository_root=ROOT):
        diagnostics.append(Diagnostic("contracts/registry.yaml", "$", "contract_integrity", failure))

    for version, entry in version_registry.versions.items():
        operation = "new_run" if entry.new_runs_allowed else "audit"
        try:
            bundle = resolve_contract_bundle(
                version,
                operation=operation,
                repository_root=ROOT,
                registry=version_registry,
            )
            context = load_bundle_context(bundle)
        except ContractResolutionError as exc:
            diagnostics.append(Diagnostic("contracts/registry.yaml", f"$.registry.versions.{version}", exc.rule, str(exc)))
            continue
        bundle_errors, bundle_count = validate_bundle(context, version_registry=version_registry)
        diagnostics.extend(bundle_errors)
        checked += bundle_count

    for version, root_ref in STAGED_STATIC_BUNDLE_ROOTS.items():
        if version in version_registry.versions:
            diagnostics.append(Diagnostic("contracts/registry.yaml", f"$.registry.versions.{version}", "staged_bundle_registered", f"Staged Bundle {version} must not be registered before promotion"))
            continue
        root = (ROOT / root_ref).resolve()
        try:
            context = load_bundle_context(ContractBundle(version, root, "staged", "audit"))
        except ContractResolutionError as exc:
            diagnostics.append(Diagnostic(root_ref, "$", exc.rule, str(exc)))
            continue
        bundle_errors, bundle_count = validate_bundle(context, version_registry=version_registry)
        diagnostics.extend(bundle_errors)
        checked += bundle_count
    return sorted(diagnostics, key=lambda item: (item.source, item.path, item.rule, item.message)), checked


def main() -> int:
    try:
        diagnostics, checked = validate_repository()
    except (OSError, ValueError, TypeError, json.JSONDecodeError, yaml.YAMLError) as exc:
        print(f"[INTERNAL] {type(exc).__name__}: {exc}", file=sys.stderr)
        return 10
    except Exception as exc:  # pragma: no cover - last-resort stable exit contract
        print(f"[INTERNAL] {type(exc).__name__}: {exc}", file=sys.stderr)
        return 10
    if diagnostics:
        for diagnostic in diagnostics:
            print(diagnostic.render(), file=sys.stderr)
        print(f"[FAILED] checked={checked} errors={len(diagnostics)}", file=sys.stderr)
        return 2
    print(f"[OK] checked={checked} errors=0")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
