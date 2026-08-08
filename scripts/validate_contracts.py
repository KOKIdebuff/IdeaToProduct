"""Validate Product Discovery SkillGraph Step 1 contracts.

This is a static repository validator, not the normative Runtime CLI described by
SPEC v0.1. It never fetches remote schemas and never mutates repository files.
"""

from __future__ import annotations

import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any, Iterable
from urllib.parse import unquote, urlparse

import yaml
from jsonschema import Draft202012Validator, FormatChecker
from jsonschema.exceptions import SchemaError
from referencing import Registry, Resource


ROOT = Path(__file__).resolve().parents[1]
SCHEMA_DIR = ROOT / "schemas"
PROFILE_DIR = ROOT / "profiles"
FIXTURE_MANIFEST = ROOT / "fixtures" / "contracts" / "manifest.json"
MAX_DOCUMENT_BYTES = 5 * 1024 * 1024

CORE_NODES = {
    "idea",
    "contract",
    "gate_research",
    "research_verifier",
    "research_gap",
    "evidence_waiver",
    "research_synthesis",
    "opportunity",
    "gate_direction",
    "definition",
    "feasibility",
    "proof",
    "proof_result",
    "scope",
    "gate_scope",
    "prd",
    "prd_consistency_verifier",
    "build_readiness_verifier",
}
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


@dataclass(frozen=True)
class Diagnostic:
    source: str
    path: str
    rule: str
    message: str

    def render(self) -> str:
        location = f"{self.source}:{self.path}" if self.path else self.source
        return f"{location} [{self.rule}] {self.message}"


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
        return json.loads(text)
    return yaml.safe_load(text)


def load_schemas() -> tuple[dict[str, dict[str, Any]], Registry]:
    schemas: dict[str, dict[str, Any]] = {}
    resources: list[tuple[str, Resource[Any]]] = []
    for path in sorted(SCHEMA_DIR.glob("*.schema.json")):
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


def validate_instance(
    instance: Any,
    schema_name: str,
    source: str,
    schemas: dict[str, dict[str, Any]],
    registry: Registry,
) -> list[Diagnostic]:
    schema = schemas.get(schema_name)
    if schema is None:
        return [Diagnostic(source, "$", "missing_schema", f"Schema not found: {schema_name}")]
    validator = Draft202012Validator(schema, registry=registry, format_checker=FormatChecker())
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


def workflow_semantics(document: dict[str, Any], source: str) -> list[Diagnostic]:
    diagnostics: list[Diagnostic] = []
    nodes = document.get("nodes", {})
    if not isinstance(nodes, dict):
        return diagnostics

    missing_core = sorted(CORE_NODES - set(nodes))
    if missing_core:
        diagnostics.append(Diagnostic(source, "$.nodes", "missing_core_nodes", f"Missing core nodes: {', '.join(missing_core)}"))

    for node_id, node in nodes.items():
        if not isinstance(node, dict):
            continue
        dependencies = node.get("depends_on", [])
        if node_id in dependencies:
            diagnostics.append(Diagnostic(source, f"$.nodes.{node_id}.depends_on", "self_dependency", "Node cannot depend on itself"))
        for dependency in dependencies:
            if dependency not in nodes:
                diagnostics.append(Diagnostic(source, f"$.nodes.{node_id}.depends_on", "missing_dependency", f"Unknown dependency: {dependency}"))

        expected_field = KIND_FIELD.get(node.get("kind"))
        present_fields = IMPLEMENTATION_FIELDS.intersection(node)
        if expected_field and present_fields != {expected_field}:
            diagnostics.append(Diagnostic(source, f"$.nodes.{node_id}", "kind_contract", f"Kind {node.get('kind')} must use exactly {expected_field}; found {sorted(present_fields)}"))

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
            if schema_ref and not (SCHEMA_DIR / schema_ref).is_file():
                diagnostics.append(Diagnostic(source, f"$.nodes.{node_id}.on_submit.validate", "missing_schema", f"Schema does not exist: {schema_ref}"))

        if "trigger_on_terminal_events" in node and node_id != "build_readiness_verifier":
            diagnostics.append(Diagnostic(source, f"$.nodes.{node_id}.trigger_on_terminal_events", "terminal_trigger_owner", "Only build_readiness_verifier may declare terminal triggers"))

        if node_id in RESEARCH_BRANCHES and node.get("configurable_by_profile") is not True:
            diagnostics.append(Diagnostic(source, f"$.nodes.{node_id}", "profile_branch", "Research branch must be configurable_by_profile"))
        if node_id not in RESEARCH_BRANCHES and node.get("configurable_by_profile"):
            diagnostics.append(Diagnostic(source, f"$.nodes.{node_id}", "profile_branch", "Only the four research branches may be profile-configurable"))

    cycle = _cycle(nodes)
    if cycle:
        diagnostics.append(Diagnostic(source, "$.nodes", "dag_cycle", "Dependency cycle: " + " -> ".join(cycle)))

    readiness = nodes.get("build_readiness_verifier", {})
    readiness_writers = [node_id for node_id, node in nodes.items() if node.get("skill") == "build-readiness-verifier"]
    if readiness.get("kind") != "verifier" or readiness_writers != ["build_readiness_verifier"]:
        diagnostics.append(Diagnostic(source, "$.nodes.build_readiness_verifier", "readiness_writer", "Build Readiness Verifier must remain the unique readiness writer"))
    return diagnostics


