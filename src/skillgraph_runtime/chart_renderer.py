"""Deterministic, local-only native SVG chart rendering.

The renderer deliberately stays outside RuntimeKernel persistence and workflow
orchestration.  A future visualization task may compose it with a verified
Chart Spec/Data Artifact, but this module only accepts in-memory documents and
returns one self-contained canonical SVG string.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
from html import escape
from math import isfinite
from numbers import Real
from pathlib import Path
from types import MappingProxyType
from typing import Any
from urllib.parse import urlparse
from xml.etree import ElementTree as ET
import re

import yaml

from .errors import RuntimeContractError


_SVG_NAMESPACE = "http://www.w3.org/2000/svg"
_MIN_WIDTH = 320
_MAX_WIDTH = 2400
_MIN_HEIGHT = 240
_MAX_HEIGHT = 1600
_KIND_CONTRACTS = MappingProxyType(
    {
        "matrix": "competitor_by_dimension_cells",
        "scatter": "competitor_xy_points",
        "bar": "category_values",
        "line": "time_series_values",
        "distribution": "bucket_counts",
    }
)
_INITIAL_TEMPLATE_PAIRS = MappingProxyType(
    {
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
)
_STYLE = (
    ".chart{font-family:Arial,sans-serif;fill:#172033;}"
    ".axis{stroke:#65738b;stroke-width:1;}"
    ".grid{stroke:#d9e0ea;stroke-width:1;}"
    ".label{font-size:12px;fill:#34445f;}"
    ".value{font-size:11px;fill:#172033;}"
    ".legend{font-size:11px;fill:#34445f;}"
)
_PALETTE = ("#2563eb", "#0f766e", "#d97706", "#9333ea", "#dc2626", "#0891b2")


class _RegistryYamlLoader(yaml.SafeLoader):
    """Safe YAML loader with YAML 1.2-style boolean spellings.

    The approved Registry intentionally contains the event-handler prefix
    ``on``.  PyYAML's YAML 1.1 compatibility resolver turns that unquoted token
    into ``True``; retaining only true/false boolean spellings preserves policy
    semantics without widening deserialization capabilities.
    """


_RegistryYamlLoader.yaml_implicit_resolvers = {
    key: [
        (tag, expression)
        for tag, expression in resolvers
        if tag != "tag:yaml.org,2002:bool"
    ]
    for key, resolvers in yaml.SafeLoader.yaml_implicit_resolvers.items()
}
yaml.add_implicit_resolver(
    "tag:yaml.org,2002:bool",
    re.compile(r"^(?:true|True|TRUE|false|False|FALSE)$"),
    list("tTfF"),
    Loader=_RegistryYamlLoader,
)


@dataclass(frozen=True)
class ChartTemplate:
    """One closed Registry entry selected by ``chart_id``."""

    chart_id: str
    renderer_kind: str
    data_contract: str


@dataclass(frozen=True)
class _SvgPolicy:
    required_attributes: frozenset[str]
    required_elements: frozenset[str]
    forbidden_elements: frozenset[str]
    forbidden_attribute_prefixes: tuple[str, ...]


@dataclass(frozen=True)
class _ChartSpec:
    chart_id: str
    renderer_kind: str
    data_contract: str
    title: str
    description: str
    width: int
    height: int


@dataclass(frozen=True)
class NativeChartRenderer:
    """Render one Chart Spec/Data pair through an explicit native Registry.

    Instances are immutable and hold no RuntimeKernel, Storage, network, or
    Version Registry dependency.  The explicit Bundle root is intentional: a
    caller must opt into the Contract bundle whose closed template catalogue it
    wants to use.
    """

    contract_version: str
    templates: Mapping[str, ChartTemplate]
    _svg_policy: _SvgPolicy

    @classmethod
    def from_bundle_root(cls, bundle_root: Path) -> "NativeChartRenderer":
        """Load a validated native chart Registry from one local Bundle root."""

        root = Path(bundle_root).resolve()
        registry_path = root / "chart-templates" / "registry.yaml"
        try:
            resolved_registry = registry_path.resolve(strict=True)
            resolved_registry.relative_to(root)
        except (OSError, ValueError) as exc:
            raise RuntimeContractError(
                "Native Chart Template Registry must be a local file inside the supplied Bundle root",
                code="INPUT_INVALID",
                rule="chart_template_registry_path",
            ) from exc
        if not resolved_registry.is_file():
            raise RuntimeContractError(
                "Native Chart Template Registry is not a regular file",
                code="INPUT_INVALID",
                rule="chart_template_registry_path",
            )
        try:
            loader = _RegistryYamlLoader(resolved_registry.read_text(encoding="utf-8"))
            try:
                document = loader.get_single_data()
            finally:
                loader.dispose()
        except (OSError, yaml.YAMLError) as exc:
            raise RuntimeContractError(
                "Native Chart Template Registry could not be read safely",
                code="SCHEMA_INVALID",
                rule="chart_template_registry",
            ) from exc
        if not isinstance(document, Mapping):
            raise RuntimeContractError(
                "Native Chart Template Registry must be an object",
                code="SCHEMA_INVALID",
                rule="chart_template_registry",
            )

        version = document.get("contract_version")
        if version != "0.3.2":
            raise RuntimeContractError(
                "Native Chart Template Registry must declare contract_version 0.3.2",
                code="SCHEMA_INVALID",
                rule="chart_template_registry_version",
            )
        raw_templates = document.get("templates")
        if not isinstance(raw_templates, Mapping) or not raw_templates:
            raise RuntimeContractError(
                "Native Chart Template Registry must declare a non-empty template map",
                code="SCHEMA_INVALID",
                rule="chart_template_registry",
            )

        templates: dict[str, ChartTemplate] = {}
        for chart_id, raw_template in raw_templates.items():
            if not isinstance(chart_id, str) or not chart_id:
                raise RuntimeContractError(
                    "Native Chart Template Registry chart IDs must be non-empty strings",
                    code="SCHEMA_INVALID",
                    rule="chart_template_registry",
                )
            if not isinstance(raw_template, Mapping) or set(raw_template) != {"renderer_kind", "data_contract"}:
                raise RuntimeContractError(
                    "Each Native Chart Template must define exactly renderer_kind and data_contract",
                    code="SCHEMA_INVALID",
                    rule="chart_template_registry",
                )
            renderer_kind = raw_template.get("renderer_kind")
            data_contract = raw_template.get("data_contract")
            if not isinstance(renderer_kind, str) or _KIND_CONTRACTS.get(renderer_kind) != data_contract:
                raise RuntimeContractError(
                    "Native Chart Template has an unsupported renderer_kind/data_contract pair",
                    code="SCHEMA_INVALID",
                    rule="chart_template_registry",
                )
            templates[chart_id] = ChartTemplate(chart_id, renderer_kind, data_contract)
        actual_pairs = {chart_id: (template.renderer_kind, template.data_contract) for chart_id, template in templates.items()}
        if actual_pairs != dict(_INITIAL_TEMPLATE_PAIRS):
            raise RuntimeContractError(
                "Native Chart Template Registry must contain exactly the approved 0.3.2 template set",
                code="SCHEMA_INVALID",
                rule="chart_template_registry",
            )

        raw_policy = document.get("svg_contract")
        if not isinstance(raw_policy, Mapping):
            raise RuntimeContractError(
                "Native Chart Template Registry must declare svg_contract",
                code="SCHEMA_INVALID",
                rule="chart_svg_policy",
            )
        policy = _load_svg_policy(raw_policy)
        _validate_png_policy(document.get("png_compatibility"))
        return cls(str(version), MappingProxyType(templates), policy)

    def render_svg(self, chart_spec: Mapping[str, Any], chart_data: Mapping[str, Any]) -> str:
        """Return a safe, deterministic SVG or fail closed on invalid input."""

        spec, template = self._validate_spec(chart_spec)
        rows = _validate_chart_data(chart_data, template)
        renderer = {
            "matrix": _render_matrix,
            "scatter": _render_scatter,
            "bar": _render_bar,
            "line": _render_line,
            "distribution": _render_distribution,
        }[template.renderer_kind]
        content = renderer(spec, rows)
        svg = _svg_document(spec, content)
        _validate_static_svg(svg, spec, self._svg_policy)
        return svg

    def _validate_spec(self, document: Mapping[str, Any]) -> tuple[_ChartSpec, ChartTemplate]:
        if not isinstance(document, Mapping):
            raise RuntimeContractError("Chart Spec must be an object", code="SCHEMA_INVALID", rule="chart_spec")
        allowed = {"chart_id", "renderer_kind", "data_contract", "title", "description", "width", "height", "style_tokens"}
        required = allowed - {"style_tokens"}
        if not required <= set(document) or set(document) - allowed:
            raise RuntimeContractError(
                "Chart Spec has missing or unsupported fields",
                code="SCHEMA_INVALID",
                rule="chart_spec",
            )
        chart_id = _required_text(document.get("chart_id"), rule="chart_spec")
        template = self.templates.get(chart_id)
        if template is None:
            raise RuntimeContractError(
                "Chart Spec selects an unregistered native template",
                code="SCHEMA_INVALID",
                rule="chart_template",
            )
        renderer_kind = _required_text(document.get("renderer_kind"), rule="chart_spec")
        data_contract = _required_text(document.get("data_contract"), rule="chart_spec")
        if (renderer_kind, data_contract) != (template.renderer_kind, template.data_contract):
            raise RuntimeContractError(
                "Chart Spec renderer_kind and data_contract must match the selected native template",
                code="SCHEMA_INVALID",
                rule="chart_template",
            )
        if "style_tokens" in document:
            _validate_style_tokens(document["style_tokens"])
        return (
            _ChartSpec(
                chart_id=chart_id,
                renderer_kind=renderer_kind,
                data_contract=data_contract,
                title=_required_text(document.get("title"), rule="chart_spec"),
                description=_required_text(document.get("description"), rule="chart_spec"),
                width=_dimension(document.get("width"), field="width"),
                height=_dimension(document.get("height"), field="height"),
            ),
            template,
        )


def _load_svg_policy(raw: Mapping[str, Any]) -> _SvgPolicy:
    required_attributes = _string_set(raw.get("required_attributes"), rule="chart_svg_policy")
    required_elements = _string_set(raw.get("required_elements"), rule="chart_svg_policy")
    forbidden_elements = _string_set(raw.get("forbidden_elements"), rule="chart_svg_policy")
    prefixes = raw.get("forbidden_attribute_prefixes")
    if not isinstance(prefixes, list) or not all(isinstance(item, str) and item for item in prefixes):
        raise RuntimeContractError("SVG policy attribute prefixes must be non-empty strings", code="SCHEMA_INVALID", rule="chart_svg_policy")
    if not {"viewBox", "role"} <= required_attributes or not {"title", "desc"} <= required_elements:
        raise RuntimeContractError("SVG policy must require viewBox, role, title, and desc", code="SCHEMA_INVALID", rule="chart_svg_policy")
    if not {"script", "foreignObject"} <= forbidden_elements or "on" not in prefixes:
        raise RuntimeContractError("SVG policy must forbid script, foreignObject, and event handlers", code="SCHEMA_INVALID", rule="chart_svg_policy")
    if raw.get("external_references") != "forbidden" or raw.get("network_dependency") != "forbidden":
        raise RuntimeContractError("SVG policy must forbid external references and network dependencies", code="SCHEMA_INVALID", rule="chart_svg_policy")
    return _SvgPolicy(required_attributes, required_elements, forbidden_elements, tuple(prefixes))


def _validate_png_policy(raw: Any) -> None:
    if not isinstance(raw, Mapping) or raw.get("canonical") is not False or raw.get("explicit_request_only") is not True:
        raise RuntimeContractError("Native Chart Template Registry must keep PNG non-canonical and explicit", code="SCHEMA_INVALID", rule="chart_png_policy")
    if raw.get("failure_after_valid_svg") != "PARTIAL" or raw.get("svg_fallback") != "forbidden":
        raise RuntimeContractError("Native Chart Template Registry has an invalid PNG fallback policy", code="SCHEMA_INVALID", rule="chart_png_policy")


def _string_set(value: Any, *, rule: str) -> frozenset[str]:
    if not isinstance(value, list) or not value or not all(isinstance(item, str) and item for item in value):
        raise RuntimeContractError("Registry policy values must be non-empty string lists", code="SCHEMA_INVALID", rule=rule)
    return frozenset(value)


def _validate_chart_data(document: Mapping[str, Any], template: ChartTemplate) -> tuple[Mapping[str, Any], ...]:
    if not isinstance(document, Mapping) or set(document) != {"data_contract", "rows"}:
        raise RuntimeContractError("Chart Data must contain exactly data_contract and rows", code="SCHEMA_INVALID", rule="chart_data")
    if document.get("data_contract") != template.data_contract:
        raise RuntimeContractError("Chart Data contract must match the selected Chart Spec", code="SCHEMA_INVALID", rule="chart_data_contract")
    raw_rows = document.get("rows")
    if not isinstance(raw_rows, list) or not raw_rows:
        raise RuntimeContractError("Chart Data rows must be a non-empty list", code="SCHEMA_INVALID", rule="chart_data")
    validator = {
        "matrix": _matrix_rows,
        "scatter": _scatter_rows,
        "bar": _bar_rows,
        "line": _line_rows,
        "distribution": _distribution_rows,
    }[template.renderer_kind]
    return validator(raw_rows)


def _matrix_rows(rows: list[Any]) -> tuple[Mapping[str, Any], ...]:
    normalized: list[Mapping[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for item in rows:
        row = _row_mapping(item)
        competitor = _required_text(row.get("competitor_id"), rule="chart_data_shape")
        dimension = _required_text(row.get("dimension_id"), rule="chart_data_shape")
        key = (competitor, dimension)
        _reject_duplicate(key, seen, rule="chart_data_duplicate")
        normalized.append(
            MappingProxyType(
                {
                    "competitor_id": competitor,
                    "dimension_id": dimension,
                    "value": _finite_number(row.get("value")),
                    "evidence_refs": _evidence_refs(row.get("evidence_refs")),
                }
            )
        )
    return tuple(sorted(normalized, key=lambda row: (str(row["competitor_id"]), str(row["dimension_id"]))))


def _scatter_rows(rows: list[Any]) -> tuple[Mapping[str, Any], ...]:
    normalized: list[Mapping[str, Any]] = []
    seen: set[str] = set()
    labels: set[tuple[str, str]] = set()
    for item in rows:
        row = _row_mapping(item)
        competitor = _required_text(row.get("competitor_id"), rule="chart_data_shape")
        _reject_duplicate(competitor, seen, rule="chart_data_duplicate")
        x_label = _required_text(row.get("x_label"), rule="chart_data_shape")
        y_label = _required_text(row.get("y_label"), rule="chart_data_shape")
        labels.add((x_label, y_label))
        normalized.append(
            MappingProxyType(
                {
                    "competitor_id": competitor,
                    "x_value": _finite_number(row.get("x_value")),
                    "y_value": _finite_number(row.get("y_value")),
                    "x_label": x_label,
                    "y_label": y_label,
                    "evidence_refs": _evidence_refs(row.get("evidence_refs")),
                }
            )
        )
    if len(labels) != 1:
        raise RuntimeContractError("Scatter rows must declare one consistent pair of axis labels", code="SCHEMA_INVALID", rule="chart_data_shape")
    return tuple(sorted(normalized, key=lambda row: str(row["competitor_id"])))


def _bar_rows(rows: list[Any]) -> tuple[Mapping[str, Any], ...]:
    normalized: list[Mapping[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for item in rows:
        row = _row_mapping(item)
        category = _required_text(row.get("category"), rule="chart_data_shape")
        series = _optional_series(row)
        key = (category, series)
        _reject_duplicate(key, seen, rule="chart_data_duplicate")
        normalized.append(
            MappingProxyType(
                {
                    "category": category,
                    "series": series,
                    "value": _finite_number(row.get("value")),
                    "evidence_refs": _evidence_refs(row.get("evidence_refs")),
                }
            )
        )
    return tuple(sorted(normalized, key=lambda row: (str(row["category"]), str(row["series"]))))


def _line_rows(rows: list[Any]) -> tuple[Mapping[str, Any], ...]:
    normalized: list[Mapping[str, Any]] = []
    seen: set[tuple[str, datetime]] = set()
    for item in rows:
        row = _row_mapping(item)
        timestamp, parsed_timestamp = _iso_timestamp(row.get("timestamp"))
        series = _optional_series(row)
        key = (series, parsed_timestamp)
        _reject_duplicate(key, seen, rule="chart_data_duplicate")
        normalized.append(
            MappingProxyType(
                {
                    "timestamp": timestamp,
                    "parsed_timestamp": parsed_timestamp,
                    "series": series,
                    "value": _finite_number(row.get("value")),
                    "evidence_refs": _evidence_refs(row.get("evidence_refs")),
                }
            )
        )
    return tuple(sorted(normalized, key=lambda row: (str(row["series"]), row["parsed_timestamp"])))


def _distribution_rows(rows: list[Any]) -> tuple[Mapping[str, Any], ...]:
    normalized: list[Mapping[str, Any]] = []
    seen: set[str] = set()
    for item in rows:
        row = _row_mapping(item)
        bucket = _required_text(row.get("bucket"), rule="chart_data_shape")
        _reject_duplicate(bucket, seen, rule="chart_data_duplicate")
        count = row.get("count")
        if isinstance(count, bool) or not isinstance(count, int) or count < 0:
            raise RuntimeContractError("Distribution count must be a non-negative integer", code="SCHEMA_INVALID", rule="chart_data_value")
        normalized.append(MappingProxyType({"bucket": bucket, "count": count, "evidence_refs": _evidence_refs(row.get("evidence_refs"))}))
    return tuple(sorted(normalized, key=lambda row: str(row["bucket"])))


def _row_mapping(value: Any) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise RuntimeContractError("Chart Data rows must be objects", code="SCHEMA_INVALID", rule="chart_data_shape")
    return value


def _required_text(value: Any, *, rule: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise RuntimeContractError("Required Chart field must be a non-empty string", code="SCHEMA_INVALID", rule=rule)
    return value.strip()


def _optional_series(row: Mapping[str, Any]) -> str:
    if "series" not in row:
        return ""
    return _required_text(row.get("series"), rule="chart_data_shape")


def _finite_number(value: Any) -> float:
    if isinstance(value, bool) or not isinstance(value, Real) or not isfinite(float(value)):
        raise RuntimeContractError("Chart numeric values must be finite numbers", code="SCHEMA_INVALID", rule="chart_data_value")
    return float(value)


def _evidence_refs(value: Any) -> tuple[str, ...]:
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence) or not value:
        raise RuntimeContractError("Chart rows require non-empty evidence_refs", code="SCHEMA_INVALID", rule="chart_data_evidence")
    references = tuple(_required_text(item, rule="chart_data_evidence") for item in value)
    if len(set(references)) != len(references):
        raise RuntimeContractError("Chart row evidence_refs must be unique", code="SCHEMA_INVALID", rule="chart_data_evidence")
    return references


def _iso_timestamp(value: Any) -> tuple[str, datetime]:
    timestamp = _required_text(value, rule="chart_data_time")
    normalized = timestamp[:-1] + "+00:00" if timestamp.endswith("Z") else timestamp
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError as exc:
        raise RuntimeContractError("Line timestamps must be ISO-8601 datetimes", code="SCHEMA_INVALID", rule="chart_data_time") from exc
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return timestamp, parsed.astimezone(timezone.utc)


def _reject_duplicate(key: Any, seen: set[Any], *, rule: str) -> None:
    if key in seen:
        raise RuntimeContractError("Chart Data contains a duplicate render key", code="SCHEMA_INVALID", rule=rule)
    seen.add(key)


def _dimension(value: Any, *, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise RuntimeContractError("Chart dimensions must be integers", code="SCHEMA_INVALID", rule="chart_spec_dimension")
    lower, upper = (_MIN_WIDTH, _MAX_WIDTH) if field == "width" else (_MIN_HEIGHT, _MAX_HEIGHT)
    if not lower <= value <= upper:
        raise RuntimeContractError("Chart dimensions are outside the supported native SVG bounds", code="SCHEMA_INVALID", rule="chart_spec_dimension")
    return value


def _validate_style_tokens(value: Any) -> None:
    if not isinstance(value, Mapping) or not all(isinstance(key, str) and key and isinstance(item, str) and item for key, item in value.items()):
        raise RuntimeContractError("Chart style_tokens must be a string-to-string map", code="SCHEMA_INVALID", rule="chart_spec_style_tokens")


def _render_matrix(spec: _ChartSpec, rows: tuple[Mapping[str, Any], ...]) -> str:
    competitors = sorted({str(row["competitor_id"]) for row in rows})
    dimensions = sorted({str(row["dimension_id"]) for row in rows})
    values = [float(row["value"]) for row in rows]
    low, high = _domain(values)
    left, top, plot_width, plot_height = _plot_area(spec)
    cell_width = plot_width / len(dimensions)
    cell_height = plot_height / len(competitors)
    lookup = {(str(row["competitor_id"]), str(row["dimension_id"])): float(row["value"]) for row in rows}
    parts = _axes(spec, left, top, plot_width, plot_height)
    for index, dimension in enumerate(dimensions):
        center = left + (index + 0.5) * cell_width
        parts.append(_text(center, top - 10, dimension, anchor="middle", css_class="label"))
    for row_index, competitor in enumerate(competitors):
        y = top + row_index * cell_height
        parts.append(_text(left - 8, y + cell_height / 2 + 4, competitor, anchor="end", css_class="label"))
        for column_index, dimension in enumerate(dimensions):
            value = lookup.get((competitor, dimension))
            fill = "#f8fafc" if value is None else _heat_color(_scale(value, low, high))
            x = left + column_index * cell_width
            parts.append(_rect(x + 1, y + 1, cell_width - 2, cell_height - 2, fill=fill))
            if value is not None:
                parts.append(_text(x + cell_width / 2, y + cell_height / 2 + 4, _number(value), anchor="middle", css_class="value"))
    return "".join(parts)


def _render_scatter(spec: _ChartSpec, rows: tuple[Mapping[str, Any], ...]) -> str:
    left, top, plot_width, plot_height = _plot_area(spec)
    x_low, x_high = _domain([float(row["x_value"]) for row in rows])
    y_low, y_high = _domain([float(row["y_value"]) for row in rows])
    parts = _axes(spec, left, top, plot_width, plot_height)
    parts.append(_text(left + plot_width / 2, top + plot_height + 42, str(rows[0]["x_label"]), anchor="middle", css_class="label"))
    parts.append(_text(left, top - 18, str(rows[0]["y_label"]), css_class="label"))
    for index, row in enumerate(rows):
        x = left + _scale(float(row["x_value"]), x_low, x_high) * plot_width
        y = top + (1 - _scale(float(row["y_value"]), y_low, y_high)) * plot_height
        parts.append(_circle(x, y, 5, fill=_PALETTE[index % len(_PALETTE)]))
        parts.append(_text(x + 7, y - 7, str(row["competitor_id"]), css_class="value"))
    return "".join(parts)


def _render_bar(spec: _ChartSpec, rows: tuple[Mapping[str, Any], ...]) -> str:
    left, top, plot_width, plot_height = _plot_area(spec)
    categories = sorted({str(row["category"]) for row in rows})
    series = sorted({str(row["series"]) for row in rows})
    values = [float(row["value"]) for row in rows]
    low, high = _domain_with_zero(values)
    zero = top + (1 - _scale(0, low, high)) * plot_height
    lookup = {(str(row["category"]), str(row["series"])): float(row["value"]) for row in rows}
    group_width = plot_width / len(categories)
    bar_width = max(2.0, (group_width * 0.72) / len(series))
    parts = _axes(spec, left, top, plot_width, plot_height)
    parts.append(_line(left, zero, left + plot_width, zero, css_class="axis"))
    for category_index, category in enumerate(categories):
        base = left + category_index * group_width + group_width * 0.14
        parts.append(_text(left + (category_index + 0.5) * group_width, top + plot_height + 18, category, anchor="middle", css_class="label"))
        for series_index, series_name in enumerate(series):
            value = lookup.get((category, series_name))
            if value is None:
                continue
            y = top + (1 - _scale(value, low, high)) * plot_height
            rect_y = min(y, zero)
            height = max(abs(zero - y), 1.0)
            parts.append(_rect(base + series_index * bar_width, rect_y, bar_width - 1, height, fill=_PALETTE[series_index % len(_PALETTE)]))
    parts.extend(_legend(series, left, top))
    return "".join(parts)


def _render_line(spec: _ChartSpec, rows: tuple[Mapping[str, Any], ...]) -> str:
    left, top, plot_width, plot_height = _plot_area(spec)
    series = sorted({str(row["series"]) for row in rows})
    moments = sorted({row["parsed_timestamp"] for row in rows})
    values = [float(row["value"]) for row in rows]
    low, high = _domain(values)
    moment_index = {moment: index for index, moment in enumerate(moments)}
    denominator = max(len(moments) - 1, 1)
    parts = _axes(spec, left, top, plot_width, plot_height)
    for series_index, series_name in enumerate(series):
        points = []
        for row in rows:
            if row["series"] != series_name:
                continue
            x = left + moment_index[row["parsed_timestamp"]] / denominator * plot_width
            y = top + (1 - _scale(float(row["value"]), low, high)) * plot_height
            points.append((x, y))
        encoded_points = " ".join(f"{_number(x)},{_number(y)}" for x, y in points)
        parts.append(f'<polyline fill="none" stroke="{_PALETTE[series_index % len(_PALETTE)]}" stroke-width="2" points="{encoded_points}"/>')
        for x, y in points:
            parts.append(_circle(x, y, 3.5, fill=_PALETTE[series_index % len(_PALETTE)]))
    for index, moment in enumerate(moments):
        label = moment.date().isoformat()
        x = left + index / denominator * plot_width
        parts.append(_text(x, top + plot_height + 18, label, anchor="middle", css_class="label"))
    parts.extend(_legend(series, left, top))
    return "".join(parts)


def _render_distribution(spec: _ChartSpec, rows: tuple[Mapping[str, Any], ...]) -> str:
    left, top, plot_width, plot_height = _plot_area(spec)
    high = max(max(int(row["count"]) for row in rows), 1)
    bar_width = plot_width / len(rows) * 0.72
    parts = _axes(spec, left, top, plot_width, plot_height)
    for index, row in enumerate(rows):
        x = left + index * (plot_width / len(rows)) + (plot_width / len(rows) - bar_width) / 2
        height = int(row["count"]) / high * plot_height
        y = top + plot_height - height
        parts.append(_rect(x, y, bar_width, max(height, 1.0), fill=_PALETTE[index % len(_PALETTE)]))
        parts.append(_text(x + bar_width / 2, top + plot_height + 18, str(row["bucket"]), anchor="middle", css_class="label"))
        parts.append(_text(x + bar_width / 2, y - 6, str(row["count"]), anchor="middle", css_class="value"))
    return "".join(parts)


def _svg_document(spec: _ChartSpec, content: str) -> str:
    return (
        f'<svg xmlns="{_SVG_NAMESPACE}" width="{spec.width}" height="{spec.height}" '
        f'viewBox="0 0 {spec.width} {spec.height}" role="img" aria-labelledby="chart-title chart-desc">'
        f'<title id="chart-title">{_escaped(spec.title)}</title>'
        f'<desc id="chart-desc">{_escaped(spec.description)}</desc>'
        f"<style>{_STYLE}</style><g class=\"chart\">{content}</g></svg>"
    )


def _plot_area(spec: _ChartSpec) -> tuple[float, float, float, float]:
    left, top, right, bottom = 72.0, 54.0, 24.0, 58.0
    return left, top, float(spec.width) - left - right, float(spec.height) - top - bottom


def _axes(spec: _ChartSpec, left: float, top: float, width: float, height: float) -> list[str]:
    del spec
    return [
        _line(left, top, left, top + height, css_class="axis"),
        _line(left, top + height, left + width, top + height, css_class="axis"),
        _line(left, top + height * 0.5, left + width, top + height * 0.5, css_class="grid"),
    ]


def _legend(series: Sequence[str], left: float, top: float) -> list[str]:
    if len(series) == 1 and not series[0]:
        return []
    parts: list[str] = []
    for index, name in enumerate(series):
        x = left + index * 110
        parts.append(_rect(x, top - 34, 10, 10, fill=_PALETTE[index % len(_PALETTE)]))
        parts.append(_text(x + 14, top - 25, name or "default", css_class="legend"))
    return parts


def _domain(values: Sequence[float]) -> tuple[float, float]:
    low, high = min(values), max(values)
    if low == high:
        padding = max(abs(low) * 0.1, 1.0)
        return low - padding, high + padding
    return low, high


def _domain_with_zero(values: Sequence[float]) -> tuple[float, float]:
    low, high = min(min(values), 0.0), max(max(values), 0.0)
    if low == high:
        return -1.0, 1.0
    return low, high


def _scale(value: float, low: float, high: float) -> float:
    return (value - low) / (high - low)


def _heat_color(value: float) -> str:
    start = (239, 246, 255)
    end = (30, 64, 175)
    channels = [round(first + (second - first) * value) for first, second in zip(start, end)]
    return "#" + "".join(f"{channel:02x}" for channel in channels)


def _number(value: float) -> str:
    return format(value, ".10g")


def _escaped(value: str) -> str:
    return escape(value, quote=True)


def _text(x: float, y: float, value: str, *, anchor: str | None = None, css_class: str) -> str:
    anchor_attribute = "" if anchor is None else f' text-anchor="{anchor}"'
    return f'<text x="{_number(x)}" y="{_number(y)}" class="{css_class}"{anchor_attribute}>{_escaped(value)}</text>'


def _line(x1: float, y1: float, x2: float, y2: float, *, css_class: str) -> str:
    return f'<line x1="{_number(x1)}" y1="{_number(y1)}" x2="{_number(x2)}" y2="{_number(y2)}" class="{css_class}"/>'


def _rect(x: float, y: float, width: float, height: float, *, fill: str) -> str:
    return f'<rect x="{_number(x)}" y="{_number(y)}" width="{_number(width)}" height="{_number(height)}" fill="{fill}"/>'


def _circle(cx: float, cy: float, radius: float, *, fill: str) -> str:
    return f'<circle cx="{_number(cx)}" cy="{_number(cy)}" r="{_number(radius)}" fill="{fill}"/>'


def _validate_static_svg(svg: str, spec: _ChartSpec, policy: _SvgPolicy) -> None:
    try:
        root = ET.fromstring(svg)
    except ET.ParseError as exc:  # pragma: no cover - defensive self-audit.
        raise RuntimeContractError("Native Renderer produced malformed SVG", code="SCHEMA_INVALID", rule="chart_svg_output") from exc
    if _local_name(root.tag) != "svg" or root.get("viewBox") != f"0 0 {spec.width} {spec.height}" or root.get("role") != "img":
        raise RuntimeContractError("Native Renderer produced an invalid SVG root", code="SCHEMA_INVALID", rule="chart_svg_output")
    if root.get("aria-labelledby") != "chart-title chart-desc":
        raise RuntimeContractError("Native Renderer produced an inaccessible SVG", code="SCHEMA_INVALID", rule="chart_svg_output")
    child_names = {_local_name(child.tag) for child in root}
    if not policy.required_elements <= child_names:
        raise RuntimeContractError("Native Renderer omitted a required SVG element", code="SCHEMA_INVALID", rule="chart_svg_output")
    for element in root.iter():
        tag = _local_name(element.tag)
        if tag in policy.forbidden_elements or tag == "image":
            raise RuntimeContractError("Native Renderer produced a forbidden SVG element", code="SCHEMA_INVALID", rule="chart_svg_output")
        if tag == "style" and element.text and ("@import" in element.text.casefold() or "url(" in element.text.casefold()):
            raise RuntimeContractError("Native Renderer produced an external SVG style dependency", code="SCHEMA_INVALID", rule="chart_svg_output")
        for name, value in element.attrib.items():
            attribute = _local_name(name)
            if any(attribute.casefold().startswith(prefix.casefold()) for prefix in policy.forbidden_attribute_prefixes):
                raise RuntimeContractError("Native Renderer produced an SVG event handler", code="SCHEMA_INVALID", rule="chart_svg_output")
            if attribute in {"href", "src"}:
                parsed = urlparse(value)
                if parsed.scheme or parsed.netloc or value.startswith("//") or value:
                    raise RuntimeContractError("Native Renderer produced an external SVG reference", code="SCHEMA_INVALID", rule="chart_svg_output")


def _local_name(value: str) -> str:
    return value.rsplit("}", 1)[-1]
