"""Compile one validated Contract Bundle into immutable Runtime graphs."""

from __future__ import annotations

from dataclasses import dataclass, replace
from pathlib import Path
from types import MappingProxyType
from typing import Any, Mapping

from .bundles import (
    BundleContext,
    ContractResolutionError,
    VersionRegistry,
    _load_document,
    load_bundle_context,
    load_bundle_schemas,
    load_version_registry,
    resolve_contract_bundle,
    validate_bundle,
)
from .domain import (
    ConditionExpression,
    ConditionPredicate,
    NodeAddress,
    NodeDefinition,
    NodeKind,
    Priority,
    RunPolicy,
    TerminalEvent,
    deep_freeze,
)
from .errors import RuntimeContractError


@dataclass(frozen=True)
class CompiledGraph:
    graph_path: tuple[str, ...]
    definitions: Mapping[NodeAddress, NodeDefinition]
    declaration_order: tuple[NodeAddress, ...]
    dynamic_fanout_templates: frozenset[NodeAddress] = frozenset()


@dataclass(frozen=True)
class CompiledBundle:
    context: BundleContext
    registry: VersionRegistry
    workflow_id: str
    workflow_version: str
    profile_id: str
    profile_ref: str
    run_policy: RunPolicy
    top_level: CompiledGraph
    subgraphs: Mapping[str, CompiledGraph]
    skills: Mapping[str, Mapping[str, Any]]
    schemas: Mapping[str, Mapping[str, Any]]
    schema_registry: Any
    validation_checked: int

    def definition(self, address: NodeAddress) -> NodeDefinition:
        graph = self.top_level if not address.graph_path else self.subgraphs.get(address.graph_path[0])
        if graph is None:
            raise RuntimeContractError(
                "Unknown graph path",
                rule="node_address_graph",
                details={"graph_path": address.graph_path},
            )
        template = NodeAddress(address.graph_path, address.node_id)
        try:
            definition = graph.definitions[template]
        except KeyError as exc:
            raise RuntimeContractError(
                "Unknown node address",
                rule="node_address",
                details={"graph_path": address.graph_path, "node_id": address.node_id},
            ) from exc
        return replace(definition, address=address)


def _predicate(raw: Mapping[str, Any]) -> ConditionPredicate:
    fields = ("node_status", "verification_result", "gate_decision", "feasibility_result", "proof_outcome")
    selected = [field for field in fields if field in raw]
    if len(selected) != 1:
        raise RuntimeContractError("Condition predicate must select one result field", rule="condition_shape")
    value = raw[selected[0]]
    expected = tuple(value) if isinstance(value, list) else (value,)
    return ConditionPredicate(raw["node"], selected[0], expected)


def _condition(raw: Mapping[str, Any] | None) -> ConditionExpression | None:
    if raw is None:
        return None
    if "any_of" in raw:
        return ConditionExpression(tuple(_predicate(item) for item in raw["any_of"]), any_of=True)
    return ConditionExpression((_predicate(raw),), any_of=False)


def _implementation_ref(raw: Mapping[str, Any], kind: NodeKind) -> str | None:
    field = {
        NodeKind.SKILL: "skill",
        NodeKind.VERIFIER: "skill",
        NodeKind.SUBGRAPH: "subgraph",
        NodeKind.HUMAN_GATE: "gate",
        NodeKind.ROUTER: "router",
        NodeKind.EXTERNAL_INPUT: "contract",
    }[kind]
    return raw.get(field)


def _node_definition(
    node_id: str,
    raw: Mapping[str, Any],
    *,
    graph_path: tuple[str, ...],
    declaration_order: int,
    skills: Mapping[str, Mapping[str, Any]],
    profile_node: Mapping[str, Any] | None = None,
    relevant_config: Mapping[str, Any] | None = None,
) -> NodeDefinition:
    kind = NodeKind(raw["kind"])
    implementation = _implementation_ref(raw, kind)
    enabled = True
    required = bool(raw.get("required", False))
    priority = Priority.HIGH
    if profile_node is not None:
        mode = profile_node["mode"]
        enabled = mode != "disabled"
        required = mode == "required"
        priority = Priority(profile_node["priority"])
    interactive = bool(implementation and implementation in skills and "interaction" in skills[implementation])
    triggers = tuple(TerminalEvent(item) for item in raw.get("trigger_on_terminal_events", []))
    return NodeDefinition(
        address=NodeAddress(graph_path, node_id),
        kind=kind,
        implementation_ref=implementation,
        depends_on=tuple(raw.get("depends_on", [])),
        required=required,
        configurable_by_profile=bool(raw.get("configurable_by_profile", False)),
        enabled=enabled,
        interactive=interactive,
        condition=_condition(raw.get("when")),
        trigger_on_terminal_events=triggers,
        priority=priority,
        declaration_order=declaration_order,
        relevant_config=relevant_config or {},
    )


