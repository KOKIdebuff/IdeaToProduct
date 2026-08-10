# Skill: opportunity-mapping

## Purpose

Map verified research into a small, evidence-linked set of product opportunities and one transparent recommendation.

## Trigger

Run after `research-synthesis` is verified.

## Inputs

Require the current `research_synthesis` artifact.

## Reads

Read `artifacts/03-analysis/research-synthesis.md` and no unapproved research input.

## Tasks

Define at most four opportunities, score the specified dimensions, preserve Evidence references, document methodology, and recommend one direction with rationale.

## Required Outputs

Write `opportunities.yaml` as `opportunity_map` and `opportunity-methodology.yaml` as `opportunity_methodology` under the declared Research Schema definitions.

## Evidence Rules

Every opportunity and material score must trace to the verified Synthesis; uncertainty must reduce confidence rather than be filled.

## Completion Criteria

There are no more than four schema-valid opportunities, one recommendation is identified, and the methodology makes every score reproducible.

## Verification

Validate Evidence references, score dimensions, methodology coverage, recommendation membership, and deterministic ordering.

## Failure Conditions

Fail when Synthesis is missing or unverified, a score lacks methodology, evidence is unresolved, or either output is schema-invalid.

## Retry Strategy

Retry after correcting Synthesis or a recoverable executor failure; evidence insufficiency returns to the Research loop.

## Forbidden Behavior

Do not conduct new research, exceed four directions, hide low feasibility, or choose a direction without traceable rationale.

## Permissions

Use no external access or secrets and write only the two declared Opportunity artifacts.

## Budget

Use at most 20 minutes and no external sources.

## Executor Requirements

The executor must use deterministic scoring from explicit input versions and keep methodology separate from recommendations.

## Next

Present the opportunity set at the Product Direction Gate.
