# Skill: research-verifier

## Purpose

Independently classify every enabled Research section and the overall Research result as PASS, PARTIAL, or FAIL.

## Trigger

Run after all enabled top-level Research branches have terminated.

## Inputs

Require the Research Contract, competitor verification, User Evidence, and Market Landscape; require Technology Landscape when enabled and accept Source Index context.

## Reads

Read only the effective branch and Source Index paths declared in `skill.yaml`, treating disabled optional branches as not applicable.

## Tasks

Check coverage, provenance, source quality, freshness, contradictions, data completeness, and required visualization completeness.

## Required Outputs

Write `artifacts/03-analysis/research-verification.yaml` as `research_verification` with per-section and overall results and structured issues.

## Evidence Rules

Any required Artifact or provenance absence is FAIL; only non-critical unmet checks may produce PARTIAL.

## Completion Criteria

Every enabled section is classified exactly once, disabled sections are recorded, and overall status follows the v0.2 decision rules.

## Verification

Validate all input contracts, issue criticality, enabled-section aggregation, visualization requirements, and Source reference integrity.

## Failure Conditions

Domain gaps produce a normal Verification result; execution fails only for invalid inputs, schema, executor, budget, or security errors.

## Retry Strategy

Do not retry a domain FAIL directly; allow Workflow routing through `research-gap` and verify again after targeted nodes complete.

## Forbidden Behavior

Do not use weighted totals to hide critical failures, accept missing provenance, mutate research, or grant an Evidence Waiver.

## Permissions

Use no external access or secrets and write only the declared Research Verification artifact.

## Budget

Use at most 20 minutes and no external sources.

## Executor Requirements

The executor must be independent from research generation and evaluate explicit, versioned Artifact references deterministically.

## Next

Route FAIL to `research-gap`, PARTIAL to `evidence-waiver`, and PASS to `research-synthesis`.
