# Skill: prd-consistency-verifier

## Purpose

Independently verify that the PRD is consistent with approved Discovery, Feasibility, Scope, risks, metrics, and open questions.

## Trigger

Run immediately after `prd-generator` produces a PRD.

## Inputs

Require the PRD, Synthesis, Product Definition, Feasibility, and MVP Scope; accept Proof and accepted-risk context when applicable.

## Reads

Read only the PRD and approved upstream paths declared in `skill.yaml`.

## Tasks

Detect unapproved P0 features, reintroduced non-goals, direction drift, ignored blockers, missing metrics, and unknowns presented as facts.

## Required Outputs

Write `prd-consistency-verification.yaml` as `prd_consistency_verification` with an independent result and structured issues.

## Evidence Rules

Every consistency check must cite the PRD location and the controlling approved Artifact, Decision, or Evidence reference.

## Completion Criteria

Emit one schema-valid verification result covering every required guardrail and all detected inconsistencies.

## Verification

Validate issue references, guardrail coverage, independence from generation, result aggregation, and output Schema conformance.

## Failure Conditions

Domain inconsistency produces `PRD_INCONSISTENT_WITH_APPROVED_DISCOVERY`; execution failure is reserved for invalid inputs, schema, executor, budget, or security errors.

## Retry Strategy

Do not waive or auto-retry inconsistency; repair approved inputs or regenerate the PRD, then run this verifier again.

## Forbidden Behavior

Do not edit the PRD, accept Gate overrides, conceal drift, or write readiness status.

## Permissions

Use no external access or secrets and write only the declared PRD Consistency Verification artifact.

## Budget

Use at most 20 minutes and no external sources.

## Executor Requirements

The verifier must be independent from the PRD generating attempt and evaluate immutable input versions.

## Next

Pass the result to `build-readiness-verifier`; on FAIL, require repair and re-verification.
