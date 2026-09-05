# Skill: competitor-deep-dive

## Purpose

Produce an evidence-backed Deep Dive for one selected competitor without crossing the approved research scope.

## Trigger

Run once per selected competitor after ranking, using bounded subgraph fan-out.

## Inputs

Require `competitor_ranking` and `research_contract`; accept the current `source_index` for reuse and deduplication.

## Reads

Read the ranking, Research Contract, and Source Index paths declared in `skill.yaml`.

## Tasks

Research positioning, users, product, business model, traction, feedback, strengths, weaknesses, and strategic threat for the assigned competitor.

## Required Outputs

Write one `competitor_deep_dive` member beneath `artifacts/02-research/competitors/deep-dives/` using a collision-free competitor ID.

## Evidence Rules

All material claims require Source IDs, and every time-varying metric requires an observation time; missing values remain null or unknown.

## Completion Criteria

The assigned competitor has one schema-valid Deep Dive and all required provenance and freshness fields are present.

## Verification

Validate artifact identity, selected-competitor membership, Source references, observed timestamps, and schema conformance.

## Failure Conditions

Report source unavailability, insufficient evidence, budget exhaustion, schema failure, or security-policy violations as structured errors.

## Retry Strategy

Retry only the affected competitor within node limits; unresolved evidence gaps are returned by `competitor-verifier` as targeted retry targets.

## Forbidden Behavior

Do not fabricate metrics, infer missing averages, access restricted content, or overwrite another fan-out member.

## Permissions

Use read-only approved external access, no secrets, and write only beneath the declared Deep Dive directory.

## Budget

Use at most 20 minutes and 50 sources, subject to effective host limits.

## Executor Requirements

The executor must receive a stable competitor ID and enforce collision-free, contained output paths.

## Next

Fan in all verified Deep Dives to `competitor-normalizer`.
