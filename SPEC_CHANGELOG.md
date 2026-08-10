# SPEC Version Consolidation

> Baseline: `SPEC_v0.1.md` / Contract `0.1.0`  
> Amendment and Current Source of Truth: `SPEC_v0.2.md` / Contract `0.2.0`  
> Consolidation rule: v0.2 explicit changes override v0.1; topics not addressed by v0.2 inherit v0.1. Absence never means deprecation.  
> Frozen result: `SPEC_v0.2.md` is the only Current Technical Specification; `SPEC_v0.1.md` remains immutable Architecture Baseline.

Status is restricted to `Added`, `Modified`, `Deprecated`, `Inherited`, `Conflict`, and `Unclear`. This frozen changelog contains no unresolved `Conflict` or `Unclear` decision.

## 1. Chapter-by-Chapter Decisions

| Contract ID / Topic | v0.1 | v0.2 | Final Decision | Status | Source Sections |
|---|---|---|---|---|---|
| S-01 / Spec 目标 | Defines implementable P0 architecture baseline. | Adds Adaptive Idea Shaping target but previously described a draft delta. | Freeze v0.2 as baseline plus Amendment; implementation remains blocked until Phase 3 PASS. | Modified | SPEC v0.1 §1; SPEC v0.2 §1 |
| S-02 / Architecture Overview | Single Orchestrator, DAG, artifacts and runtime state. | Adds interactive execution concerns. | Keep one Orchestrator and one Runtime; select a complete versioned DAG through Registry. | Modified | v0.1 §2; v0.2 §2 |
| S-03 / Runtime Responsibilities | Scheduling, persistence, gates, retry and recovery. | Adds Interaction checkpoint and resume. | Inherit all baseline responsibilities; add Registry resolution, legacy validation and unsupported-version Fail Closed. | Modified | v0.1 §3; v0.2 §3 |
| S-04 / Core Domain Model | Defines Node and Edge kinds and declarative conditions. | Does not replace the model. | Inherit Node and Edge contracts unchanged; internal method calls are not Nodes or Edges. | Inherited | v0.1 §4; v0.2 §4 |
| S-05 / Workflow File | Core DAG from idea through Readiness. | Adds Adaptive Idea Shaping inside idea. | Keep the same Core DAG; idea remains a skill and the selected workflow comes from a complete `0.2.0` Bundle. | Modified | v0.1 §5; v0.2 §5 |
| S-06 / State and Result Model | Separates Node, Verification, Gate, Feasibility, Workflow and Readiness states. | Adds interactive waiting. | Preserve all state domains; add `WAITING_FOR_USER` without conflating Interaction and Gate. | Modified | v0.1 §6; v0.2 §6 |
| S-07 / Runtime State Schema | Persists workflow, node, gate and readiness state. | Adds `current_interaction`. | Add current Method and checkpoint references; v0.1 State remains read-only and cannot be resumed. | Modified | v0.1 §7; v0.2 §7 |
| S-08 / Attempt Model | Append-only Attempt and retry history. | Adds Interactive Attempt and Checkpoint. | Resume user replies in the same Attempt without consuming Retry; explicit Retry creates a new Attempt after safe stop. | Modified | v0.1 §8; v0.2 §8 |
| S-09 / Standard Skill Contract | Defines SKILL.md and skill.yaml contracts. | Adds optional interaction config. | Require output contracts for all 23 Skills and four dynamic Methods for `idea-intake`. | Modified | v0.1 §9; v0.2 §9 |
| S-10 / Artifact Contract | Versioned artifacts, current manifest and single writer. | Excludes Interaction Checkpoint from artifacts. | Preserve artifact rules; Idea Shaping produces only `idea_definition`, never method-specific artifacts. | Modified | v0.1 §10; v0.2 §10 |
| S-11 / Directory Layout | Defines full baseline contract and runtime tree. | Previously omitted latest verifier and Subgraph schema closure. | Freeze immutable root `0.1.0` plus complete `contracts/0.2.0/` Bundle with 23 Skills and all schemas/templates. | Modified | v0.1 §11; v0.2 §5.1, §11 |
| S-12 / Idea Definition | Research-before hypothesis artifact. | Adds clarity, shaping, assumptions, unknowns and seeds. | Use the extended `0.2.0` Idea Definition; prohibit verified conclusions and extra Idea Shaping artifacts. | Modified | v0.1 §12; v0.2 §12 |
| S-13 / Research Contract | Defines effective research questions and run policy after Idea. | Adds origin refs from Idea Definition. | Generate independently after Idea completion; preserve traceability and require Research Scope Gate before Research. | Modified | v0.1 §13; v0.2 §13 |
| S-14 / Source and Evidence | Source Index, provenance and evidence contract. | No semantic replacement. | Inherit baseline; legacy Evidence is only a seed and must pass v0.2 checks again. | Inherited | v0.1 §14; v0.2 §14, §50.5 |
| S-15 / Claim Schema | Separates claim, evidence and validation status. | No explicit replacement. | Inherit without weakening Unknown or evidence traceability. | Inherited | v0.1 §15; v0.2 §15 |
| S-16 / Decision Schema | Records approved product decisions and evidence links. | No explicit replacement. | Inherit; Interaction responses are not Decisions. | Inherited | v0.1 §16; v0.2 §16, §32.1 |
| S-17 / Source Hierarchy | Defines tiered and claim-specific source quality. | No explicit replacement. | Inherit source hierarchy and anti-fabrication constraints. | Inherited | v0.1 §17; v0.2 §17 |
| S-18 / Competitor Subgraph | Dataset-first research Subgraph with verifier loop. | Previously used ambiguous hyphenated internal IDs. | Restore the full Subgraph schema, producer and unique verifier closure; internal Node IDs use snake_case. | Modified | v0.1 §18; v0.2 §18 |
| S-19 / Competitor Candidate | Defines candidate categories and evidence. | No explicit replacement. | Inherit candidate schema. | Inherited | v0.1 §19; v0.2 §19 |
| S-20 / Competitor Deep Dive | Defines per-competitor research payload. | No explicit replacement. | Inherit deep-dive schema and source requirements. | Inherited | v0.1 §20; v0.2 §20 |
| S-21 / Competitor Dataset | Defines normalized comparison dataset. | No explicit replacement. | Inherit normalized dataset contract. | Inherited | v0.1 §21; v0.2 §21 |
| S-22 / Scoring Methodology | Defines auditable scoring and null handling. | No explicit replacement. | Inherit methodology; no invented values. | Inherited | v0.1 §22; v0.2 §22 |
| S-23 / Visualization Pipeline | Separates data, chart spec and renderer. | No explicit replacement. | Inherit dataset-first renderer-independent pipeline. | Inherited | v0.1 §23; v0.2 §23 |
| S-24 / Chart Artifact | Defines chart data, rendering and insight artifact. | No explicit replacement. | Inherit chart artifact boundary. | Inherited | v0.1 §24; v0.2 §24 |
| S-25 / Profile Visualizations | Defines required charts per Profile. | No explicit replacement. | Inherit all Profile visualization requirements and Gap/Waiver behavior. | Inherited | v0.1 §25; v0.2 §25 |
| S-26 / User Evidence Research | Defines user evidence scope and outputs. | No explicit replacement. | Inherit unchanged. | Inherited | v0.1 §26; v0.2 §26 |
| S-27 / Market Landscape | Defines market evidence and outputs. | No explicit replacement. | Inherit unchanged. | Inherited | v0.1 §27; v0.2 §27 |
| S-28 / OSS and Technical Landscape | Defines technical research and limitations. | No explicit replacement. | Inherit unchanged. | Inherited | v0.1 §28; v0.2 §28 |
| S-29 / Research Verifier | Controls research completion through PASS, PARTIAL or FAIL. | No explicit replacement. | Inherit verifier authority and required gap output. | Inherited | v0.1 §29; v0.2 §29 |
| S-30 / Research Gap Planner | Produces targeted retry plan. | No explicit replacement. | Inherit gap schema and retry targeting. | Inherited | v0.1 §30; v0.2 §30 |
| S-31 / Loop Algorithm | Defines bounded research retry and invalidation. | No explicit replacement. | Inherit global and node retry bounds. | Inherited | v0.1 §31; v0.2 §31 |
| S-32 / Human Gate | Defines three standard gates and conditional Evidence Waiver. | Clarifies interactive input is not a gate. | Preserve all gates; keep `current_gate` null during Idea Interaction and create no Gate Decision. | Modified | v0.1 §32; v0.2 §32 |
| S-33 / Downstream Invalidation | Defines explicit invalidation after approved changes. | No explicit replacement. | Inherit unchanged; Interaction Checkpoint is working state, not approved product change. | Inherited | v0.1 §33; v0.2 §33 |
| S-34 / Research Synthesis | Produces grounded synthesis after valid research outcome. | No explicit replacement. | Inherit PASS or accepted-PARTIAL prerequisites. | Inherited | v0.1 §34; v0.2 §34 |
| S-35 / Opportunity Mapping | Maps evidence to opportunities before direction gate. | No explicit replacement. | Inherit unchanged. | Inherited | v0.1 §35; v0.2 §35 |
| S-36 / Product Definition | Creates evidence-backed product direction. | Clarifies boundary from Idea Definition. | Inherit output; only post-Research approved decisions may populate it. | Inherited | v0.1 §36; v0.2 §12.2, §36 |
| S-37 / Feasibility Review | Defines feasible, conditional, blocked and not-feasible results. | No explicit replacement. | Inherit unchanged. | Inherited | v0.1 §37; v0.2 §37 |
| S-38 / Proof Planner | Plans external proof and re-review. | No explicit replacement. | Inherit external wait and import boundary. | Inherited | v0.1 §38; v0.2 §38 |
| S-39 / MVP Scope | Defines scoped P0 output after feasibility. | No explicit replacement. | Inherit unchanged and preserve Scope Gate. | Inherited | v0.1 §39; v0.2 §39 |
| S-40 / PRD and Final Verifiers | Separates PRD generation, consistency and Readiness. | No explicit replacement. | Inherit; only Build Readiness Verifier writes final readiness. | Inherited | v0.1 §40; v0.2 §40 |
| S-41 / Event Log | Append-only runtime audit events. | Adds Idea Interaction events. | Add Method selection and Legacy Ref accept/reject events; preserve recovery and audit semantics. | Modified | v0.1 §41; v0.2 §41 |
| S-42 / Decision Log | Stores formal human/product decisions. | No explicit replacement. | Inherit; Interaction responses never enter Decision Log. | Inherited | v0.1 §42; v0.2 §42 |
| S-43 / Error Taxonomy | Defines structured runtime errors. | Adds product-context and schema-version errors. | Retain baseline errors; add `INSUFFICIENT_PRODUCT_CONTEXT` and `SCHEMA_VERSION_UNSUPPORTED` Fail Closed behavior. | Modified | v0.1 §43; v0.2 §43 |
| S-44 / Idempotency | Guards retries and duplicate mutations. | Adds interaction response idempotency. | Preserve baseline; same reply resumes same Attempt once and conflicting reply is rejected. | Modified | v0.1 §44; v0.2 §44, §50.1 |
| S-45 / Freshness Policy | Defines freshness by source and claim type. | No explicit replacement. | Inherit; legacy evidence is always rechecked. | Inherited | v0.1 §45; v0.2 §45, §50.5 |
| S-46 / Parallel Execution | Research fan-out with bounded parallelism. | No explicit replacement. | Inherit; Idea Shaping remains serial within one Attempt. | Inherited | v0.1 §46; v0.2 §46 |
| S-47 / Security and Safety | Defines least privilege, path and prompt-injection controls. | No explicit replacement. | Inherit and apply to Legacy Ref validation. | Inherited | v0.1 §47; v0.2 §47, §50.5 |
| S-48 / Product Profile | Defines four Profiles and composition rules. | Uses target version `0.2.0`. | Inherit profile semantics; publish same-version Profile refs inside the complete v0.2 Bundle. | Inherited | v0.1 §48; v0.2 §48 |
| S-49 / CLI | Defines language-neutral commands and exit codes. | Adds interaction submit. | Add optional `contract_version` and `legacy_input_refs`; do not expose a client Method override. | Modified | v0.1 §49; v0.2 §49 |
| S-50 / Runtime API | Defines operations, adapters, policy and manifest. | Adds interactive request/result. | Add version selection, Legacy Refs and Method exposure; keep one API and no method-specific endpoints. | Modified | v0.1 §50; v0.2 §50 |
| S-51 / Testing Strategy | Covers static, unit, contract and workflow tests. | Adds interactive tests. | Add Method, Registry, Legacy Ref and latest v0.1 closure tests; require 13 negative tests. | Modified | v0.1 §51; v0.2 §51 |
| S-52 / P0 Acceptance | Defines deterministic fixtures and live acceptance. | Adds Idea Shaping fixtures. | Treat all fixtures as one integrated P0 Bundle, with category-specific reporting only. | Modified | v0.1 §52; v0.2 §52 |
| S-53 / P0 Build Order | Baseline seven-step implementation chain. | Previously added a separate v0.2 sequence. | Replace both with one seven-step integrated chain beginning with Registry and complete v0.2 closure. | Modified | v0.1 §53; v0.2 §53 |
| S-54 / Scope Boundary | Lists capabilities outside P0. | Previously mixed P1 and Future. | Freeze non-overlapping P0 MUST, P1 SHOULD and Future / Not Implemented scopes. | Modified | v0.1 §54; v0.2 §54 |
| S-55 / Architecture Decisions | Records baseline architecture reasons. | Adds interactive decisions. | Preserve ADR-01 through ADR-16 and add dynamic Method, Registry and Legacy Ref decisions. | Modified | v0.1 §55; v0.2 §55 |
| S-56 / Definition of Done | Defines contract and future runtime completion. | Previously called v0.2 a draft design baseline. | Freeze document DoD separately from unimplemented Runtime DoD and include all consolidated closure checks. | Modified | v0.1 §56; v0.2 §56 |
| S-57 / Core Principle | Defines stable Executor, Skill, Workflow, Artifact and governance boundaries. | Adds Checkpoint and Idea shaping emphasis. | Preserve baseline boundaries and treat Method as recoverable internal Skill strategy. | Modified | v0.1 §57; v0.2 §57 |

