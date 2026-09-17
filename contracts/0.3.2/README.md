# Contract Bundle 0.3.2

This directory is a complete staged static Contract Bundle. It is intentionally
not registered, current, resumable, auditable, or selectable for new Runs.
Runtime and Registry continue to select `0.3.0` until a separate promotion task.

It contains one Workflow, 23 JSON Schemas, four Product Profiles, 29 Standard
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
Report publication. The staged Contract includes a distinct Score Publisher,
`INITIAL`/`SCORE_SUCCESSOR`/`VERIFICATION_SUCCESSOR` Report envelopes, and one
multi-competitor `transparent_score_collection` as the Current Score entry.
Each successor requires a newly versioned offline Report Bundle and explicit
base Report compare-and-swap; a failed scoring retry publishes no collection
or Score successor and leaves the initial Report at `NOT_PERFORMED`.

The local Initial Report Publisher may be unit-tested against this Bundle, but
Score and Verification successor Runtime publication is not implemented here.
End-to-end execution still requires downstream Runtime work and a separate
Registry-promotion task; `0.3.2` remains unregistered.
