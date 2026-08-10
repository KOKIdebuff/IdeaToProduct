# Skill: feasibility-review

## Purpose

Assess product feasibility across data, API, platform, architecture, security, performance, operations, and implementation cost.

## Trigger

Run after Product Definition and re-run after a valid external Proof Result invalidates the prior review.

## Inputs

Require `product_definition`; accept Synthesis, Technology Landscape, and a validated `proof_result` during re-review.

## Reads

Read the declared Product, Research, Technology, optional Proof Result, and `templates/feasibility.md` paths.

## Tasks

Evaluate each required dimension, classify blockers and critical assumptions, determine proof requirements, and emit one feasibility result.

## Required Outputs

Write `artifacts/06-feasibility/feasibility.md` as `feasibility_review` using the declared template and Artifact header contract.

## Evidence Rules

Every blocker, critical assumption, and feasibility conclusion must trace to approved artifacts or validated Proof evidence.

## Completion Criteria

All dimensions are addressed and result is exactly FEASIBLE, CONDITIONALLY_FEASIBLE, BLOCKED, or NOT_FEASIBLE.

## Verification

Validate the Artifact header, template sections, result enum, blocker severity, Proof references, and Evidence traceability.

## Failure Conditions

Fail when required inputs are absent, a supplied Proof Result is invalid, evidence is insufficient for classification, or output is malformed.

## Retry Strategy

Retry after corrected inputs or executor failure; BLOCKED routes to Proof planning and valid Proof submission triggers a new review.

## Forbidden Behavior

Do not execute a proof, waive critical blockers, claim feasibility without evidence, or enter MVP Scope after a failed required Proof.

## Permissions

Use no external access or secrets and write only the declared Feasibility document.

## Budget

Use at most 20 minutes and no external sources.

## Executor Requirements

The executor must distinguish initial review from Proof-based re-review and consume only schema-valid external results.

## Next

Route BLOCKED to `proof-planner`, feasible results to `mvp-scope`, and terminal failure to Build Readiness.
