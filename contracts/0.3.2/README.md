# Contract Bundle 0.3.2

This directory is a complete staged static Contract Bundle. It is intentionally
not registered, current, resumable, auditable, or selectable for new Runs.
Runtime and Registry continue to select `0.3.0` until a separate promotion task.

It contains one Workflow, 23 JSON Schemas, four Product Profiles, 26 Standard
Skill Contracts, one Competitor Subgraph, five Templates (four Markdown and
one HTML), four Profile Rubrics, one closed Native Chart Template Registry,
and Bundle-local positive and negative fixtures.

This bundle is declarative only. It does not contain an Orchestrator, Runtime,
Executor implementation, generated business artifacts, or live research data.
All Contract references resolve within this directory. Cross-version input is
not evaluated while staged; no Registry fallback may assemble this Bundle.
The Bundle's `competitor-report.html` Template is
`bundle-self-contained`: a produced report may use safe relative assets inside
its own Report Artifact Bundle, but never network, CDN, a web server, or a
JavaScript/chart runtime.

The Bundle declares Hybrid Fact Provenance/typed Report Projection,
Fact-Level Citation, equal-weight Profile Rubrics, independent score
verification, Native SVG-first rendering, and optional PNG `PARTIAL` export.
It separates chart rendering, post-chart publication projection, and immutable
Report publication. The local Runtime Publisher may be unit-tested against this
Bundle, while end-to-end execution still requires the separate T17 chart
producer and a future Registry-promotion task.
