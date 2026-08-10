# Skill: idea-intake

## Purpose

Turn the submitted product idea into the canonical v0.1 Idea Definition artifact without adding unsupported facts.

## Trigger

Run as the first Core Workflow skill when a new idea is submitted.

## Inputs

Use the host-provided idea text and any explicitly supplied user constraints; there is no required upstream artifact.

## Reads

Read only the submitted input carried by the executor request.

## Tasks

Preserve the original idea, separate problem, users, proposed solution, assumptions, unknowns, and non-goals, and assign conservative confidence.

## Required Outputs

Write `artifacts/00-intake/idea-definition.yaml` as an `idea_definition` artifact conforming to `schemas/idea.schema.json#/$defs/idea_definition`.

## Evidence Rules

Do not treat user assertions as externally verified evidence; keep unsupported statements as assumptions or unknowns.

## Completion Criteria

The output is schema-valid, retains the original intent, and contains no invented validation claims.

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
