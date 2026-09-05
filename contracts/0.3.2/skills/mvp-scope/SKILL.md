# Skill: mvp-scope

## Purpose

Define a feasible first phase with explicit must-have, should-have, later, non-goal, metric, and exit-criterion boundaries.

## Trigger

Run after Feasibility is FEASIBLE or CONDITIONALLY_FEASIBLE.

## Inputs

Require `product_definition` and `feasibility_review`; accept the approved Product Direction Decision for traceability.

## Reads

Read the declared Product Definition and Feasibility paths and consume the approved Decision through the executor request.

## Tasks

Choose the smallest coherent phase, separate deferred work, preserve blockers and conditions, define success metrics, and make non-goals explicit.

## Required Outputs

Write `artifacts/05-product/mvp-scope.yaml` as `mvp_scope` conforming to the declared Research Schema definition.

## Evidence Rules

Every must-have must trace to approved product value or a feasibility constraint; speculative additions belong in later or unknown.

## Completion Criteria

The scope is schema-valid, contains at least one non-goal, respects feasibility conditions, and has measurable exit criteria.

## Verification

Validate scope classification, non-goal presence, traceability, condition preservation, metrics, and absence of blocked features.

## Failure Conditions

Fail when Feasibility is not eligible, Product Definition is missing, scope cannot be bounded, or output is schema-invalid.

## Retry Strategy

Retry after correcting approved inputs or a recoverable executor failure; a scope change after Gate requires downstream invalidation.

## Forbidden Behavior

Do not include failed Proof-dependent work, reintroduce Product non-goals, hide feasibility conditions, or approve the Scope Gate.

## Permissions

Use no external access or secrets and write only the declared MVP Scope artifact.

## Budget

Use at most 20 minutes and no external sources.

## Executor Requirements

The executor must preserve approved boundaries and produce deterministic classification from explicit Artifact versions.

## Next

Present the scope to the `mvp-scope` Human Gate.
