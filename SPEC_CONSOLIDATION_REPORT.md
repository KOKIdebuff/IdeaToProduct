# SPEC Consolidation Report

## 1. Freeze Result

**SPEC Status: FROZEN**

Current Source of Truth:

```text
SPEC_v0.1 Baseline
        +
SPEC_v0.2 explicit Amendment
        =
SPEC_v0.2 FROZEN Current Technical Specification
```

Precedence is `SPEC_v0.2 > uncovered SPEC_v0.1 baseline > existing code`. `SPEC_v0.1.md` and the root `0.1.0` Contract Tree remain immutable Architecture Baseline and historical audit material. Freezing the document does not claim that the v0.2 Runtime or Contract files have been implemented.

Phase 2 stops at this Gate. Phase 3 PRD-to-SPEC Traceability must pass before any P0 code or machine-readable contract implementation begins.

## 2. Consolidation Summary

`SPEC_CHANGELOG.md` records 71 final decisions:

| Status | Count | Meaning |
|---|---:|---|
| Added | 10 | Interactive Attempt, clarity/completion, dynamic methods, Interaction API/result, Idea and Research traceability, Registry, Legacy refs and new negative acceptance |
| Modified | 30 | Architecture, workflow/state/skill/artifact/API/version/scope/build-order contracts and v0.1 closure backfill |
| Inherited | 31 | Unchanged DAG, research, evidence, verification, profile, feasibility, PRD, readiness, security and budget baseline capabilities |
| Deprecated | 0 | No baseline capability was explicitly terminated |
| Conflict | 0 | All version, workflow and implementation-order conflicts were resolved |
| Unclear | 0 | All cross-version and dynamic-method boundaries were decided |

Major v0.2 changes:

- Adaptive Idea Shaping remains inside the single `idea` Node bound to `idea-intake`.
- Clarification, Controlled Brainstorming, Adaptive Product Discovery Interview and Assumption Challenge are dynamically selected methods in one Attempt; they can repeat or be skipped and have no fixed sequence.
- Interaction waiting uses `WAITING_FOR_USER` plus `current_interaction`, never Human Gate state.
- Idea Shaping has one output, `idea_definition`; Research Contract is generated afterward and Research starts only after Research Scope Gate approval.
- Version compatibility is fixed to parallel contract trees plus Version Registry; there is one Runtime, no automatic v0.1 Run migration and no mixed-version Bundle resolution.
- The latest v0.1 closure is restored: 23 Skill `output_contracts`, `competitor-verifier`, `subgraph.schema.json`, five parseable Template front matters, Subgraph producer mapping and snake_case internal Node IDs.
- P0 is one integrated implementation chain, not a v0.1 implementation followed by a v0.2 reimplementation.

## 3. Current Unique Architecture

```text
Host / User
    ↓
Single Orchestrator
    ↓ resolve contract_version through registry
Version-selected complete Workflow DAG
    ↓
Skill / Subgraph / Verifier / Human Gate
    ↓
Artifact Repository + Runtime State + Attempt History
    ↓
Event Log + Decision Log + Current Manifest
```

The Orchestrator is version-aware; the Runtime is not duplicated. It loads one complete Bundle, schedules its DAG, validates Executor proposals, persists state and artifacts, controls gates/retries, and fails closed on unsupported or mixed versions.

## 4. Implementable Contract Answer