def _ensure_dag(definitions: Mapping[NodeAddress, NodeDefinition]) -> None:
    by_id = {address.node_id: definition for address, definition in definitions.items()}
    indegree = {node_id: 0 for node_id in by_id}
    outgoing = {node_id: [] for node_id in by_id}
    for node_id, definition in by_id.items():
        for dependency in definition.depends_on:
            if dependency not in by_id:
                raise RuntimeContractError(
                    "Graph contains a dangling dependency",
                    rule="dependency_reference",
                    details={"node_id": node_id, "dependency": dependency},
                )
            indegree[node_id] += 1
            outgoing[dependency].append(node_id)
    queue = [node_id for node_id, degree in indegree.items() if degree == 0]
    visited = 0
    while queue:
        current = queue.pop(0)
        visited += 1
        for successor in outgoing[current]:
            indegree[successor] -= 1
            if indegree[successor] == 0:
                queue.append(successor)
    if visited != len(by_id):
        raise RuntimeContractError("Graph contains a dependency cycle", rule="dag_cycle")


def _load_skills(context: BundleContext) -> Mapping[str, Mapping[str, Any]]:
    skills: dict[str, Mapping[str, Any]] = {}
    for path in sorted(context.skill_dir.glob("*/skill.yaml")):
        document = _load_document(path)
        skill_id = document["skill"]["id"]
        skills[skill_id] = deep_freeze(document)
    return MappingProxyType(skills)


def _load_profile(context: BundleContext, profile_id: str) -> Mapping[str, Any]:
    profiles: dict[str, Mapping[str, Any]] = {}
    for path in sorted(context.profile_dir.glob("*.yaml")):
        document = _load_document(path)
        profiles[document["profile"]["id"]] = document
    try:
        profile = profiles[profile_id]
    except KeyError as exc:
        raise RuntimeContractError(
            f"Unknown product profile: {profile_id}",
            rule="profile_id",
            details={"profile_id": profile_id, "allowed": tuple(sorted(profiles))},
        ) from exc
    return profile


def _compile_top_level(
    workflow: Mapping[str, Any],
    profile: Mapping[str, Any],
    skills: Mapping[str, Mapping[str, Any]],
) -> CompiledGraph:
    raw_nodes: dict[str, Mapping[str, Any]] = {key: dict(value) for key, value in workflow["nodes"].items()}
    extension_config: dict[str, Mapping[str, Any]] = {}
    for extension in profile.get("extensions", []):
        node_id = extension["id"]
        if node_id in raw_nodes:
            raise RuntimeContractError("Profile extension replaces a Core node", rule="profile_extension_replace")
        raw = dict(extension["node"])
        raw["required"] = extension["required"]
        dependencies = list(raw.get("depends_on", []))
        if extension["insert_after"] not in dependencies:
            dependencies.append(extension["insert_after"])
        raw["depends_on"] = dependencies
        extension_config[node_id] = extension.get("config", {})
        before = extension["before"]
        if extension["insert_after"] not in raw_nodes or before not in raw_nodes:
            raise RuntimeContractError("Profile extension anchors are missing", rule="profile_extension_anchor")
        target = dict(raw_nodes[before])
        target_dependencies = [node_id if item == extension["insert_after"] else item for item in target.get("depends_on", [])]
        if node_id not in target_dependencies:
            target_dependencies.append(node_id)
        target["depends_on"] = target_dependencies
        raw_nodes[before] = target
        reordered: dict[str, Mapping[str, Any]] = {}
        for existing_id, existing in raw_nodes.items():
            if existing_id == before:
                reordered[node_id] = raw
            reordered[existing_id] = existing
        raw_nodes = reordered

    definitions: dict[NodeAddress, NodeDefinition] = {}
    order: list[NodeAddress] = []
    for index, (node_id, raw) in enumerate(raw_nodes.items()):
        profile_node = profile.get("research_nodes", {}).get(node_id) if raw.get("configurable_by_profile") else None
        profile_config: dict[str, Any] = dict(extension_config.get(node_id, {}))
        if profile_node is not None:
            profile_config.update(
                {
                    "research_mode": profile_node["mode"],
                    "research_defaults": profile["research_defaults"],
                    "profile_priority": profile_node["priority"],
                }
            )
            if node_id == "competitor":
                profile_config["competitor_visualizations"] = profile["competitor_visualizations"]
            profile_config["extra_questions"] = profile["extra_questions"]
        definition = _node_definition(
            node_id,
            raw,
            graph_path=(),
            declaration_order=index,
            skills=skills,
            profile_node=profile_node,
            relevant_config=profile_config,
        )
        definitions[definition.address] = definition
        order.append(definition.address)
    _ensure_dag(definitions)
    return CompiledGraph((), MappingProxyType(definitions), tuple(order))


