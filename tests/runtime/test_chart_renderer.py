from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from xml.etree import ElementTree as ET

import pytest
import yaml

import skillgraph_runtime.chart_renderer as renderer_module
from skillgraph_runtime.chart_renderer import NativeChartRenderer
from skillgraph_runtime.errors import RuntimeContractError


ROOT = Path(__file__).resolve().parents[2]
BUNDLE_ROOT = ROOT / "contracts" / "0.3.2"


_DATA_BY_CONTRACT = {
    "competitor_by_dimension_cells": {
        "data_contract": "competitor_by_dimension_cells",
        "rows": [
            {"competitor_id": "cmp_b", "dimension_id": "workflow", "value": 0.4, "evidence_refs": ["EV-002"]},
            {"competitor_id": "cmp_a", "dimension_id": "workflow", "value": 0.8, "evidence_refs": ["EV-001"]},
        ],
    },
    "competitor_xy_points": {
        "data_contract": "competitor_xy_points",
        "rows": [
            {"competitor_id": "cmp_b", "x_value": 2, "y_value": 3, "x_label": "Cost", "y_label": "Depth", "evidence_refs": ["EV-002"]},
            {"competitor_id": "cmp_a", "x_value": 1, "y_value": 4, "x_label": "Cost", "y_label": "Depth", "evidence_refs": ["EV-001"]},
        ],
    },
    "category_values": {
        "data_contract": "category_values",
        "rows": [
            {"category": "cmp_b", "value": 2.5, "series": "observed", "evidence_refs": ["EV-002"]},
            {"category": "cmp_a", "value": 1.5, "series": "observed", "evidence_refs": ["EV-001"]},
        ],
    },
    "time_series_values": {
        "data_contract": "time_series_values",
        "rows": [
            {"timestamp": "2026-02-01T00:00:00Z", "value": 4, "series": "cmp_a", "evidence_refs": ["EV-002"]},
            {"timestamp": "2026-01-01T00:00:00Z", "value": 2, "series": "cmp_a", "evidence_refs": ["EV-001"]},
        ],
    },
    "bucket_counts": {
        "data_contract": "bucket_counts",
        "rows": [
            {"bucket": "positive", "count": 4, "evidence_refs": ["EV-001"]},
            {"bucket": "negative", "count": 1, "evidence_refs": ["EV-002"]},
        ],
    },
}


@pytest.fixture(scope="module")
def renderer() -> NativeChartRenderer:
    return NativeChartRenderer.from_bundle_root(BUNDLE_ROOT)


def _spec(chart_id: str, renderer: NativeChartRenderer) -> dict:
    template = renderer.templates[chart_id]
    return {
        "chart_id": chart_id,
        "renderer_kind": template.renderer_kind,
        "data_contract": template.data_contract,
        "title": f"{chart_id} title",
        "description": f"{chart_id} description",
        "width": 960,
        "height": 540,
        "style_tokens": {"theme": "report_default"},
    }


def test_registry_loads_exact_staged_v032_template_set(renderer: NativeChartRenderer):
    assert renderer.contract_version == "0.3.2"
    assert set(renderer.templates) == {
        "feature_matrix",
        "feature_ux_matrix",
        "capability_matrix",
        "integration_security_coverage",
        "positioning_map",
        "momentum_comparison",
        "ecosystem_momentum",
        "cost_performance",
        "pricing_comparison",
        "oss_activity",
        "sentiment_distribution",
    }


@pytest.mark.parametrize(
    "chart_id",
    [
        "feature_matrix",
        "feature_ux_matrix",
        "capability_matrix",
        "integration_security_coverage",
        "positioning_map",
        "momentum_comparison",
        "ecosystem_momentum",
        "cost_performance",
        "pricing_comparison",
        "oss_activity",
        "sentiment_distribution",
    ],
)
def test_all_registered_chart_ids_render_deterministic_accessible_svg(renderer: NativeChartRenderer, chart_id: str):
    spec = _spec(chart_id, renderer)
    data = deepcopy(_DATA_BY_CONTRACT[spec["data_contract"]])
    first = renderer.render_svg(spec, data)
    second = renderer.render_svg(deepcopy(spec), deepcopy(data))
    assert first == second
    root = ET.fromstring(first)
    assert root.tag.endswith("svg")
    assert root.attrib["viewBox"] == "0 0 960 540"
    assert root.attrib["role"] == "img"
    assert root.attrib["aria-labelledby"] == "chart-title chart-desc"
    assert [child.tag.rsplit("}", 1)[-1] for child in root[:2]] == ["title", "desc"]


