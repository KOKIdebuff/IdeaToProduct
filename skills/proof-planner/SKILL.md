# Skill: proof-planner

## Purpose

Convert feasibility blockers into a bounded external Proof plan with explicit pass, fail, and expected-artifact criteria.

## Trigger

Run only when `feasibility-review` returns BLOCKED with required Proof items.

## Inputs

Require the current `feasibility_review` artifact and accept Product Definition context.

## Reads

Read the declared Feasibility and Product Definition paths.

## Tasks

Define the proof question, hypothesis, experiment steps, inputs, pass criteria, fail criteria, and expected artifacts.

## Required Outputs

Write `artifacts/06-feasibility/proof-plan.yaml` as `proof_plan` conforming to the declared Research Schema definition.

## Evidence Rules

Every planned Proof must trace to a named blocker or critical assumption in Feasibility.

## Completion Criteria

Each required Proof has unambiguous inputs, bounded steps, pass and fail criteria, and expected evidence artifacts.

## Verification

Validate blocker references, criteria completeness, non-overlapping outcomes, safety boundaries, and Schema conformance.

## Failure Conditions

Fail when no BLOCKED feasibility input exists, proof criteria are not testable, expected artifacts are undefined, or output is invalid.

## Retry Strategy

Retry only after correcting the Feasibility input or a recoverable executor failure.

## Forbidden Behavior

Do not execute commands, write a Spike, modify a codebase, submit a Proof Result, or claim that a planned experiment passed.

## Permissions

Use no external access or secrets and write only the declared Proof Plan artifact.

## Budget

Use at most 20 minutes and no external sources.

## Executor Requirements

The executor is planning-only and must not invoke coding, deployment, shell, or external mutation capabilities.

## Next

Wait for the external `proof_result` node, then return a valid submission to `feasibility-review`.