def _compile_subgraphs(context: BundleContext, top_level: CompiledGraph, skills: Mapping[str, Mapping[str, Any]]) -> Mapping[str, CompiledGraph]:
    available: dict[str, Mapping[str, Any]] = {}
    for path in sorted(context.subgraph_dir.glob("*.yaml")):
        document = _load_document(path)
        available[document["subgraph"]["id"]] = document

    compiled: dict[str, CompiledGraph] = {}
    for top_address in top_level.declaration_order:
        top_definition = top_level.definitions[top_address]
        if top_definition.kind is not NodeKind.SUBGRAPH:
            continue
        try:
            document = available[top_definition.implementation_ref or ""]
        except KeyError as exc:
            raise RuntimeContractError("Subgraph contract is missing", rule="subgraph_reference") from exc
        graph_path = (top_address.node_id,)
        definitions: dict[NodeAddress, NodeDefinition] = {}
        order: list[NodeAddress] = []
        for index, (node_id, raw) in enumerate(document["nodes"].items()):
            definition = _node_definition(
                node_id,
                raw,
                graph_path=graph_path,
                declaration_order=index,
                skills=skills,
                relevant_config={"subgraph_ref": top_definition.implementation_ref},
            )
            definitions[definition.address] = definition
            order.append(definition.address)
        _ensure_dag(definitions)
        dynamic = frozenset(
            {NodeAddress(graph_path, "deep_dive")}
            if top_definition.implementation_ref == "competitor-research" and NodeAddress(graph_path, "deep_dive") in definitions
            else set()
        )
        compiled[top_address.node_id] = CompiledGraph(graph_path, MappingProxyType(definitions), tuple(order), dynamic)
    return MappingProxyType(compiled)


def compile_bundle(
    repository_root: Path,
    profile_id: str,
    contract_version: str | None = None,
) -> CompiledBundle:
    try:
        registry = load_version_registry(repository_root=repository_root)
        registry = replace(
            registry,
            versions=MappingProxyType(dict(registry.versions)),
            frozen_documents_sha256=MappingProxyType(dict(registry.frozen_documents_sha256)),
        )
        bundle = resolve_contract_bundle(
            contract_version,
            operation="new_run",
            repository_root=repository_root,
            registry=registry,
        )
        context = load_bundle_context(bundle)
        diagnostics, checked = validate_bundle(context, registry=registry)
    except ContractResolutionError as exc:
        raise RuntimeContractError(str(exc), code=exc.code, rule=exc.rule) from exc
    if diagnostics:
        first = diagnostics[0]
        raise RuntimeContractError(
            "Selected Contract Bundle failed validation",
            code="SCHEMA_INVALID",
            rule="bundle_validation",
            details={"checked": checked, "errors": len(diagnostics), "first": first.render()},
        )
    workflow = _load_document(context.workflow_path)
    profile = _load_profile(context, profile_id)
    skills = _load_skills(context)
    top_level = _compile_top_level(workflow, profile, skills)
    subgraphs = _compile_subgraphs(context, top_level, skills)
    policy = workflow["policies"]
    run_policy = RunPolicy(
        max_parallel=policy["max_parallel"],
        automated_attempt_timeout_minutes=policy["automated_attempt_timeout_minutes"],
        max_sources_per_research_node=policy["max_sources_per_research_node"],
        max_retries_per_node=policy["max_retries_per_node"],
        max_global_research_cycles=policy["max_global_research_cycles"],
        automated_run_timeout_minutes=policy["automated_run_timeout_minutes"],
        host_token_limit=policy["host_token_limit"],
        host_cost_limit=policy["host_cost_limit"],
    )
    schemas, schema_registry = load_bundle_schemas(context)
    return CompiledBundle(
        context=context,
        registry=registry,
        workflow_id=workflow["workflow"]["id"],
        workflow_version=workflow["workflow"]["version"],
        profile_id=profile_id,
        profile_ref=f"{profile_id}@{bundle.contract_version}",
        run_policy=run_policy,
        top_level=top_level,
        subgraphs=subgraphs,
        skills=skills,
        schemas=deep_freeze(schemas),
        schema_registry=schema_registry,
        validation_checked=checked,
    )
