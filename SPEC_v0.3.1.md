# Product Discovery SkillGraph — SPEC v0.3.1 Design Amendment

> Status: **Approved technical design with a staged static Bundle closure; not registered, frozen, activated, or Runtime-implemented.**  
> Predecessor: `SPEC_v0.3.md` / Contract `0.3.0` (frozen and unchanged).  
> Intended target: a complete independent Contract `0.3.1` Bundle.

## 1. Inheritance and activation boundary

This Amendment inherits all `SPEC_v0.3.md` semantics except the additive
Report Publication, Fact-Level Citation, and Transparent Scoring requirements
below. It does not mutate v0.2/v0.3 Bundle contents, Runtime behavior,
Registry selection, API wire version, or existing Run resume semantics.

The selected Runtime Contract remains `0.3.0` until a full `0.3.1` Bundle,
Registry schema/entry, Resolver support, fixtures, validators, and tests are
implemented and verified. An existing `0.3.0` Run must always resume its
complete `0.3.0` Bundle; there is no migration, fallback, or mixed-Bundle
assembly.

## 2. ADR-22 — v0.3.1 closed-version governance

`0.3.1` is the approved next Contract design target. It must be introduced as
a complete, independent Bundle and only then become the default new-run
version. At that future activation point, `0.3.0` becomes `frozen_previous`
with resume/audit allowed and new runs forbidden. Before activation, Registry
and Runtime remain exactly at their observed `0.3.0` current/default state.

## 3. ADR-23 — Immutable Report Bundle Publisher

`competitor-report.html` is published by a dedicated Runtime-managed,
single-writer Immutable Report Bundle Publisher. The Publisher must:

- atomically publish root HTML and only contained Bundle-local static assets;
- maintain an append-only, hashable inventory and versioned root reference;
- enforce safe relative paths, containment, symlink rejection, and declared
  Writer permissions;
- preserve non-current versions/crash leftovers for recovery diagnostics;
- use explicit base-version CAS/idempotency for successor publications; and
- prohibit network, URL fetches, remote assets, scripts, event handlers,
  external rendering services, and fact inference.

The precise Fact Provenance representation/owner remains an open design item.
It must be resolved before Fact Provenance Materialization is implemented; a
Builder cannot choose it ad hoc.

## 4. ADR-24 — Fact-Level Citation Closure and local rendering

### 4.1 Required fact traceability

For any visible external fact, the selected `0.3.1` Contract must prove the
following closed relation before HTML rendering:

```text
Rendered Fact / Fact Group → Claim → Evidence → Source
```

Candidate selection/exclusion reasons, Deep Dive facts, Analysis facts and
conclusions, Dataset-derived external values, and Chart/Table external values
are cited facts. Artifact identifiers, UI structure, Builder/Workflow
metadata, and local verification status are not external facts.

Citation Closure contains only the minimum stable-deduplicated Claim,
Evidence, and Source set reachable from rendered cited facts. Missing or
dangling references, a cited fact without provenance, or a Closure that
contains an unreferenced Source/Evidence is a validation error. Required cited
facts fail Report Build closed; optional favicon availability does not.

### 4.2 Citation source metadata and UI

A Source in Citation Closure must have validated canonical HTTP(S) URL,
publisher short name, title, and excerpt. The selected `0.3.1` Source Contract
must represent publisher short name and optional local favicon reference
explicitly; it may not infer them from a URL. Existing source text is
untrusted data and must be HTML-escaped before projection.

Each cited Fact/Group renders local, pill-style inline `<a>` Badge(s) whose
`href` exactly equals the verified canonical URL. A local CSS-only hover/focus
Preview Card renders the verified publisher short name, title, excerpt, and
canonical URL verbatim. The only permitted external dependency is a user's
passive click on a Badge; offline opening and reading must require no network.

Favicon is optional presentation metadata. If its local ref is absent,
invalid, or unavailable, the Report omits it or uses a Bundle-local generic
icon without network access and without failing the Build.

### 4.3 Deterministic projection

The Contract must define a deterministic projection/DOM scope mechanism so a
Builder never guesses badge coverage from rendered prose. A Fact Group is
legal only when all grouped facts have the same Evidence/Source set; different
provenance must remain separate. Stable sort, stable deduplication, reference
resolution, and dangling-reference validation are mandatory. Exact multi-Badge
priority and Preview truncation remain open presentation decisions.

## 5. ADR-25 — Report successor section ownership

The initial HTML Builder emits `PENDING` verification and, absent a valid
Transparent Score Artifact, `NOT_PERFORMED` scoring. Future Report successors
must use current-root CAS and may alter only their assigned section:

| Publisher | May change | Must not change |
|---|---|---|
| HTML Builder | Initial deterministic presentation | Research facts, upstream Artifacts, Renderer output |
| Competitor Verifier | Verification Summary / verification ref | every other Report content |
| Score Publisher | scoring section / score ref | every non-scoring Report section |

