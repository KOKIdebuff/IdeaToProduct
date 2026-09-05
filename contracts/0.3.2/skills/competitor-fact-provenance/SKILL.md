# Skill: competitor-fact-provenance

## Purpose
Materialize verified field-level provenance into one deterministic Report Projection.
## Trigger
Run after all required competitor analysis artifacts are verified.
## Inputs
Require the current contract, candidate/ranking/deep-dive/dataset/analysis artifacts, Source Index, and state-version provenance bindings.
## Reads
Read only the declared current Artifact and Source paths; never dereference Source URLs.
## Tasks
Bind existing facts to Claim/Evidence/Source records, form deterministic Fact Groups and DOM scopes, and calculate the minimum Citation Closure.
## Required Outputs
Write one typed `report_projection` artifact at the declared path.
## Evidence Rules
Every rendered external fact must close through Claim to Evidence to Source; no inferred or orphan fact is allowed.
## Completion Criteria
All required facts have stable IDs, content identity, resolvable references, deterministic ordering, and exact minimal Closure.
## Verification
Validate state/version identity, upstream Artifact refs, JSON pointers, binding equality, closure completeness, and duplicate/conflict behavior.
## Failure Conditions
Fail closed on missing or dangling binding, state drift, conflicting identity, unsafe path, or unresolvable Source metadata.
## Retry Strategy
Open a targeted Research Gap for insufficient evidence; retry only after the affected upstream fact or provenance binding is corrected.
## Forbidden Behavior
Do not research, fetch URLs, infer from HTML/SVG, create business facts, or alter upstream Artifacts.
## Permissions
Use no external access or secrets and write only the declared Projection path.
## Budget
Use at most 20 minutes and no external Sources.
## Executor Requirements
Execution must be deterministic and Kernel-owned; provider proposals have no write authority.
## Next
Pass the verified Projection to visualization, scoring, and verification consumers.
