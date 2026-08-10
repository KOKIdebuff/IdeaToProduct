# Skill: competitor-normalizer

## Purpose

Normalize verified competitor Deep Dives into one renderer-independent dataset with consistent dimensions and missing-value semantics.

## Trigger

Run after all required `competitor-deep-dive` fan-out members finish.

## Inputs

Require the current `competitor_ranking` and the complete `competitor_deep_dive` collection.

## Reads

Read the ranking artifact and Deep Dive directory declared in `skill.yaml`.

## Tasks

Align competitor identifiers, normalize comparable metrics, retain raw provenance, and represent unavailable values explicitly.

## Required Outputs

Write `artifacts/02-research/competitors/competitor-dataset.json` as `competitor_dataset`.

## Evidence Rules

Preserve Source IDs and observation times from upstream artifacts; derived values must identify their method.

## Completion Criteria

Every selected competitor is represented once, dimensions are consistent, and no missing value is replaced with a fabricated average.

## Verification

Validate schema conformance, identifier uniqueness, selected-set coverage, provenance preservation, and null handling.

## Failure Conditions

Fail on missing fan-out members, incompatible identifiers, invalid metric shapes, provenance loss, or schema failure.

## Retry Strategy

Retry after repairing the affected Deep Dive or a recoverable executor failure; do not re-run unrelated research.

## Forbidden Behavior

Do not perform external research, invent normalization inputs, or silently discard an outlier or selected competitor.

## Permissions

Use no external access, no secrets, and write only the declared dataset path.

## Budget

Use at most 20 minutes and no external sources.

## Executor Requirements

The executor must provide deterministic serialization and stable ordering for identical inputs.

## Next

Pass the normalized dataset to all four `competitor-analysis` nodes.