| Concern | Frozen contract |
|---|---|
| Node | `skill`, `subgraph`, `human_gate`, `verifier`, `router` or `external_input`; `idea` remains `kind: skill`. Internal Interaction Methods are not Nodes. |
| Edge | Declarative dependency, condition, fan-out/fan-in and bounded loop edges; Profile composition cannot remove Core nodes. Research branches may fan out after Research Scope Gate. |
| Input | Natural-language Raw Idea, Product Profile, optional Contract override, optional `contract_version` fixed to `0.2.0`, and explicitly validated optional `legacy_input_refs`. |
| Output | Versioned Artifacts and Verification results culminating in PRD plus `READY_FOR_BUILD`, `READY_WITH_ACCEPTED_RISKS` or `NOT_READY`. Idea Shaping outputs only `idea_definition`. |
| Artifact | Append-only, schema-versioned, single-writer and selected through Current Manifest. Checkpoints, interactions and method history are Runtime working state, not business Artifacts. |
| Gate | Three standard Human Gates: Research Scope, Product Direction and MVP Scope; Evidence Waiver is conditional. Interactive user input is not a Gate and creates no Decision. |
| State | Node, Attempt, Workflow, Verification, Gate, Feasibility and Readiness enums remain separated. `current_interaction` and `current_gate` are independent and mutually exclusive during Idea Shaping. |
| Retry | A user reply resumes the same Interactive Attempt and does not consume Retry. Verifier gaps create bounded targeted retries. After insufficient context at the round limit, only explicit Retry creates a new Attempt. |
| Failure handling | Structured errors drive blocked, paused, retry, waiver, external-proof or terminal paths. Unsupported v0.1 State returns `SCHEMA_VERSION_UNSUPPORTED`, preserves data and does not migrate. |
| Runtime transition | `PENDING → READY → RUNNING`; an interactive Skill may move `RUNNING → WAITING_FOR_USER → RUNNING` in one Attempt, then complete/verify. Human Gates move through their own waiting and decision path. Failed/insufficient verification uses bounded retry or explicit terminal handling. |
| Skill invocation | Orchestrator resolves the Skill from the selected Bundle, validates inputs and permissions, creates an Attempt, sends a version-matched Executor Request, validates Result/Artifact/Checkpoint proposals, persists them atomically, then advances or retries the DAG. |

## 5. Adaptive Idea Shaping Contract

The exact method enum is:

```text
clarification
controlled_brainstorming
adaptive_product_discovery_interview
assumption_challenge
```

Each round first runs Completion Check, selects the highest-value information gap, then selects the best method. Completely tied candidates use stable Method ID ordering only as a deterministic tie-breaker, not as a workflow sequence.

- Clear: normally zero questions; at most one blocking clarification.
- Partial: progressive interaction and early exit as soon as the Idea is researchable.
- Vague: may use Controlled Brainstorming or Adaptive Interview, while allowing option rejection, modification and free-form input.
- Controlled Brainstorming presents two to four framing options plus one main question and does not generate a complete Feature List.
- Maximum: eight main questions. A researchable result becomes `PARTIAL_RESEARCHABLE`; otherwise the Run pauses with `INSUFFICIENT_PRODUCT_CONTEXT`.
- Completion stops questioning immediately. No preset Interview may continue after completion.

The current method is present in Skill config, Checkpoint, Executor Result, Runtime State and Host-facing state. Clients cannot set or override it. No Brainstorming/Interview-specific API, Node, Gate, Attempt or Artifact exists.

## 6. Version and Compatibility Strategy

```text
root contract tree             → immutable 0.1.0 baseline
contracts/registry.yaml        → version resolution and new-run policy
contracts/0.2.0/               → complete current Bundle
single Orchestrator / Runtime  → executes selected Bundle
```

- New Runs default to and only allow `contract_version: 0.2.0`.
- All schema refs, Skill/Profile refs, Workflow versions and Bundle resources must resolve within one version tree.
- v0.1 Runs are available for historical validation and read-only audit only. Current Runtime cannot create or resume them.
- P0 has no cross-version Run migration. A v0.1 in-flight State is rejected with `SCHEMA_VERSION_UNSUPPORTED` and remains unchanged.
- Legacy input compatibility is explicit and default-deny. Source, Evidence, Claim and registered Research artifacts may only seed a new Run as read-only refs.
- Old Evidence is revalidated under v0.2 Freshness, Provenance, safety and Verification rules. It never enters Current Manifest or directly changes Node, Gate or Readiness state.
- Workflow-driving and runtime objects such as Idea Definition, Contract, Product Definition, Decision, MVP, PRD, Readiness, State, Attempt, Event and Manifest are blocked from direct cross-version reuse.

## 7. Workflow, Gates and Concurrency

Serial control path:

```text
Idea Shaping
→ Research Contract
→ Research Scope Gate
→ Research fan-out
→ Research Verifier / bounded Gap Loop / optional Evidence Waiver
→ Research Synthesis
→ Opportunity
→ Product Direction Gate
→ Product Definition
→ Feasibility / optional External Proof
→ MVP Scope
→ MVP Scope Gate
→ PRD
→ PRD Consistency Verifier
→ Build Readiness Verifier
```

Parallel boundaries:

- Competitor, User, Market and Technology research can run in parallel after Research Scope Gate, subject to Profile and `max_parallel`.
- Competitor Deep Dives and eligible analysis branches can fan out within their Subgraph.
- Idea Interaction rounds, each Gate, Research verification/synthesis, downstream product decisions and final verifiers remain serial where dependencies require them.

