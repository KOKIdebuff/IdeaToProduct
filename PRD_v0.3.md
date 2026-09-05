# Product Discovery SkillGraph — PRD v0.3 Amendment

> Status: Frozen Amendment after Registry integrity verification.  
> Predecessor: `PRD_v0.2.md` (frozen, preserved byte-for-byte).  
> Contract target: `0.3.0`.

## 1. Purpose, inheritance, and precedence

This is a narrow Amendment, not a rewrite of PRD v0.2. Except for the Report /
Chart Artifact, HTML Bundle, and Version Lifecycle rules below, every v0.2
Product, Runtime, Workflow, Research, Evidence, Verification, and Human Gate
semantic is inherited unchanged. Absence from this Amendment is not a removal.

For a conflict within the stated scope, this document wins for Contract
`0.3.0` only. `PRD_v0.2.md`, `SPEC_v0.2.md`, and
`V0.2_CHANGE_IMPACT.md` remain the historical authority for an existing v0.2
Run.

## 2. Report and chart artifact architecture

### 2.1 Final report

The final `competitor_report` artifact is
`artifacts/02-research/competitors/competitor-report.html`.
`competitor-report.md` is not a final report artifact in a v0.3 Run.

The HTML report organizes Dataset, Analysis, Evidence, Sources, Citations,
Chart Bundles, SVG Visualizations, Limitations, and Verification Summary. It
is a presentation assembled from Structured Research Artifacts; neither HTML
nor SVG becomes a fact source.

```text
Structured Research Artifacts
  Dataset / Analysis / Evidence / Sources
                         + Chart Spec → SVG
                                       ↓
                            HTML Report Builder
                                       ↓
                         competitor-report.html
```

### 2.2 Chart Bundle

Every required chart bundle contains `data_ref`, `chart_spec_ref`, `svg_ref`,
and `insight_ref`. `svg_ref` identifies the canonical rendering. `png_ref`
remains a valid attribute but is optional and is produced only for an explicit
compatibility or export requirement; it cannot replace SVG.

## 3. bundle-self-contained HTML

`bundle-self-contained` means that `report.html` opens directly offline and
may use safe relative references to canonical SVG, CSS, and static assets
inside the same Report Artifact Bundle. It does not mean a single-file HTML
document.

The report must not require a network connection, CDN, remote script, Web
Server, React, ECharts, Chart.js, D3, or Node.js Runtime. Inline scripts,
event handlers, remote/`file:` assets, and path traversal are prohibited.
Static source citations may be text or links, but cannot be required to open
or render the report.

## 4. Version lifecycle

```yaml
0.3.0:
  status: current
  new_runs_allowed: true
  resume_allowed: true
  audit_allowed: true

0.2.0:
  status: frozen_previous
  new_runs_allowed: false
  resume_allowed: true
  audit_allowed: true
```

New Runs default to `0.3.0`. Resume resolves the contract version recorded by
the persisted Run Snapshot. Therefore an existing v0.2 Run resumes with its
complete `0.2.0` Workflow, Schema, Skill, Subgraph, Template, Profile, and
Fixture Bundle; it is never migrated to or completed with `0.3.0` assets.
Audit is explicit and permitted for both versions. Bundle lookup is closed:
`0.3.0 + 0.2.0` fallback or mixed references are invalid.

## 5. Decisions and scope boundary

**Decision A — Artifact Architecture (approved):** HTML is the final report,
SVG is canonical, and PNG is optional compatibility output.

**Decision B — Renderer Implementation (deferred):** this Amendment does not
choose a renderer Option 1/2/3 and does not implement SVG generation, PNG
generation, SVG/PNG parity, or export fallback. It only defines the artifacts
that a later renderer must produce.

This Amendment supersedes only the Report/Chart format portions of v0.2
FR-08 and FR-13. Scoring, research quality, profile coverage, gaps, waivers,
verification behavior, and all unrelated requirements remain inherited.
