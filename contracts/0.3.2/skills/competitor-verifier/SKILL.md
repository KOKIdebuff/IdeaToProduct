# Skill: competitor-verifier

## Purpose

Independently verify the complete Competitor Research Subgraph and produce its PASS, PARTIAL, or FAIL result.

## Trigger

Run after the competitor report and every required internal artifact are complete.

## Inputs

Require the Research Contract and all candidate, ranking, Deep Dive, dataset, analysis, chart, and current Report outputs; accept Source Index and completed scoring collection context.

## Reads

Read only the complete set of paths declared in `skill.yaml`.

## Tasks

Check coverage, selection traceability, provenance, freshness, data completeness, required visualizations, contradictions, optional score collection identity, and static HTML report consistency. Produce the typed Verification first, then ask the Runtime-owned Publisher to create a verification-only Report successor from the current base.

## Required Outputs

Write `competitor-verification.yaml` as `competitor_verification`; every gap must include internal `retry_targets` and `return_to: competitor_verifier`. Then write one `competitor_report` with `publication_kind: VERIFICATION_SUCCESSOR` whose verification ref points to that Artifact.

## Evidence Rules

Verify Source and Evidence references without creating new research claims or accepting missing critical provenance.

## Completion Criteria

Emit exactly one schema-valid PASS, PARTIAL, or FAIL result and one verification-only Report successor after all required nodes and the optional scoring path have terminated. Disabled scoring skips all three optional nodes; retry exhaustion opens a targeted Research Gap, skips Score Publisher, leaves the current Initial Report at `NOT_PERFORMED`, and still allows verification from that Initial base.

## Verification

Validate every referenced artifact and retry target, enforce offline HTML identity/structure and the no-remote/no-script policy, ensure critical failures cannot be averaged away, confirm `return_to` resolves to this node, and verify that the successor preserves scoring and every non-verification Report field.

## Failure Conditions

Domain insufficiency produces a Verification result, not an execution error; fail execution only for invalid inputs, schema errors, budget, executor, or security failures.

## Retry Strategy

Do not retry a domain FAIL directly; return precise targets to the subgraph scheduler and verify again after those targets complete. Replay an identical successor publication idempotently and reject a stale current Report base.

## Forbidden Behavior

Do not modify research artifacts, scoring, or unrelated Report fields; do not reuse predecessor HTML Bundle refs, waive gaps, replace critical failures with PARTIAL, use last-writer-wins, or write top-level readiness.

## Permissions

Use no external access or secrets and write only the declared competitor verification, Report successor, and versioned `report-bundles/` paths through the Runtime-owned Publisher.

## Budget

Use at most 20 minutes and no external sources.

## Executor Requirements

The executor must be independent from the generating attempts and provide deterministic validation over explicit Artifact versions.

## Next

Return the verified subgraph status, Verification successor, and output references to the top-level `competitor` node.
