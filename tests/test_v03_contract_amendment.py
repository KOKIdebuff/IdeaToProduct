from __future__ import annotations

from scripts.contract_bundles import load_bundle_context, load_version_registry, resolve_contract_bundle
from scripts.validate_contracts import (
    ROOT,
    build_repository_catalog,
    load_document,
    load_schemas,
    template_contract_diagnostics,
    validate_instance,
)


def _rules(diagnostics):
    return {item.rule for item in diagnostics}


def _v03_context():
    registry = load_version_registry()
    bundle = resolve_contract_bundle("0.3.0", operation="new_run", registry=registry)
    return registry, load_bundle_context(bundle)


def test_v03_chart_bundle_requires_canonical_svg_but_not_png():
    _, context = _v03_context()
    schemas, schema_registry = load_schemas(context.schema_dir)
    svg_only = load_document(context.bundle.root / "fixtures/valid/chart-bundle-svg-only.yaml")
    with_png = load_document(context.bundle.root / "fixtures/valid/chart-bundle.yaml")
    missing_svg = load_document(context.bundle.root / "fixtures/invalid/chart-bundle-missing-svg.yaml")

    assert validate_instance(svg_only, "chart.schema.json", "svg-only.yaml", schemas, schema_registry) == []
    assert validate_instance(with_png, "chart.schema.json", "with-png.yaml", schemas, schema_registry) == []
    assert "required" in _rules(validate_instance(missing_svg, "chart.schema.json", "missing-svg.yaml", schemas, schema_registry))

    required = set(schemas["chart.schema.json"]["$defs"]["chart_bundle"]["allOf"][1]["required"])
    assert {"data_ref", "chart_spec_ref", "svg_ref", "insight_ref"} <= required
    assert "png_ref" not in required
    assert "png_ref" in schemas["chart.schema.json"]["$defs"]["chart_bundle"]["allOf"][1]["properties"]


def test_v03_competitor_report_template_is_static_offline_html():
    _, context = _v03_context()
    source = "templates/competitor-report.html"
    text = (context.template_dir / "competitor-report.html").read_text(encoding="utf-8")

    assert template_contract_diagnostics(text, source, "competitor_report", contract_version="0.3.0") == []

    remote = text.replace("</head>", '<link rel="stylesheet" href="https://cdn.example.invalid/report.css">\n</head>')
    scripted = text.replace("</head>", "<script>window.alert('no')</script>\n</head>")
    evented = text.replace("</head>", '<div onclick="window.alert(\'no\')"></div>\n</head>')
    escaping = text.replace("</head>", '<img src="../outside.svg" alt="invalid">\n</head>')
    local_css = text.replace("</head>", '<link rel="stylesheet" href="assets/report.css">\n</head>')
    citation = text.replace("</main>", '<a href="https://source.example.invalid/report">Source citation</a>\n</main>')
    assert "static_html_asset" in _rules(template_contract_diagnostics(remote, source, "competitor_report", contract_version="0.3.0"))
    assert "static_html" in _rules(template_contract_diagnostics(scripted, source, "competitor_report", contract_version="0.3.0"))
    assert "static_html" in _rules(template_contract_diagnostics(evented, source, "competitor_report", contract_version="0.3.0"))
    assert "static_html_asset" in _rules(template_contract_diagnostics(escaping, source, "competitor_report", contract_version="0.3.0"))
    assert template_contract_diagnostics(local_css, source, "competitor_report", contract_version="0.3.0") == []
    assert template_contract_diagnostics(citation, source, "competitor_report", contract_version="0.3.0") == []

    required_sections = {
        "normalized-dataset",
        "analysis",
        "evidence",
        "sources",
        "citations",
        "required-visualizations",
        "svg-visualizations",
        "limitations-and-unknowns",
        "verification-summary",
    }
    for section_id in required_sections:
        assert f'id="{section_id}"' in text


def test_v03_report_contract_uses_html_and_preserves_competitor_subgraph_topology():
    _, context = _v03_context()
    visualization = load_document(context.skill_dir / "competitor-visualization/skill.yaml")
    verifier = load_document(context.skill_dir / "competitor-verifier/skill.yaml")
    synthesis = load_document(context.skill_dir / "research-synthesis/skill.yaml")
    subgraph = load_document(context.subgraph_dir / "competitor-research.yaml")

    report_path = "artifacts/02-research/competitors/competitor-report.html"
    assert "templates/competitor-report.html" in visualization["reads"]
    assert report_path in visualization["writes"]
    assert report_path in verifier["reads"]
    assert report_path in synthesis["reads"]
    assert all("competitor-report.md" not in value for document in (visualization, verifier, synthesis) for value in document.get("reads", []) + document.get("writes", []))

    nodes = subgraph["nodes"]
    assert nodes["visualization"]["depends_on"] == [
        "feature_analysis",
        "traction_analysis",
        "review_analysis",
        "pricing_analysis",
    ]
    assert nodes["competitor_verifier"]["depends_on"] == ["visualization"]
    assert nodes["visualization"]["skill"] == "competitor-visualization"
    assert nodes["competitor_verifier"]["skill"] == "competitor-verifier"

    catalog = build_repository_catalog(context.bundle.root)
    assert "templates/competitor-report.html" in catalog.template_paths
    assert "templates/competitor-report.md" not in catalog.template_paths


def test_v03_amendment_defers_renderer_decision_b():
    amendment = (ROOT / "contracts/0.3.0/AMENDMENT.md").read_text(encoding="utf-8")
    assert "Decision A — Artifact Architecture" in amendment
    assert "Decision B — Renderer Implementation" in amendment
    assert "neither selects a renderer nor implements SVG or PNG" in amendment
