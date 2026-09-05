# Skill: research-gap

## Purpose

Convert Research Verification issues or a request for more research into a bounded, targeted retry plan.

## Trigger

Run after Research FAIL or an Evidence Waiver decision of `REQUEST_MORE_RESEARCH`.

## Inputs

Require `research_verification`; accept the triggering `evidence_waiver_decision` when present.

## Reads

Read `artifacts/03-analysis/research-verification.yaml` and consume the Gate decision through the executor request.

## Tasks

Group issues by responsible Skill, define required actions and reusable artifacts, resolve retry targets, and declare exact invalidation and return behavior.

## Required Outputs

Write `artifacts/03-analysis/research-gap.yaml` as `research_gap` with resolvable retry targets and `return_to: research-verifier`.

## Evidence Rules

Each gap must trace to an existing Verification issue; do not introduce new research claims.

## Completion Criteria

Every actionable issue has a bounded target, required action, invalidation set, reuse plan, and valid return node.

## Verification

Validate issue references, target existence, invalidation safety, absence of unrelated broad retries, and Schema conformance.

## Failure Conditions

Fail when issues are missing, targets are unresolved, a plan exceeds remaining limits, or the output contract is invalid.

## Retry Strategy

Retry this planner only after corrected Verification input; the generated plan controls downstream research retries and must not self-loop.

## Forbidden Behavior

Do not retry every research branch, exceed configured cycles, waive critical gaps, or discard unaffected artifacts.

## Permissions

Use no external access or secrets and write only the declared Research Gap artifact.

## Budget

Use at most 20 minutes and no external sources.

## Executor Requirements

The executor must receive the Effective Workflow so all target and invalidation references can be checked.

## Next

Return the plan to the Workflow loop, then route completed retries back to `research-verifier`.
