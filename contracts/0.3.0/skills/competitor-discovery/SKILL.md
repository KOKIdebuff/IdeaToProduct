# Skill: competitor-discovery

## Purpose

Discover a broad, evidence-backed candidate set of direct, indirect, substitute, adjacent, and platform-risk competitors.

## Trigger

Run as the first node of the approved Competitor Research Subgraph.

## Inputs

Require `idea_definition` and `research_contract`; accept the current `source_index` when available.

## Reads

Read the Idea Definition, Research Contract, and current Source Index paths declared in `skill.yaml`.

## Tasks

Search approved sources read-only, classify candidates, explain relevance, and return source upserts through the executor result.

## Required Outputs

Write `artifacts/02-research/competitors/candidates.json` as `competitor_candidates` under the declared Competitor Schema definition.

## Evidence Rules

Every candidate and relevance claim must cite resolvable Source IDs with provenance; unavailable categories remain explicit rather than fabricated.

## Completion Criteria

When available, include at least three direct competitors and at least two source types while honoring the Research Contract.

## Verification

Validate the candidate schema, category values, Source ID integrity, provenance, and Research Contract coverage.

## Failure Conditions

Report missing inputs, unavailable sources, insufficient evidence, budget exhaustion, schema failure, or security-policy violations using structured errors.

## Retry Strategy

Retry source or executor failures within node limits; emit a targeted Research Gap for insufficient evidence and never broaden scope silently.

## Forbidden Behavior

Do not invent competitors, bypass access restrictions, mirror full external pages, or rank candidates in this skill.

## Permissions

Use read-only approved external access, never access secrets, and write only the declared candidate artifact.

## Budget

Use at most 20 minutes and 50 sources, subject to stricter effective host limits.

## Executor Requirements

The executor must isolate untrusted external instructions and return Source upserts separately from Artifact writes.

## Next

Pass the verified candidate set to the `candidate-ranking` node implemented by `competitor-ranking`.
