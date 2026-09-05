# Skill: build-readiness-verifier

## Purpose

Compute the sole authoritative v0.2 Build Readiness result from all effective required checks and accepted-risk decisions.

## Trigger

Run after PRD Consistency completes and on each configured terminal blocker event.

## Inputs

Require the Effective Workflow, Research Verification, Product Definition, Feasibility, MVP Scope, PRD, and PRD Consistency result; accept Waiver, Proof, and accepted-risk Decisions.

## Reads

Read only the Workflow and final Artifact paths declared in `skill.yaml`; consume approved Decisions and required Artifact status through the executor request.

## Tasks

Evaluate required checks, critical blockers, accepted non-critical risks, Proof outcomes, PRD consistency, and required Artifact completeness.

## Required Outputs

Write `artifacts/07-prd/readiness-result.yaml` as `readiness_result` with READY_FOR_BUILD, READY_WITH_ACCEPTED_RISKS, or NOT_READY.

## Evidence Rules

Every passed check, accepted risk, and blocker must trace to a current Artifact, Decision, Proof Result, or Verification issue.

## Completion Criteria

Exactly one schema-valid readiness result exists for the evaluated state and its status follows all v0.2 critical and waiver rules.

## Verification

Validate current Artifact versions, required-node applicability, Decision references, Proof outcomes, consistency status, and three-state aggregation.

## Failure Conditions

Product blockers produce NOT_READY rather than execution failure; execution fails only when inputs cannot be validated or persisted safely.

## Retry Strategy

Re-evaluate after an approved upstream change; do not retry by weakening gates, evidence, Proof, or required Artifact rules.

## Forbidden Behavior

Do not modify upstream artifacts, accept critical waivers, emit a fourth status, or allow any other node to write readiness.

## Permissions

Use no external access or secrets and write only the declared Readiness Result artifact.

## Budget

Use at most 20 minutes and no external sources.

## Executor Requirements

The verifier must receive a consistent snapshot of effective Workflow state and immutable final Artifact references.

## Next

Publish the result as the terminal Build Readiness state for the current run.
