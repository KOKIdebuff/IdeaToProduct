# Skill: competitor-analysis

## Purpose

Analyze one fixed competitor dimension from the normalized dataset while preserving an explicit methodology.

## Trigger

Run in the four static subgraph nodes `feature_analysis`, `traction_analysis`, `review_analysis`, and `pricing_analysis` after normalization.

## Inputs

Require `competitor_dataset` and `research_contract`; accept Source Index context for provenance validation.

## Reads

Read the Research Contract, normalized dataset, and current Source Index paths declared in `skill.yaml`.

## Tasks

Select the dimension from the invoking node ID, calculate or classify only supported metrics, and embed scoring and missing-value methodology in the output.

## Required Outputs

Write one node-specific `competitor_analysis` member beneath `artifacts/02-research/competitors/analysis/` without sharing a fixed filename across parallel nodes.

## Evidence Rules

Every derived metric must identify its inputs and method; qualitative coding must be labeled `derived_qualitative` and cite Evidence IDs.

## Completion Criteria

The assigned dimension has one schema-valid analysis artifact with methodology, limitations, and collision-free identity.

## Verification

Validate the node-to-dimension mapping, schema, methodology, Evidence references, missing-value rules, and deterministic calculations.

## Failure Conditions

Fail when required dataset dimensions are absent, fewer than the minimum metrics support a composite score, or provenance is invalid.

## Retry Strategy

Retry the affected analysis after upstream correction; insufficient source data is reported to `competitor-verifier` for targeted recovery.

## Forbidden Behavior

Do not perform external research, use undocumented weights, fill missing values, or write another analysis node's member.

## Permissions

Use no external access, no secrets, and write only beneath the declared analysis directory.

## Budget

Use at most 20 minutes and no external sources.

## Executor Requirements

The executor must expose the invoking static node ID and provide deterministic arithmetic and collision-free contained writes.

## Next

Fan in all required analysis members to `competitor-visualization`.
