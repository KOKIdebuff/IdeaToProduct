from __future__ import annotations

from types import MappingProxyType

import pytest

from skillgraph_runtime.domain import NodeAddress, NodeDefinition, NodeKind
from skillgraph_runtime.errors import RuntimeContractError
from skillgraph_runtime.graph import _compile_top_level, _ensure_dag


def node(node_id: str, *dependencies: str) -> NodeDefinition:
    return NodeDefinition(
        address=NodeAddress((), node_id),
        kind=NodeKind.SKILL,
        implementation_ref="idea-intake",
        depends_on=dependencies,
    )


def test_graph_rejects_cycles_and_dangling_dependencies():
    cycle = {
        NodeAddress((), "alpha"): node("alpha", "beta"),
        NodeAddress((), "beta"): node("beta", "alpha"),
    }
    with pytest.raises(RuntimeContractError) as cyclic:
        _ensure_dag(MappingProxyType(cycle))
    assert cyclic.value.rule == "dag_cycle"

    dangling = {NodeAddress((), "alpha"): node("alpha", "missing")}
    with pytest.raises(RuntimeContractError) as missing:
        _ensure_dag(MappingProxyType(dangling))
    assert missing.value.rule == "dependency_reference"


def test_profile_extension_is_inserted_without_replacing_core_order():
    workflow = {
        "nodes": {
            "alpha": {"kind": "skill", "skill": "idea-intake"},
            "omega": {"kind": "skill", "skill": "research-contract", "depends_on": ["alpha"]},
        }
    }
    profile = {
        "research_defaults": {"competitor_count": 5, "primary_sources": 8, "user_evidence_items": 15, "technology_items": 5},
        "competitor_visualizations": {"required": ["feature_matrix", "positioning_map"]},
        "extra_questions": [],
        "extensions": [
            {
                "id": "extension",
                "node": {"kind": "skill", "skill": "user-evidence"},
                "insert_after": "alpha",
                "before": "omega",
                "required": False,
                "config": {"ordered": ["first", "second"]},
            }
        ],
    }
    graph = _compile_top_level(workflow, profile, {})
    assert [address.node_id for address in graph.declaration_order] == ["alpha", "extension", "omega"]
    assert graph.definitions[NodeAddress((), "extension")].depends_on == ("alpha",)
    assert graph.definitions[NodeAddress((), "omega")].depends_on == ("extension",)
    with pytest.raises(TypeError):
        graph.definitions[NodeAddress((), "extension")].relevant_config["ordered"] = ()
