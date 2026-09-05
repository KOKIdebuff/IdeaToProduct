# Contract Amendment 0.3.0 — Report and Chart Artifact Architecture

## Status

Approved Contract Amendment. This document changes only the report and chart
artifact architecture for Contract Bundle `0.3.0`. All behavior not explicitly
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

Deferred. This amendment neither selects a renderer nor implements SVG or PNG
generation, renderer fallback, SVG/PNG parity, or any Renderer Option 1/2/3.

## Superseded Format Clauses

For Bundle `0.3.0` only, this amendment supersedes the report/chart format
portions of PRD v0.2 FR-08 and FR-13 and SPEC v0.2 sections 23, 24, 29, and
52.1. The frozen PRD and SPEC documents themselves are not modified.
