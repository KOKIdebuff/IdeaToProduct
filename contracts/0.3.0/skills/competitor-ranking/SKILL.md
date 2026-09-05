# Skill: competitor-ranking

## Purpose

Select the competitor set for Deep Dive using a transparent, reproducible methodology.

## Trigger

Run after `competitor-discovery` produces a valid candidate set.

## Inputs

Require `competitor_candidates` and `research_contract`; accept Source Index context for provenance checks.

## Reads

Read the candidate set, Research Contract, and current Source Index paths declared in `skill.yaml`.

## Tasks

Score relevance against approved questions, select the bounded Deep Dive set, and preserve reasons for every exclusion.

## Required Outputs

Write `artifacts/02-research/competitors/ranking.yaml` as `competitor_ranking` with selection methodology and excluded-candidate reasons.

## Evidence Rules

Use only candidate facts supported by Source IDs and keep unknown values explicit.

## Completion Criteria

The ranking is schema-valid, deterministic for identical inputs, and explains selected and excluded candidates.

## Verification

Validate input coverage, stable ordering, methodology presence, exclusion reasons, and provenance references.

## Failure Conditions

Fail on missing candidates, invalid evidence references, schema failure, or an inability to select without unsupported assumptions.

## Retry Strategy

Retry only after corrected upstream artifacts or a recoverable executor failure; evidence gaps return to discovery through the subgraph verifier.

## Forbidden Behavior

Do not perform new external research, hide excluded candidates, or use an undocumented weighted score.

## Permissions

Use no external access, no secrets, and write only the declared ranking artifact.

## Budget

Use at most 20 minutes and no external sources.

## Executor Requirements

The executor must produce deterministic analysis from explicit Artifact references.

## Next

Fan out the selected competitors to `competitor-deep-dive`.
