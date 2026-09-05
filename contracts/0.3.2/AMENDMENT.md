# Contract Amendment 0.3.2 — Report and Chart Artifact Architecture

## Status

Approved Contract Amendment. This document changes only the report and chart
artifact architecture for Contract Bundle `0.3.2`. All behavior not explicitly
changed here inherits Contract Bundle `0.2.0`.

## Decision A — Artifact Architecture

The report artifact bundle root is `artifacts/02-research/competitors/`.

```text
competitor-report.html                 MUST; final competitor_report artifact
visualizations/<chart-id>/data.json    MUST
visualizations/<chart-id>/chart-spec.json MUST
visualizations/<chart-id>/chart.svg    MUST; canonical rendering
visualizations/<chart-id>/chart.png    MAY; compatibility rendering
visualizations/<chart-id>/insight.md   MUST
```

`competitor-report.html` is `bundle-self-contained`: it must open offline
through `file://` and may use only safe relative references to static assets
inside the same report artifact bundle. It must not depend on a network
resource, CDN, remote script, runtime JavaScript, web server, React, ECharts,
Chart.js, D3, or Node.js Runtime. Static source citations may be text or links
but cannot be a report-opening or rendering dependency. The default report
representation references the canonical SVG; a future renderer may choose to
inline that same SVG.

`png_ref` is optional and cannot satisfy or replace the required `svg_ref`.
All Profile visualization coverage, evidence, insight, Research Gap/Waiver,
and verifier semantics are inherited unchanged.

## Decision B — Renderer Implementation

The selected Contract is Runtime-owned Native SVG-first rendering over a
closed `matrix | scatter | bar | line | distribution` Template Registry. SVG
is canonical and has no cross-renderer fallback. PNG is explicit optional
compatibility output; a PNG failure after valid SVG is disclosed `PARTIAL`.
This Bundle defines the Contract but does not implement a Renderer.

## Fact Provenance and Citation

Kernel-owned state-version Fact bindings are materialized by the future T18
step into an immutable typed `report_projection`. Required visible facts must
close through Claim → Evidence → Source. The HTML Builder consumes the
Projection and cannot infer facts or Citation scope from SVG, HTML, URL, or
unverified free text.

## Report Pipeline Separation

Bundle `0.3.2` replaces the combined visualization producer with three
ordered, single-purpose nodes:

```text
fact_provenance → competitor-chart-rendering
                → report-publication-projection
                → competitor-report-builder
```

`competitor-chart-rendering` produces one typed `chart_bundle_collection`.
Every member retains its canonical SVG, explicit Claim/Evidence references,
and local asset refs. `report-publication-projection` combines only the
verified base Projection and that collection into an immutable Builder-facing
Projection; it does not inspect SVG or create facts. `competitor-report-builder`
publishes the HTML Bundle through the Runtime-owned single writer using an
explicit base Report reference, append-only version directories, and an atomic
current Report pointer. A stale base must fail rather than overwrite.

## Transparent Scoring

Each Profile selects one self-contained, five-dimension, equal-weight Rubric.
Dimension scores are integer `1..10`; at least `80%` legal weighted coverage is
required for a `PARTIAL` aggregate, with available weights re-normalized to
`1.0`. An independent Score Verifier checks each Judgment; exhausted retry
opens a targeted Research Gap. Candidate Selection score is not Transparent
Score. These are declarative contracts only and contain no scoring runtime.

## Superseded Format Clauses

For Bundle `0.3.2` only, this amendment supersedes the report/chart format
portions of PRD v0.2 FR-08 and FR-13 and SPEC v0.2 sections 23, 24, 29, and
52.1. The frozen PRD and SPEC documents themselves are not modified.
