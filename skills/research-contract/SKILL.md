# Skill: research-contract

## Purpose

Compose the Idea Definition, selected Product Profile, and host limits into the project-specific v0.1 Research Contract.

## Trigger

Run after `idea-intake` and before the Research Scope Gate.

## Inputs

Require the current `idea_definition` and active `product_profile` together with host permission and budget ceilings.

## Reads

Read `artifacts/00-intake/idea-definition.yaml` and the selected contract under `profiles/`.

## Tasks

Resolve enabled research branches, questions, evidence thresholds, required visualizations, approved-adjustment placeholders, run policy, and stop conditions.

## Required Outputs

Write `artifacts/01-contract/research-contract.yaml` as a `research_contract` artifact conforming to `schemas/research.schema.json#/$defs/research_contract`.

## Evidence Rules

Profile defaults and user-requested adjustments are contract inputs, not research evidence; record every proposed relaxation for Gate review.

## Completion Criteria

The contract is schema-valid, references exactly one v0.1 Profile, stays within host limits, and makes all branch and visualization requirements explicit.

## Verification

Validate profile/version references, thresholds, adjustment records, stop conditions, and host-limit containment.

## Failure Conditions

Fail when the Idea Definition or Profile is missing, incompatible, or requests permissions or budgets beyond the host ceiling.

## Retry Strategy

Retry only after correcting the input contract or resolving a recoverable executor failure.

## Forbidden Behavior

Do not silently relax Profile requirements, approve the Research Scope Gate, or start research.

## Permissions

Use no external access and write only the declared Research Contract path.

## Budget

Use at most 20 minutes and no external sources.

## Executor Requirements

The executor must receive the selected Profile and effective host constraints as trusted configuration.

## Next

Submit the Research Contract to the `research-scope` Human Gate.