## 8. Frozen Scope

P0 MUST:

- Complete v0.2 Bundle and Registry, Core Workflow, four Profiles, all inherited research/evidence/gate/verification/retry/readiness capabilities.
- Adaptive Idea Shaping, dynamic methods, Checkpoint/Resume, Idea Definition and Research Contract traceability.
- Competitor/User/Market/Technical research through PRD and final Readiness.
- Single-writer storage, recovery, language-neutral CLI/API, three generic adapters, fixtures and live acceptance.

P1 SHOULD:

- UI Graph, Artifact Inspector, Better Chart Renderer and Incremental Research.

Future / Not Implemented:

- Vendor-specific or distributed Executor Adapters, team and organization features, Workflow Library, benchmark/evaluation suite and other §54.3 items.
- Cross-version Run Migration is P1+ candidate work, not P0 and not part of the frozen P1 SHOULD list.

## 9. Unified P0 Build Order

1. Version Registry and complete v0.2 Contract/Schema/Skill/Subgraph/Template/Fixture closure.
2. Orchestrator, DAG, State, Attempt, Interaction, Gate, Retry, single-writer storage, CLI/API and generic adapters.
3. `idea-intake`, dynamic methods, Checkpoint/Resume, Idea Definition and Research Contract.
4. Competitor Research Subgraph.
5. User/Market/Technical Research, Verifier, Waiver, Gap Loop and Synthesis.
6. Opportunity, Product Definition, Feasibility, External Proof and MVP Scope.
7. PRD, final verifiers, full fixtures and Live Acceptance.

This sequence is frozen for later implementation planning only; it is not an authorization to start Phase 5.

## 10. Conflicts and Unclear Items

Resolved:

- Separate v0.1 then v0.2 implementation was removed in favor of one integrated chain.
- Version coexistence was resolved to parallel contract trees and Registry.
- v0.1 Run recovery was resolved to Fail Closed without P0 migration.
- Dynamic methods were resolved as same-Attempt internal Skill strategy.
- Missing latest v0.1 output/Subgraph/Template closure was restored.

Unresolved `Conflict`: 0  
Unresolved `Unclear`: 0

## 11. Phase Boundary and Verification

Phase 2 changed documentation only:

- Updated: `SPEC_v0.2.md`
- Added: `SPEC_CHANGELOG.md`
- Added: `SPEC_CONSOLIDATION_REPORT.md`
- Unchanged: `SPEC_v0.1.md`
- Unchanged: frozen `PRD_v0.2.md`
- Not read as authority: existing implementation code
- Not modified: Workflow, Schema, Profile, Skill, Subgraph, Template, Fixture, Runtime or test files

Deterministic freeze checks require: both protected hashes unchanged, all 57 main sections decided once, legal status enum with zero unresolved conflict/unclear, all fenced YAML/JSON examples parse, dynamic Method coverage is complete, v0.1 closure is present, the thirteen negative tests are present, and the separate incremental implementation section is absent.

Executed results:

| Check | Result |
|---|---|
| `SPEC_v0.1.md` SHA-256 | `3FF75E1C02D6D4088D45C210349F5EC4AE5620D453A63D82BC34A2219E1079EE` — unchanged |
| `PRD_v0.2.md` SHA-256 | `159F8E7298FA118225D686CD1D4CF0D044FD11A879CEBB73D82186ECD5FE9797` — unchanged |
| Frozen `SPEC_v0.2.md` SHA-256 | `9CD4A7CBF284499752974213FF2AC8EB48A5ECB15951E92E1A89CF1B98F4B4E4` |
| Main chapter decisions | 57 / 57, unique and ordered |
| Changelog decisions | 71; legal status enum; Conflict 0; Unclear 0 |
| YAML / JSON examples | 57 parsed; 0 errors |
| Contract closure | 23 Skills; 5 Templates; Subgraph Schema and producer/verifier closure present |
| Dynamic Method coverage | All four methods present across Skill, Checkpoint, Executor, State/API and tests |
| Negative acceptance | 13 / 13 |
| Hyphenated Runtime target IDs | 0 |
| Separate v0.2 implementation phase text | Absent |

**Recommendation: PROCEED TO PHASE 3 TRACEABILITY ONLY — STOP IMPLEMENTATION**
