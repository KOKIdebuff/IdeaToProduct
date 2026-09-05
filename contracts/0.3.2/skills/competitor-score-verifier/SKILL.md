# Skill: competitor-score-verifier

## Purpose
Independently verify each proposed Dimension Judgment against its fixed Rubric and approved provenance Closure.
## Trigger
Run after Dimension Judgment proposal validation and before deterministic aggregation.
## Inputs
Require current Projection, selected Rubric, and proposed Judgment.
## Reads
Read only the declared Projection, Rubric, and Judgment paths.
## Tasks
Return ACCEPT, REJECT, or RETRY based solely on Rubric fit, score range, rationale, and Claim/Evidence/Source closure.
## Required Outputs
Write one typed `score_verification` artifact per reviewed Judgment.
## Evidence Rules
Verification may use only the same approved facts and provenance available to the Judge.
## Completion Criteria
Every result has a deterministic next action and cannot introduce or modify scoring inputs.
## Verification
Validate role separation, refs, Rubric version, result/action consistency, retry exhaustion, and no free-form aggregation.
## Failure Conditions
Reject malformed, unsupported, unclosed, out-of-range, or Rubric-drifting Judgments.
## Retry Strategy
Request bounded retry; on exhaustion open a targeted Research Gap and leave the dimension unresolved.
## Forbidden Behavior
Do not conduct Research, change Rubric/weights, create facts, calculate totals, or write Report sections.
## Permissions
Use no external access or secrets and write only the verification path.
## Budget
Use at most 20 minutes and no external Sources.
## Executor Requirements
Verifier role must be independent from the Judge and has no Runtime write authority.
## Next
Pass accepted verification refs to the deterministic Runtime Aggregator.