## 2. Important Subcontract Decisions

| Contract ID / Topic | v0.1 | v0.2 | Final Decision | Status | Source Sections |
|---|---|---|---|---|---|
| X-01 / Interactive Attempt | Non-interactive Attempt baseline. | Introduces user waiting inside an Attempt. | Persist working Checkpoints and resume the same Attempt; only explicit Retry creates another Attempt. | Added | v0.2 §8.1 |
| X-02 / Clarity and Completion | No adaptive pre-research classification. | Adds CLEAR, PARTIAL, VAGUE and safe outcomes. | Completion-first evaluation controls early exit and maximum eight main questions. | Added | v0.2 §8.2, §12.1 |
| X-03 / Dynamic Interaction Method | No Method contract. | Methods were conceptually mentioned but not wired across contracts. | Use exactly four dynamic methods with `highest_value_gap`; allow repeat and skip, prohibit fixed order. | Added | v0.2 §8.3, §9, §50, §51 |
| X-04 / Interaction API | No interaction operation. | Adds response submit and current interaction. | Host receives current Method but submits only Option and Freeform; no dedicated Brainstorming or Interview API. | Added | v0.2 §49, §50.1 |
| X-05 / Executor Waiting Result | Executor returns completed or failed. | Adds `WAITING_FOR_USER`. | Use completed, waiting-for-user or failed with conditional Request and Checkpoint fields; old adapters Fail Closed. | Added | v0.2 §50.2 |
| X-06 / Idea Definition Extension | Baseline hypothesis artifact. | Adds shaping state, assumptions, unknowns and research seeds. | Keep one `idea_definition`; prohibit validated conclusions and method-specific artifacts. | Added | v0.2 §12 |
| X-07 / Research Question Traceability | Research questions exist without Idea-origin links. | Adds `origin_refs`. | Every Research Question traces to Assumption, Unknown or Research Seed from Idea Definition. | Added | v0.2 §13.1 |
| X-08 / Version Registry | Single root baseline tree. | Compatibility strategy was not previously decided. | Use immutable root `0.1.0` plus complete `contracts/0.2.0/` selected by Registry and one Runtime. | Added | v0.2 §5.1, §50.5 |
| X-09 / Legacy Input Ref | No cross-version seed interface. | Cross-version reuse boundary was unclear. | Add explicit hash-bound refs, source-version validation, default-deny matrix and v0.2 re-verification. | Added | v0.2 §50.5 |
| X-10 / Skill Output Closure | Latest baseline requires `output_contracts`. | Earlier v0.2 text omitted them. | Require artifact type, write, schema ref and nullable template ref; writes sets must match exactly. | Modified | v0.1 §9; v0.2 §9 |
| X-11 / Competitor Verifier Closure | Latest baseline defines the 23rd Skill and unique Subgraph verifier. | Earlier v0.2 layout and IDs were incomplete. | Restore verifier Skill, Subgraph schema, producer references, unique terminal verifier and snake_case runtime targets. | Modified | v0.1 §11, §18; v0.2 §11, §18 |
| X-12 / Markdown Template Closure | Five parseable templates at `0.1.0`. | Target Bundle requires v0.2 versions. | Preserve mappings and front matter format; publish the five templates as `0.2.0`. | Modified | v0.1 §11; v0.2 §11 |
| X-13 / Negative Acceptance | Baseline has no Adaptive Idea Shaping negatives. | Earlier v0.2 defined ten. | Freeze thirteen, including no fixed Method steps, no method-specific artifacts and no post-completion questioning. | Added | v0.2 §51.5 |
| X-14 / Integrated Build Chain | Baseline and amendment could be read as sequential implementations. | Earlier v0.2 explicitly separated incremental work. | One integrated P0 chain implements inherited baseline and Amendment together; Phase 3 PASS remains mandatory. | Modified | v0.2 §53 |

## 3. Resolution Summary

- `Added`: 10
- `Modified`: 30
- `Deprecated`: 0
- `Inherited`: 31
- `Conflict`: 0
- `Unclear`: 0
- Total decisions: 71

Resolved conflicts:

- The former “baseline first, v0.2 increment later” interpretation is replaced by one integrated P0 chain.
- Version coexistence is fixed to parallel contract trees plus one Version Registry and one Runtime.
- Dynamic Idea Shaping methods are fixed as internal strategy, not top-level workflow structure.
- The latest v0.1 output, template and Competitor Subgraph closure is explicitly inherited into the complete v0.2 Bundle.

No v0.1 capability is deprecated merely because the earlier v0.2 draft did not repeat it.