def profile_semantics(document: dict[str, Any], source: str, workflow: dict[str, Any]) -> list[Diagnostic]:
    diagnostics: list[Diagnostic] = []
    profile_id = document.get("profile", {}).get("id")
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


def _is_safe_relative_path(value: str) -> bool:
    if not value or value.startswith(("/", "\\")) or re.match(r"^[A-Za-z]:", value):
        return False
    return ".." not in re.split(r"[/\\]+", value)


def path_semantics(document: dict[str, Any], source: str) -> list[Diagnostic]:
    candidates: list[tuple[str, Any]] = []
    if "skill" in document:
        candidates.extend(("$.reads", value) for value in document.get("reads", []))
        candidates.extend(("$.writes", value) for value in document.get("writes", []))
        candidates.extend(("$.permissions.workspace_write", value) for value in document.get("permissions", {}).get("workspace_write", []))
    if "executor_request" in document:
        candidates.extend(("$.executor_request.permissions.workspace_write_paths", value) for value in document["executor_request"].get("permissions", {}).get("workspace_write_paths", []))
    return [Diagnostic(source, path, "unsafe_path", f"Path must stay relative to the discovery workspace: {value}") for path, value in candidates if not isinstance(value, str) or not _is_safe_relative_path(value)]


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


def _collect_ids(cases: list[dict[str, Any]]) -> tuple[set[str], set[str], set[str], set[str]]:
    source_ids: set[str] = set()
    claim_ids: set[str] = set()
    evidence_ids: set[str] = set()
    decision_ids: set[str] = set()
    for case in cases:
        if not case["spec"].get("expected_valid", False):
            continue
        document = case["document"]
        if "source" in document:
            source_ids.add(document["source"].get("id"))
        if "claim" in document:
            claim_ids.add(document["claim"].get("id"))
        if "evidence" in document:
            evidence_ids.add(document["evidence"].get("id"))
        if "decision" in document:
            decision_ids.add(document["decision"].get("id"))
    return source_ids, claim_ids, evidence_ids, decision_ids


def resolve_repo_path(relative_path: str) -> Path:
    if not isinstance(relative_path, str) or not _is_safe_relative_path(relative_path):
        raise ValueError(f"Unsafe repository-relative path: {relative_path!r}")
    resolved = (ROOT / relative_path).resolve()
    try:
        resolved.relative_to(ROOT.resolve())
    except ValueError as exc:
        raise ValueError(f"Path escapes repository root: {relative_path}") from exc
    return resolved


def fixture_diagnostics(
    schemas: dict[str, dict[str, Any]],
    registry: Registry,
    workflow: dict[str, Any],
) -> tuple[list[Diagnostic], int]:
    manifest = load_document(FIXTURE_MANIFEST)
    loaded_cases: list[dict[str, Any]] = []
    diagnostics: list[Diagnostic] = []
    for spec in manifest.get("cases", []):
        try:
            path = resolve_repo_path(spec["path"])
        except ValueError as exc:
            diagnostics.append(Diagnostic(str(spec.get("path", "<missing>")), "$", "unsafe_fixture_path", str(exc)))
            continue
        try:
            document = load_document(path)
        except Exception as exc:  # deterministic fixture load failure
            diagnostics.append(Diagnostic(spec["path"], "$", "fixture_load", str(exc)))
            continue
        loaded_cases.append({"spec": spec, "document": document})

    source_ids, claim_ids, evidence_ids, decision_ids = _collect_ids(loaded_cases)
    for case in loaded_cases:
        spec = case["spec"]
        document = case["document"]
        source = spec["path"]
        case_diagnostics = validate_instance(document, spec["schema"], source, schemas, registry)
        if not case_diagnostics:
            semantics = set(spec.get("semantics", []))
            if "workflow" in semantics:
                case_diagnostics.extend(workflow_semantics(document, source))
            if "profile" in semantics:
                case_diagnostics.extend(profile_semantics(document, source, workflow))
            if "paths" in semantics:
                case_diagnostics.extend(path_semantics(document, source))
            if "gate" in semantics:
                case_diagnostics.extend(gate_semantics(document, source))
            if "references" in semantics:
                case_diagnostics.extend(reference_integrity(document, source, source_ids, claim_ids, evidence_ids, decision_ids))

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


def validate_repository() -> tuple[list[Diagnostic], int]:
    schemas, registry = load_schemas()
    diagnostics = schema_diagnostics(schemas)
    checked = len(schemas)

    workflow_path = ROOT / "workflow.yaml"
    workflow = load_document(workflow_path)
    workflow_source = _display_path(workflow_path)
    workflow_errors = validate_instance(workflow, "workflow.schema.json", workflow_source, schemas, registry)
    diagnostics.extend(workflow_errors)
    if not workflow_errors:
        diagnostics.extend(workflow_semantics(workflow, workflow_source))
    checked += 1

    for profile_path in sorted(PROFILE_DIR.glob("*.yaml")):
        profile = load_document(profile_path)
        source = _display_path(profile_path)
        profile_errors = validate_instance(profile, "profile.schema.json", source, schemas, registry)
        diagnostics.extend(profile_errors)
        if not profile_errors:
            diagnostics.extend(profile_semantics(profile, source, workflow))
        checked += 1

    fixture_errors, fixture_count = fixture_diagnostics(schemas, registry, workflow)
    diagnostics.extend(fixture_errors)
    checked += fixture_count
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
