# Skill: user-evidence

## Purpose

Collect evidence about user pains, severity, observed frequency signals, workarounds, and willingness signals for the approved questions.

## Trigger

Run as the `users` research branch after the Research Scope Gate.

## Inputs

Require `idea_definition` and `research_contract`; accept the current `source_index` for reuse and deduplication.

## Reads

Read the Idea Definition, Research Contract, and Source Index paths declared in `skill.yaml`.

## Tasks

Gather approved user evidence read-only, normalize observations, distinguish sample signals from population claims, and return Source upserts.

## Required Outputs

Write `artifacts/02-research/user-evidence.json` as `user_evidence` conforming to the declared Research Schema definition.

## Evidence Rules

Every item must reference a Source ID; frequency signals must not be presented as market incidence unless the sample supports inference.

## Completion Criteria

The output is schema-valid and meets the enabled Research Contract thresholds or explicitly reports an evidence gap.

## Verification

Validate provenance, threshold coverage, source diversity, freshness, privacy minimization, and unknown-value handling.

## Failure Conditions

Report unavailable sources, insufficient evidence, research limits, invalid schema, budget exhaustion, or security violations as structured errors.

## Retry Strategy

Retry source and executor failures within limits; emit a targeted Research Gap for unresolved evidence insufficiency.

## Forbidden Behavior

Do not infer population frequency from convenience samples, retain unnecessary PII, or fabricate willingness evidence.

## Permissions

Use only approved read-only external access, no secrets, and write only the declared User Evidence artifact.

## Budget

Use at most 20 minutes and 50 sources, subject to stricter effective limits.

## Executor Requirements

The executor must isolate untrusted content, minimize personal data, and return Source upserts with provenance metadata.

## Next

Pass the verified User Evidence artifact to `research-verifier`.
