# Skill: competitor-scoring

## Purpose
Produce Rubric-bounded dimension judgments for deterministic Runtime aggregation.
## Trigger
Run after verified Report Projection and Profile Rubric selection.
## Inputs
Require the immutable Projection, selected Profile, and its exact versioned equal-weight Rubric.
## Reads
Read only the declared Projection, Profile, and Rubric paths.
## Tasks
Request structured semantic judgments per competitor/dimension and submit only schema-valid evidence-linked proposals for Kernel validation.
## Required Outputs
Write typed Dimension Judgment artifacts; the Runtime may write Transparent Score artifacts only after accepted independent verification and aggregation.
## Evidence Rules
Each scored judgment must reference Rubric-permitted Claims and Evidence from the Projection Closure.
## Completion Criteria
All attempted dimensions are SCORED or explicitly UNRESOLVED; no free-form total or hidden weight exists.
## Verification
Validate profile/Rubric version, integer range, dimension membership, evidence scope, coverage, configured/effective weights, and Candidate Ranking separation.
## Failure Conditions
Fail closed on out-of-range/decimal scores, invented facts, dangling refs, Rubric drift, invalid weights, or provider authority fields.
## Retry Strategy
Retry within Run Policy limits; exhaustion opens a targeted Research Gap and leaves the dimension without a legal score.
## Forbidden Behavior
Do not conduct Research, alter Rubrics, calculate a free-form total, tune per Run, or write Runtime state directly.
## Permissions
Use no external research access or secrets and write only declared scoring paths.
## Budget
Use at most 20 minutes and no external Sources.
## Executor Requirements
The semantic Judge is proposal-only; Kernel owns validation, aggregation, persistence, and ranking.
## Next
Pass Dimension Judgments to the independent Score Verifier.
