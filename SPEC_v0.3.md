# Product Discovery SkillGraph — System / Workflow Spec v0.3 Amendment

> Status: Frozen Amendment after Registry integrity verification.  
> Base: `SPEC_v0.2.md` / Contract `0.2.0` (frozen, preserved byte-for-byte).  
> Current Contract: `0.3.0`.

## 1. Inheritance and normative precedence

This narrow Amendment changes only Report/Chart Artifact Architecture, HTML
Bundle semantics, and Version Lifecycle. All other v0.2 Product, Spec,
Runtime, Workflow, Research, Evidence, Verification, and Human Gate semantics
are inherited. The v0.2 documents remain authoritative for a selected v0.2
Bundle and are not retroactively reinterpreted.

For Contract `0.3.0`, this Amendment supersedes the format-specific parts of
v0.2 sections 23, 24, 29, and 52.1 and the related v0.2 Skill/Template
references. It does not replace their Dataset-first, provenance, profile,
coverage, gap, waiver, or verifier logic.

## 2. Version Registry and closed Bundle resolution

The Registry has exactly one default new-run version: `0.3.0`. The status
vocabulary separates lifecycle from permissions:

| Version | Status | new_run | resume | audit |
|---|---|---:|---:|---:|
| `0.1.0` | `immutable_baseline` | no | no | yes |
| `0.2.0` | `frozen_previous` | no | yes | yes |
| `0.3.0` | `current` | yes | yes | yes |

`new_run` may omit a version and resolves to `0.3.0`. `resume` may not omit a
version; Runtime supplies the persisted Run Snapshot version. It resolves the
complete corresponding Bundle without default-version substitution. `audit`
requires an explicit registered version when it is not otherwise determined.

Every `0.3.0` Workflow, Schema, Skill, Subgraph, Template, Profile, and
Fixture reference resolves inside `contracts/0.3.0/`. Resolver fallback to
the root baseline or `contracts/0.2.0/`, a cross-version `@` reference, URI,
absolute path, backslash path, traversal, symlink escape, or missing asset is
an error. The existing Registry default-deny, read-only v0.1 Research Seed
rules remain separate from Bundle composition and do not permit v0.2 assets
inside a v0.3 Run.

`api_version: "0.2.0"` remains the existing Runtime API wire version. It is
not a Contract Bundle selector; persisted `contract_version` is.

## 3. Report and Chart Contract

### 3.1 Chart Bundle

```text
visualizations/<chart-id>/
  data.json        MUST
  chart-spec.json  MUST
  chart.svg        MUST; canonical rendering
  chart.png        MAY; explicit compatibility/export only
  insight.md       MUST
```

The v0.3 Chart Schema required set is `data_ref`, `chart_spec_ref`, `svg_ref`,
and `insight_ref`; `png_ref` remains declared but is not required. Profile
coverage uses canonical SVG, not PNG presence. A missing SVG fails verification
even when PNG exists.

### 3.2 HTML Report Bundle

`competitor-report.html` is the only final `competitor_report` artifact. The
HTML Report Builder reads Structured Research Artifacts and the Chart Spec to
SVG result; it does not infer facts from SVG or make SVG the source of truth.
It organizes Dataset, Analysis, Evidence, Sources, Citations, Chart Bundles,
SVG Visualizations, Limitations, and Verification Summary.

The report is `bundle-self-contained`: it opens through `file://` without
network or a server and may use only safe relative local asset references
within the same Report Artifact Bundle. No remote asset, CDN, runtime script,
inline script/event handler, React, ECharts, Chart.js, D3, Node.js Runtime,
`file:` URL, traversal, or external rendering service is allowed. External
source citations are passive metadata, never an opening/render dependency.

`competitor-visualization` writes chart bundles and the HTML report contract;
`competitor-verifier` checks the canonical SVG, local report references,
provenance, profile coverage, and static HTML consistency. The verifier does
not treat HTML/SVG as research evidence.

## 4. Decision records

### ADR-20 — Artifact Architecture: HTML final report, canonical SVG

`competitor-report.html` is the final report, canonical SVG is required for
each chart, and PNG is optional compatibility output. This supersedes the
contrary format assumptions in v0.2 only for Contract `0.3.0`; it preserves
the historical v0.2 Bundle unchanged.

### ADR-21 — Renderer implementation is independent and deferred

Artifact Architecture defines what must exist. Renderer implementation decides
how SVG and optional PNG are generated. No renderer Option 1/2/3 is selected,
and this Amendment does not claim a Renderer, HTML Builder, visualization
execution, verifier execution, parity, retry/return, or end-to-end workflow
implementation exists.

## 5. Verification requirements

Static validation must prove independent v0.3 Bundle closure, schema/skill/
subgraph/template coherence, HTML restrictions, optional PNG, canonical SVG,
closed version resolution, v0.2 frozen Bundle integrity, and frozen document
hashes. Contract tests must prove v0.2 new-run rejection and exact v0.2
resume/audit behavior, v0.3 default new-run behavior, and mixed-Bundle
rejection. Full Runtime/E2E claims require later implementation evidence.