On base-version conflict, a Publisher must reject/refresh/retry according to
the future explicit policy; it must never silently overwrite another
Publisher's update.

## 6. ADR-26 — Transparent Scoring architecture

The scoring pipeline is separated into four bounded roles:

```text
versioned fixed Rubric
        ↓
LLM Dimension Judgment proposal
        ↓  (Kernel validates schema, scope, and provenance)
Dimension Judgment Artifact
        ↓
Deterministic Aggregator
        ↓
Transparent Score Artifact
```

The LLM is a restricted semantic-judgment provider, not an Artifact writer,
research tool, weighting authority, total-score calculator, or final-ranking
authority. It may propose a score only for a Rubric-defined dimension and only
with validated Claim/Evidence references in the permitted scope.

The Runtime is the sole writer and owns fixed aggregation, content hashes,
weights, missing-value behavior, final score/rank, and audit lineage. A legal
Dimension Judgment minimally identifies competitor, Rubric/version, dimension,
judgment status, bounded score when scored, Claim/Evidence refs, and rationale.
An illegal score, unknown Rubric/dimension, hallucinated reference, unclosed
provenance chain, or malformed judgment fails closed before aggregation.

`competitor_ranking.score` remains Candidate Selection policy data and is
strictly distinct from the future Transparent Score Artifact.

## 7. Open design decisions and implementation gate

Future Contract evolution may add new Rubric Versions, dimensions, Chart
Template IDs, or renderer behavior only through a new complete versioned
Bundle. The initial selected Rubric Catalogue and native Chart Template
Registry are specified in §8.5 and §8.6; no per-Run tuning is permitted.

No implementation claim is made for Fact Provenance Materialization, Report
Publisher/Builder, Citation UI, Scoring Judge, Aggregator, Renderer, Verifier,
Retry/Return, or any end-to-end workflow. The staged `0.3.1` static Contract
Closure is separately validated; Runtime, integration, and end-to-end evidence
remain future required evidence.

## 8. Approved decision details — 2026-08-30

### 8.1 ADR-24a — Hybrid Fact Provenance representation

The `0.3.1` Fact Provenance representation is hybrid:

```text
Kernel-owned state-versioned private sidecar
  Source / Evidence / Claim / fact_bindings
                  ↓
P0-04-T18 deterministic materializer
                  ↓
typed immutable report_projection Artifact
                  ↓
HTML Builder / Score pipeline / Verifier
```

The sidecar is the recoverable, state-version-authoritative binding source.
The typed `report_projection` Artifact is the manifest-tracked, Builder-facing
snapshot. It is written at
`artifacts/02-research/competitors/report-projection.json` by the
Kernel-owned T18 materializer after all required upstream facts are verified.

Each binding must contain stable fact identity, origin Artifact ref, origin
field pointer, Claim refs, Evidence refs, Source refs, fact class, and content
identity. The Projection must contain only renderable facts, deterministic
Fact Groups/DOM scopes, and the exact minimal Citation Closure. If an upstream
Artifact invalidates, its Projection and downstream Report/Score projections
invalidate; resume reads the effective sidecar for the persisted Snapshot
state and verifies the current Projection ref. A Builder may not substitute a
different state, sidecar, Bundle, or Projection.

### 8.2 ADR-26a — Profile Rubric and deterministic aggregation

One static versioned Rubric is selected by `profile_ref`. Each Rubric defines
its own dimensions, integer `1..10` score bands, allowed Fact/Claim/Evidence
scope, weights summing to `1.0`, and the profile-specific version. Decimal
Dimension Judgments are invalid. The selected Rubric applies only to the
current Profile and does not establish cross-Profile score comparability.

The Aggregator computes a weighted arithmetic total only if the weight of
legal completed dimensions is at least `0.80`. It renormalizes available
weights to `1.0`, records configured and effective weights, missing dimension
IDs, coverage, and `PARTIAL` status. Below `0.80`, `final_score` and final
rank are absent. Equal total scores order by higher verified Evidence coverage;
equal coverage retains a shared rank. `competitor_ranking.score` remains
outside this pipeline and cannot become an input to it.

The exact per-Profile dimension IDs, score-band prose, allowed Evidence scope,
and numeric weights are intentionally still unset. They are blocking Rubric
decisions, not implementation defaults.

### 8.3 ADR-26b — Independent Score Verifier and recovery

The scoring Judge and Score Verifier are independent semantic roles. The
Verifier receives only the same fixed Rubric, approved Projection Closure, and
proposed Dimension Judgment; it returns accept/reject/retry and cannot conduct
Research, introduce Claims/Evidence/Sources, alter Rubric/weights, calculate a
total, or write Runtime state directly.

