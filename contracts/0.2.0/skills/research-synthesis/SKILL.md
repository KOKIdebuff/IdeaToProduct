# Skill: research-synthesis

## Purpose

Synthesize verified Research into validated, partially validated, invalidated, unknown, contradictory, opportunity, and risk sections.

## Trigger

Run after Research PASS or after non-critical PARTIAL has an approved Evidence Waiver.

## Inputs

Require Research Verification and all enabled Research outputs; accept approved Waiver and accepted-risk Decisions when applicable.

## Reads

Read the declared Research outputs, Verification artifact, and `templates/synthesis.md`; consume approved Decisions through the executor request.

## Tasks

Reconcile claims and contradictions, preserve accepted-risk boundaries, classify uncertainty, and summarize opportunities without defining MVP features.

## Required Outputs

Write `artifacts/03-analysis/research-synthesis.md` as `research_synthesis` using the declared template and Artifact header contract.

## Evidence Rules

Every material synthesis statement must trace to verified Evidence or an explicit accepted-risk Decision.

## Completion Criteria

The template is complete, all enabled research is represented, contradictions and unknowns remain visible, and no unsupported key fact is added.

## Verification

Validate the Artifact header, template sections, Verification/Waiver eligibility, Evidence references, and absence of unsupported MVP scope.

## Failure Conditions

Fail when required research is not verified or waived, provenance is missing, contradictions are hidden, or template output is invalid.

## Retry Strategy

Retry only after input correction or a recoverable executor failure; unresolved evidence returns through the Research Gap loop.

## Forbidden Behavior

Do not create new unsupported facts, add MVP features, conceal unknowns, or reinterpret a critical failure as accepted risk.

## Permissions

Use no external access or secrets and write only the declared Synthesis document.

## Budget

Use at most 20 minutes and no external sources.

## Executor Requirements

The executor must receive immutable approved Artifact versions and render the template without executing embedded content.

## Next

Pass the verified Synthesis to `opportunity-mapping`.
