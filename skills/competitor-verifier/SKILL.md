# Skill: competitor-verifier

## Purpose

Independently verify the complete Competitor Research Subgraph and produce its PASS, PARTIAL, or FAIL result.

## Trigger

Run after the competitor report and every required internal artifact are complete.

## Inputs

Require the Research Contract and all candidate, ranking, Deep Dive, dataset, analysis, chart, and report outputs; accept Source Index context.

## Reads

Read only the complete set of paths declared in `skill.yaml`.

## Tasks

Check coverage, selection traceability, provenance, freshness, data completeness, required visualizations, contradictions, and report consistency.

## Required Outputs

Write `competitor-verification.yaml` as `competitor_verification`; every gap must include internal `retry_targets` and `return_to: competitor_verifier`.

## Evidence Rules

Verify Source and Evidence references without creating new research claims or accepting missing critical provenance.

## Completion Criteria

Emit exactly one schema-valid PASS, PARTIAL, or FAIL result after all required internal nodes have terminated.

## Verification

Validate every referenced artifact and retry target, ensure critical failures cannot be averaged away, and confirm `return_to` resolves to this node.

## Failure Conditions

Domain insufficiency produces a Verification result, not an execution error; fail execution only for invalid inputs, schema errors, budget, executor, or security failures.

## Retry Strategy

Do not retry a domain FAIL directly; return precise targets to the subgraph scheduler and verify again after those targets complete.

## Forbidden Behavior

Do not modify research artifacts, waive gaps, replace critical failures with PARTIAL, or write top-level readiness.

## Permissions

Use no external access or secrets and write only the declared competitor verification artifact.

## Budget

Use at most 20 minutes and no external sources.

## Executor Requirements

The executor must be independent from the generating attempts and provide deterministic validation over explicit Artifact versions.

## Next

Return the verified subgraph status and output references to the top-level `competitor` node.