Malformed/unclosed/out-of-range Judgments, provider failure, or verifier
rejection use bounded retry from the current `max_retries_per_node` policy.
After exhaustion, Runtime opens a targeted Research Gap and records the
dimension as unresolved without a legal score. Aggregate behavior then follows
the approved `80%` coverage rule. Concrete provider/model deployment remains
an implementation configuration, but must preserve role independence and the
no-write/no-research boundary.

### 8.4 ADR-21a — Native SVG renderer with PARTIAL PNG export

The chosen Renderer is a Runtime-owned native SVG-first implementation with a
future Contract-defined supported Chart Spec subset. It emits canonical local
SVG and has no cross-renderer fallback. Invalid or missing SVG is fatal to the
Chart Bundle and final verified Report; retries are bounded and exhaustion
routes to the visualization Research Gap.

PNG is generated only for an explicit compatibility/export requirement. A PNG
failure after successful validated SVG does not replace or invalidate the SVG;
it is recorded as explicit `PARTIAL` compatibility-export state and must be
disclosed to verification/report consumers. The initial native Chart Spec
subset and SVG minimum are defined in ADR-21b; the PNG exporter implementation
remains future work.

### 8.5 ADR-26c — Equal-weight Profile Rubrics and immutable history

The initial `0.3.1` Bundle contains one Rubric file per Profile with five
integer `1..10` dimensions, each `weight: 0.20`, and weights summing exactly
to `1.0`. The complete selected catalog is:

| Profile | Dimension IDs |
|---|---|
| `developer_tool` | `workflow_fit`, `developer_experience`, `extensibility_integration`, `ai_capability`, `ecosystem_maturity` |
| `ai_agent_product` | `agent_capability`, `reliability_observability`, `tool_model_integration`, `cost_performance`, `ecosystem_momentum` |
| `consumer_app` | `user_experience`, `differentiation`, `engagement_retention_signal`, `trust_safety`, `value_monetization` |
| `b2b_saas` | `workflow_fit`, `integration_maturity`, `security_compliance`, `commercial_fit`, `differentiation` |

Every dimension permits only its declared Fact/Claim/Evidence focus: workflow,
developer experience, UX, product capability, integration, pricing/value,
security/compliance, observed traction, feedback, technology, or ecosystem
facts as semantically applicable to that dimension. A legal score requires at
least one Rubric-permitted validated Claim, Evidence, and Source; all other
facts are rejected as out of scope. The common score bands are `1–2`
insufficient/negative, `3–4` limited, `5–6` baseline, `7–8` strong, and
`9–10` clearly leading with multiple direct supporting Evidence.

Weights are immutable within a Rubric Version. A changed weight map must
replace all five weights for the affected Profile in a new self-contained
Rubric Version, preserve the prior version and a short change rationale in the
same file, and pass a load-time `sum(weights) == 1.0` check. Per-Run,
per-competitor, per-Report, or one-dimension tuning is prohibited.

Before publishing a changed weight version, a review-only replay evaluates one
or two representative historical reports, including at least one `PARTIAL`
case. It records old/new score/rank/coverage behavior and the product rationale
for any change. The replay writes no Artifact, Report, Manifest, or Snapshot.
Unexplained rank shifts or unacceptable PARTIAL coverage changes reject or
revise the proposed version. New Rubric Versions apply prospectively only;
old Score Artifacts/Reports retain their original Rubric Version unless a user
explicitly starts a new re-score that produces new append-only Artifacts.

### 8.6 ADR-21b — Fixed Native Chart Template Registry and SVG minimum

The initial native Chart Template Registry is closed:

| `renderer_kind` | Registered `chart_id` | Required data contract |
|---|---|---|
| `matrix` | `feature_matrix`, `feature_ux_matrix`, `capability_matrix`, `integration_security_coverage` | `competitor_id`, `dimension_id`, `value`, `evidence_refs` |
| `scatter` | `positioning_map` | `competitor_id`, `x_value`, `y_value`, `x_label`, `y_label`, `evidence_refs` |
| `bar` | `momentum_comparison`, `ecosystem_momentum`, `cost_performance`, `pricing_comparison` | category, value, optional series, `evidence_refs` |
| `line` | `oss_activity` | timestamp, value, optional series, `evidence_refs` |
| `distribution` | `sentiment_distribution` | bucket, count, `evidence_refs` |

Every Chart Spec selects exactly one registered `chart_id` and its fixed
`renderer_kind`; no arbitrary grammar, renderer kind substitution, or
unregistered chart is allowed. The native Renderer validates the registered
data contract before SVG generation. Mismatch is `SCHEMA_INVALID`, not a
fallback opportunity.

Every canonical SVG must be local, static, and contain `viewBox`, `role="img"`,
`<title>`, and `<desc>`. It may contain only local geometry/text/style content
and MUST NOT contain `script`, `foreignObject`, event handler attributes,
remote/image href, external CSS import, or network dependency. PNG export is
separate from these SVG conditions and remains optional/partial as ADR-21a
defines.