def test_renderer_escapes_untrusted_labels_and_does_not_create_active_markup(renderer: NativeChartRenderer):
    spec = _spec("momentum_comparison", renderer)
    spec["title"] = '<script>alert("x")</script>'
    data = deepcopy(_DATA_BY_CONTRACT["category_values"])
    data["rows"][0]["category"] = '<image href="https://example.test/x"/>'
    svg = renderer.render_svg(spec, data)
    assert "<script>" not in svg
    assert "<image " not in svg
    assert "&lt;script&gt;" in svg
    assert "&lt;image" in svg


@pytest.mark.parametrize(
    ("mutate", "rule"),
    [
        (lambda spec, data: spec.update(chart_id="not_registered"), "chart_template"),
        (lambda spec, data: spec.update(renderer_kind="line"), "chart_template"),
        (lambda spec, data: data.update(data_contract="time_series_values"), "chart_data_contract"),
        (lambda spec, data: data["rows"].append(deepcopy(data["rows"][0])), "chart_data_duplicate"),
        (lambda spec, data: data["rows"][0].update(value=float("nan")), "chart_data_value"),
    ],
)
def test_renderer_fails_closed_on_invalid_template_or_data(renderer: NativeChartRenderer, mutate, rule: str):
    spec = _spec("momentum_comparison", renderer)
    data = deepcopy(_DATA_BY_CONTRACT["category_values"])
    mutate(spec, data)
    with pytest.raises(RuntimeContractError) as captured:
        renderer.render_svg(spec, data)
    assert captured.value.code == "SCHEMA_INVALID"
    assert captured.value.rule == rule


@pytest.mark.parametrize(
    "unsafe_svg",
    [
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 960 540" role="img" aria-labelledby="chart-title chart-desc"><title id="chart-title">x</title><desc id="chart-desc">x</desc><script/></svg>',
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 960 540" role="img" aria-labelledby="chart-title chart-desc"><title id="chart-title">x</title><desc id="chart-desc">x</desc><foreignObject/></svg>',
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 960 540" role="img" aria-labelledby="chart-title chart-desc" onclick="x"><title id="chart-title">x</title><desc id="chart-desc">x</desc></svg>',
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 960 540" role="img" aria-labelledby="chart-title chart-desc"><title id="chart-title">x</title><desc id="chart-desc">x</desc><image href="https://example.test/x"/></svg>',
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 960 540" role="img" aria-labelledby="chart-title chart-desc"><title id="chart-title">x</title><desc id="chart-desc">x</desc><style>@import url(https://example.test/x)</style></svg>',
    ],
)
def test_static_svg_policy_rejects_active_or_external_content(renderer: NativeChartRenderer, unsafe_svg: str):
    spec, _template = renderer._validate_spec(_spec("feature_matrix", renderer))
    with pytest.raises(RuntimeContractError) as captured:
        renderer_module._validate_static_svg(unsafe_svg, spec, renderer._svg_policy)
    assert captured.value.rule == "chart_svg_output"


def test_registry_loader_rejects_other_contract_version(tmp_path: Path):
    root = tmp_path / "bundle"
    path = root / "chart-templates" / "registry.yaml"
    path.parent.mkdir(parents=True)
    registry = yaml.safe_load((BUNDLE_ROOT / "chart-templates" / "registry.yaml").read_text(encoding="utf-8"))
    registry["contract_version"] = "0.3.1"
    path.write_text(yaml.safe_dump(registry, sort_keys=False), encoding="utf-8")
    with pytest.raises(RuntimeContractError) as captured:
        NativeChartRenderer.from_bundle_root(root)
    assert captured.value.rule == "chart_template_registry_version"
