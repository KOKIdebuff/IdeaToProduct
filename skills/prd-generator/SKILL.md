# Skill: prd-generator

## Purpose

Generate the v0.1 PRD exclusively from approved and verified Discovery artifacts.

## Trigger

Run after the MVP Scope Gate approves the current scope.

## Inputs

Require Synthesis, Product Definition, Feasibility, MVP Scope, and its approved Decision; accept valid Proof and accepted-risk Decisions when applicable.

## Reads

Read only the approved artifact paths and `templates/prd.md` declared in `skill.yaml`; consume Decisions through the executor request.

## Tasks

Render product context, users, requirements, non-goals, constraints, success metrics, risks, evidence, and open questions without changing approved scope.

## Required Outputs

Write `artifacts/07-prd/prd.md` as `prd` using the declared template and Artifact header contract.

## Evidence Rules

Every P0 requirement and factual statement must trace to an approved source Artifact, Decision, or Evidence ID.

## Completion Criteria

All required template sections are present, approved non-goals and conditions are preserved, and open questions remain explicitly unresolved.

## Verification

Validate the Artifact header, template structure, approved-input references, requirement traceability, non-goals, metrics, and open-question wording.

## Failure Conditions

Fail when any required input is unapproved, blocked Proof is unresolved, evidence is missing, or the generated document is malformed.

## Retry Strategy

Retry after approved input correction or executor failure; a consistency failure requires repair or regeneration followed by independent re-verification.

## Forbidden Behavior

Do not add unapproved P0 features, ignore blockers, rewrite unknowns as facts, change direction, or verify your own PRD.

## Permissions

Use no external access or secrets and write only the declared PRD document.

## Budget

Use at most 20 minutes and no external sources.

## Executor Requirements

The generator must be separate from `prd-consistency-verifier` and render untrusted template content without executing it.

## Next

Pass the generated PRD to `prd-consistency-verifier`.
