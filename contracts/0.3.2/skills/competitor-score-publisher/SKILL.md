# Skill: competitor-score-publisher

## Purpose

Deterministically collect immutable per-competitor Transparent Scores and publish the scoring-only Report successor.

## Trigger

Run only for `SCORING_AVAILABLE` after the independent Score Verifier has accepted the required Judgments and the initial Report is current. If scoring is disabled or retry exhaustion leaves no legal collection, terminate this optional node as `SKIPPED` without publishing a successor.

## Inputs

Require the approved Candidate Ranking, active Profile, exact Rubric version, complete per-competitor Transparent Scores, their verification artifacts, and the current base `competitor_report`.

## Reads

Read only the declared ranking, current Report, immutable scores and score verifications, Profile, and Rubric paths.

## Tasks

Verify complete ranking-scope coverage and shared identities, order score references by final score descending, coverage descending, and competitor ID ascending, then use the Runtime-owned Publisher to create the collection and a scoring-only Report successor.

## Required Outputs

Write one `transparent_score_collection` and one `competitor_report` with `publication_kind: SCORE_SUCCESSOR` and an explicit current base Report.

## Evidence Rules

Every collection member must resolve to one independently verified immutable `transparent_score` with matching ranking, Profile, Rubric, and Rubric version. No score value is copied into the collection.

## Completion Criteria

The collection covers every ranked competitor exactly once, rank and tie semantics are deterministic, and the successor changes only the scoring section while preserving verification and upstream projection/chart refs. Every publication creates a new immutable HTML Bundle and inventory under its own versioned Report ref.

## Verification

Validate collection references, identities, complete coverage, deterministic order, competition ranks, shared ties, Report base identity, section preservation, CAS, idempotency, and append-only history.

## Failure Conditions

Fail closed on a missing, duplicate, unknown, stale, mismatched, unverified, or non-deterministically ranked score, or on a stale Report base.

## Retry Strategy

Replay an identical publication request idempotently; reject and refresh a stale Report base before retrying. Return invalid score inputs to their owning scoring or verification node.

## Forbidden Behavior

Do not conduct Research, propose judgments, recompute a free-form total, alter Rubrics or verification, reuse the predecessor HTML Bundle refs, publish without a legal collection, or use last-writer-wins.

## Permissions

Use no external access or secrets and write only the declared score collection, Report publication, and versioned `report-bundles/` paths through the Runtime-owned Publisher.

## Budget

Use at most 5 minutes and no external Sources.

## Executor Requirements

The executor is a deterministic Runtime-owned publisher, not an LLM scoring role, and must enforce current-root compare-and-swap and append-only publication.

## Next

Pass the current Score successor and collection to `competitor-verifier`.
