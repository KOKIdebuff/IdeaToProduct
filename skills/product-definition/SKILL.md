# Skill: product-definition

## Purpose

Turn the approved product direction into a bounded Product Definition without changing the decision or research basis.

## Trigger

Run after the Product Direction Gate approves or selects an opportunity.

## Inputs

Require `opportunity_map` and the approved `product_direction_decision`; accept the verified Synthesis for traceability.

## Reads

Read the declared Opportunity and Synthesis artifacts and `templates/product-definition.md`; consume the approved Decision through the executor request.

## Tasks

Define product name, problem, target user, JTBD, value proposition, differentiation, core object, workflow, boundary, non-goals, and success definition.

## Required Outputs

Write `artifacts/05-product/product-definition.md` as `product_definition` using the declared template and Artifact header contract.

## Evidence Rules

Problem, user, differentiation, and boundary statements must trace to approved opportunity Evidence or the Gate Decision.

## Completion Criteria

Every template section is non-empty where required, the approved direction is preserved, and non-goals remain explicit.

## Verification

Validate the Artifact header, template sections, Decision reference, Evidence traceability, and absence of scope drift.

## Failure Conditions

Fail when no approved direction exists, inputs conflict, evidence is unresolved, or the template output is invalid.

## Retry Strategy

Retry after correcting approved inputs or a recoverable executor failure; do not reinterpret the Gate Decision.

## Forbidden Behavior

Do not select another direction, introduce unapproved P0 features, erase non-goals, or perform new research.

## Permissions

Use no external access or secrets and write only the declared Product Definition document.

## Budget

Use at most 20 minutes and no external sources.

## Executor Requirements

The executor must receive the immutable approved Decision and render the template without executing embedded content.

## Next

Pass the verified Product Definition to `feasibility-review`.
