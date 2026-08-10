# Contract Bundle 0.2.0

This directory is the complete static Contract Bundle selected by
`contracts/registry.yaml` for new runs.

It contains one Workflow, 23 JSON Schemas, four Product Profiles, 23 Standard
Skill Contracts, one Competitor Subgraph, five Markdown Templates, and
Bundle-local positive and negative fixtures.

This bundle is declarative only. It does not contain an Orchestrator, Runtime,
Executor implementation, generated business artifacts, or live research data.
All Contract references resolve within this directory. Cross-version input is
accepted only through the Registry's read-only, default-deny Compatibility
Matrix.
