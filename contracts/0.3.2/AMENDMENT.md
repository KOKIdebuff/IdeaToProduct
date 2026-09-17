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

## Report Successor Contract

The typed `competitor_report` envelope distinguishes `INITIAL`,
`SCORE_SUCCESSOR`, and `VERIFICATION_SUCCESSOR`. The initial Builder writes a
null base, `PENDING` verification, and `NOT_PERFORMED` scoring. A successor
must name its direct base Report in both `base_report_ref` and
`artifact.supersedes` and increment the same Report identity. Every publication
has a new immutable Bundle rooted at `report-bundles/<report-id>@<version>/`;
its `report_root_ref` and `inventory_ref` must identify files under that exact
successor root and differ from the base Bundle refs. Successors preserve the
upstream projection and chart-collection refs but do not reuse predecessor
HTML or inventory files.

The Runtime-owned Score Publisher may replace only the scoring section with a
local `transparent_score_collection` ref. The Competitor Verifier first writes
its Verification Artifact and may then replace only the verification section
with that local ref. Both publishers use current-root compare-and-swap,
idempotent replay for the same base/kind/section ref, append-only history, and
fail closed on a stale base. Projection statuses remain initial projection
state and are never mutated to publish a successor.

Scoring is an all-or-none optional path. When it is absent, `scoring`,
`score_verifier`, and `score_publisher` terminate as `SKIPPED`, and the
Competitor Verifier publishes from the Initial Report. When it is present, the
Verifier waits for the Score Publisher and publishes from the current Score
successor.

If scoring was attempted but retry exhaustion leaves no legal Score, the
independent Score Verifier opens a targeted Research Gap, the optional Score
Publisher terminates `SKIPPED`, no collection or Score successor is published,
and the current Initial Report remains `NOT_PERFORMED`. The Competitor Verifier
may continue from that Initial base; this Bundle does not implement retry
routing in Runtime.

## Transparent Scoring

Each Profile selects one self-contained, five-dimension, equal-weight Rubric.
Dimension scores are integer `1..10`; at least `80%` legal weighted coverage is
required for a `PARTIAL` aggregate, with available weights re-normalized to
`1.0`. An independent Score Verifier checks each Judgment; exhausted retry
opens a targeted Research Gap. Candidate Selection score is not Transparent
Score. These are declarative contracts only and contain no scoring runtime.

Per-competitor `transparent_score` Artifacts remain immutable history. One
Runtime-owned `transparent_score_collection` is the Current Manifest entry for
a ranking scope. It binds the Candidate Ranking, Profile, Rubric and version to
an exact, complete set of per-competitor score refs. The ordered refs follow
final score descending, verified coverage descending, and competitor ID
ascending; equal score and coverage share a competition rank. The collection
does not duplicate score values, coverage, rank, or tie state.

## Superseded Format Clauses

For Bundle `0.3.2` only, this amendment supersedes the report/chart format
portions of PRD v0.2 FR-08 and FR-13 and SPEC v0.2 sections 23, 24, 29, and
52.1. The frozen PRD and SPEC documents themselves are not modified.
