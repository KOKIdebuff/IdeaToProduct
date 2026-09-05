# Skill: market-landscape

## Purpose

Describe category maturity, timing, drivers, barriers, business-model patterns, platform risks, and unknowns using current evidence.

## Trigger

Run as the `market` research branch after the Research Scope Gate.

## Inputs

Require `idea_definition` and `research_contract`; accept the current `source_index` for reuse and deduplication.

## Reads

Read the Idea Definition, Research Contract, and Source Index paths declared in `skill.yaml`.

## Tasks

Research the approved market questions, distinguish observed facts from interpretation, record freshness, and return Source upserts.

## Required Outputs

Write `artifacts/02-research/market-landscape.yaml` as `market_landscape` under the declared Research Schema definition.

## Evidence Rules

Every material market claim requires provenance, and market-report freshness must follow the effective Research Contract.

## Completion Criteria

The output is schema-valid and covers every enabled market question or records a precise evidence gap.

## Verification

Validate Source references, freshness, contradiction handling, question coverage, and explicit unknowns.

## Failure Conditions

Report unavailable sources, insufficient evidence, research limits, schema failure, budget exhaustion, or security violations as structured errors.

## Retry Strategy

Retry source and executor failures within limits; emit a targeted Research Gap for unresolved evidence insufficiency.

## Forbidden Behavior

Do not present stale reports as current, fabricate market size, or convert an unknown into a confident conclusion.

## Permissions

Use only approved read-only external access, no secrets, and write only the declared Market Landscape artifact.

## Budget

Use at most 20 minutes and 50 sources, subject to stricter effective limits.

## Executor Requirements

The executor must isolate untrusted source content and preserve observation and publication dates.

## Next

Pass the verified Market Landscape artifact to `research-verifier`.
