# Skill: idea-intake

## Purpose

Assess the submitted idea, adaptively shape missing product context, and produce the canonical v0.2 Idea Definition without adding unsupported facts.

## Trigger

Run as the first Core Workflow skill when a new idea is submitted.

## Inputs

Use the host-provided idea text and any explicitly supplied user constraints; there is no required upstream artifact.

## Reads

Read only the submitted input carried by the executor request.

## Tasks

Evaluate clarity, select the highest-value gap, ask at most one main question per round, and preserve Problem, User, Scenario, Value, Mechanism, assumptions, unknowns, research seeds, and conservative confidence.

## Interaction Model

When the Idea is not yet researchable, dynamically choose clarification, controlled brainstorming, adaptive product discovery interview, or assumption challenge. Methods may repeat, switch, or be skipped. Offer two to four choices and a recommendation only when honest candidates exist, always allow freeform input, stop as soon as completion criteria are met, and never exceed eight rounds.

## Required Outputs

Write `artifacts/00-intake/idea-definition.yaml` as an `idea_definition` artifact conforming to `schemas/idea.schema.json#/$defs/idea_definition`.

## Evidence Rules

Do not treat user assertions as externally verified evidence; keep unsupported statements as assumptions or unknowns.

## Completion Criteria

The output is schema-valid, retains the original intent, contains no invented validation claims, and ends as `SUFFICIENT`, `PARTIAL_RESEARCHABLE`, or `INSUFFICIENT_PRODUCT_CONTEXT` without a ninth question.

## Verification

Validate the output contract and confirm every material input statement is represented or deliberately classified as out of scope.

## Failure Conditions

Fail with a structured input or schema error when the submitted idea cannot be represented without guessing.

## Retry Strategy

Retry only after corrected input or a recoverable executor failure; do not retry by inventing missing detail.

## Forbidden Behavior

Do not perform research, select a product direction, or silently convert assumptions into facts.

## Permissions

Use no external access and write only the declared Idea Definition path.

## Budget

Use at most 20 minutes and no external sources.

## Executor Requirements

The executor must preserve user-provided wording, enforce workspace containment, and return a schema-valid artifact reference.

## Next

Pass the verified Idea Definition to `research-contract`.
