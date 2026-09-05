# Product Discovery SkillGraph — PRD v0.3.1 Design Amendment

> Status: **Approved design amendment with a staged static Bundle closure; not registered, frozen, activated, or Runtime-implemented.**  
> Predecessor: `PRD_v0.3.md` (frozen and preserved byte-for-byte).  
> Intended Contract target: `0.3.1`, which must be a complete independent Bundle before any Registry promotion.

## 1. Inheritance and precedence

This is a narrow design Amendment, not a rewrite of v0.3. It inherits every
v0.3 Product, Report/Chart Artifact, HTML Bundle, Version Lifecycle, Runtime,
Workflow, Research, Evidence, Verification, Human Gate, and v0.2 inherited
semantic except where it explicitly adds Report Publication, Fact-Level
Citation, or Transparent Scoring rules below.

`PRD_v0.3.md` remains the current frozen product Amendment for the implemented
`0.3.0` Runtime. This document records approved desired state only; it does
not make `0.3.1` a current/default Run version and does not prove a Builder,
Publisher, Renderer, Verifier, or Scoring implementation exists.

## 2. Report publication and presentation

### 2.1 Immutable Report Bundle Publisher

The final `competitor_report` remains the bundle-self-contained
`artifacts/02-research/competitors/competitor-report.html` presentation
surface. For `0.3.1`, publication is owned by a Runtime-managed Immutable
Report Bundle Publisher. It must atomically publish the root HTML, only
contained local SVG/CSS/static assets, and an auditable inventory/content-hash
record under the existing single-writer and append-only lifecycle.

The Publisher is not a Renderer, research source, or fact generator. It must
not select SVG/PNG generation technology, infer facts from SVG/HTML, access a
network, or introduce a Web Server, JavaScript runtime, React, ECharts,
Chart.js, D3, or Node.js Runtime.

### 2.2 Reference-first report

The HTML Report is a deterministic presentation of the complete verified fact
surface: Research Contract, Candidate and Ranking Artifacts, selected Deep
Dives, Normalized Dataset, four Analysis Artifacts, Source Index,
Source→Evidence→Claim Provenance, validated Chart Bundles/canonical local SVG,
and Product Profile. It may show only the minimum sufficient transitive
Citation Closure for facts actually rendered in the report.

The report does not include an entire Run Source Catalog merely because it is
available. It does not perform new research, fetch URL metadata, create
unsupported facts, or turn SVG/HTML/external URLs into fact sources.

### 2.3 Fact-Level Citation

External product, pricing, release, market, capability, numeric, selection,
Deep Dive, Analysis, Chart, and Table facts MUST resolve through:

```text
Rendered Fact / Dataset Field / Analysis Claim
                    ↓
                  Claim
                    ↓
                 Evidence
                    ↓
                  Source
```

System metadata, Artifact IDs/Refs, UI labels, navigation, and local
verification states such as `PASS`, `PARTIAL`, and `FAIL` do not require an
external Source Citation. A required cited fact with missing/dangling Claim,
Evidence, Source, or Citation-Closure membership fails Report Build closed;
the Builder must not hide, guess, or silently omit its Citation.

One explicit Fact Group MAY share Citation Badges only when every member has
the same verified Evidence/Source set and the group has a deterministic DOM
scope. Facts with different provenance MUST NOT be merged just to reduce
badges.

### 2.4 Inline Citation Badge and local preview

Every cited Fact or Fact Group renders one or more inline pill-style `<a>`
Citation Badges. Each `href` is the canonical URL from the validated Source
Record and is only a passive user navigation target; Report Build and offline
reading must not request it.

Badge text uses the Source Record's verified publisher short name. Hover and
keyboard focus show a locally pre-rendered Preview Card using the Source
Record's verified publisher short name, title, excerpt, and canonical URL.
Those values are projected verbatim as data and safely escaped; the Builder
must not summarize, rewrite, infer, or fetch them.

An existing validated local favicon MAY be shown. A missing or unavailable
favicon MUST gracefully degrade to no icon or a Bundle-local generic icon and
MUST NOT fail a Report Build or trigger network access.

## 3. Report successor ownership

The initial Builder publication records `Verification Summary: PENDING` and,
when no legal Transparent Score Artifact exists, `Scoring: NOT_PERFORMED`.

Later successor publications are constrained by section ownership:

- the Competitor Verifier may update only Verification Summary and its local
  verification reference;
- the Score Publisher may update only Scoring Methodology, dimension/final
  score projection, and its local score reference;
- neither may change Research facts, Dataset, Analysis, Evidence, Sources,
  Citations, Chart content, or unrelated Report sections.

Successors must use an explicit base Report version and CAS/idempotency rules.
They preserve prior versions for audit and fail on conflict rather than
silently overwrite another Publisher's section.

## 4. Transparent Scoring

Transparent Scoring is not a free-form LLM total score. Its approved model is:

```text
Validated Evidence / Dataset / Claim Closure
                    ↓
LLM Dimension Judgment under a fixed, versioned Rubric
                    ↓
Structured Dimension Judgment Artifact
                    ↓
Runtime-owned Deterministic Aggregator
                    ↓
Auditable Transparent Score Artifact
```

The LLM may make a semantic, dimension-level judgment only from facts and
Evidence/Claims allowed by the selected Rubric. It may not conduct Research,
add Sources/Evidence/Claims, choose weights, alter a score scale, calculate a
final total, or persist business state.

The Runtime owns schema validation, Rubric/version checks, Evidence/Claim/
Source closure checks, fixed weight/formula execution, missing-value behavior,
aggregation, final ranking, and append-only audit persistence. Every legal
score must trace:

```text
Final Score → Dimension Judgments → Rubric → Claim/Evidence → Source
```

Existing `competitor_ranking.score` remains the fixed Candidate Selection
policy score. It is not a Transparent Score and must never be presented as
one.

## 5. Approved boundary and open decisions

This Amendment approves the architecture and traceability requirements and the
selected Rubric, verifier, and renderer behavior in §7. Future changes must
be versioned rather than adjusted per Run or Report.

The following are also out of scope for this document-only synchronization:
actual `0.3.1` Contract Bundle closure, Registry promotion, Fact Provenance
Materialization, HTML Builder, Report Publisher, Renderer, Verifier, Scoring
Judge, Aggregator, tests, migrations, deployment, and Git release actions.

## 6. Intended lifecycle after complete closure

Only after a complete, validated `contracts/0.3.1/` Bundle and corresponding
Registry/Resolver work exist may the intended lifecycle become active:

```yaml
0.3.0:
  status: frozen_previous
  new_runs_allowed: false
  resume_allowed: true
  audit_allowed: true

0.3.1:
  status: current
  new_runs_allowed: true
  resume_allowed: true
  audit_allowed: true
```

Until then, observed Runtime lifecycle remains unchanged: `0.3.0` is the only
current/default new-run version, and no Run may resolve a nonexistent or
partial `0.3.1` Bundle.

## 7. Approved Decision Set — 2026-08-30

### 7.1 Fact Provenance and Report Projection

The approved representation is hybrid. Kernel remains the single writer of a
state-versioned private Fact Provenance sidecar that extends the existing
Source→Evidence→Claim record with field-level `fact_bindings`. `P0-04-T18`
then deterministically materializes a typed immutable `report_projection`
Artifact from that effective sidecar and the selected verified upstream
Artifacts. The HTML Builder reads the Projection, not arbitrary sidecar text,
to determine fact groups, DOM scope, and minimum Citation Closure.

The Projection does not create research facts. A missing binding for a
required cited fact is an evidence gap and fails the build closed; it cannot
be repaired by HTML, SVG, URL lookup, or Builder inference.

### 7.2 Profile-specific Transparent Scoring

Each selected Product Profile will own one fixed, versioned Rubric. Scores are
integer values from `1` through `10`; decimal scores are forbidden. The actual
dimension catalogue, definitions, permitted Evidence scopes, and weights must
be explicitly declared in each Profile Rubric before T10 implementation. A
score is comparable only inside the same Profile/Rubric version.

The Deterministic Aggregator requires at least `80%` of total configured
weight to have legal Dimension Judgments. It renormalizes only the available
weights to `1.0`, records original/effective weights and missing dimensions,
and emits a clearly disclosed `PARTIAL` result. Below `80%`, it emits no final
total score. Equal final scores are ordered by greater verified Evidence
coverage; if coverage is also equal, competitors share a rank.

### 7.3 Independent judgment verification and recovery

Every LLM Dimension Judgment is independently verified against the same
Rubric and Fact/Claim/Evidence/Source Closure. The verifier may accept,
reject, or request retry, but may not invent facts, alter weights, calculate a
free-form total, or write Report sections outside its declared artifact.

Provider failure, malformed output, unsupported score, disagreement, or
unclosed provenance uses the selected Run Policy's bounded retry allowance.
After exhaustion it opens a targeted Research Gap and produces no legal score
for that dimension. Any later aggregate follows the `80%` coverage rule; no
unresolved dimension is silently scored.

### 7.4 Native SVG-first renderer and optional PNG export

The future Renderer is Runtime-owned and renders a bounded native Chart Spec
subset directly to canonical SVG. It has no cross-renderer runtime fallback.
SVG generation/validation failure retries within the selected Run Policy and
then blocks final Report verification through the targeted visualization gap
path. PNG remains optional: absent PNG is valid when no export requirement
exists. When an explicit PNG compatibility/export request fails after valid
SVG output, the Chart Bundle/Report may remain usable only with a disclosed
`PARTIAL` compatibility-export state; PNG never substitutes for SVG.

### 7.5 Equal-weight Profile Rubric Catalogue and governance

The approved initial Profile Rubrics use five fixed dimensions at equal weight
`0.20` each. All Dimension Judgments are integers `1..10` with these common
bands: `1–2` clearly insufficient/negative Evidence; `3–4` limited or weakly
supported; `5–6` baseline capability; `7–8` strong verified capability; and
`9–10` multiple strong, direct, mutually supporting Evidence.

| Profile | Dimensions | Permitted evidence focus |
|---|---|---|
| `developer_tool` | `workflow_fit`, `developer_experience`, `extensibility_integration`, `ai_capability`, `ecosystem_maturity` | product workflow/features/integrations, technology capability, developer/user feedback, ecosystem/activity |
| `ai_agent_product` | `agent_capability`, `reliability_observability`, `tool_model_integration`, `cost_performance`, `ecosystem_momentum` | agent workflow, reliability/observability, tool/model integration, observed cost/performance, release/activity/technical ecosystem |
| `consumer_app` | `user_experience`, `differentiation`, `engagement_retention_signal`, `trust_safety`, `value_monetization` | UX/features, visible feedback, engagement/traction, policy/trust, pricing/value |
| `b2b_saas` | `workflow_fit`, `integration_maturity`, `security_compliance`, `commercial_fit`, `differentiation` | workflow/integration, security/compliance, pricing/license/procurement, competitive evidence |

Each dimension requires at least one Rubric-permitted validated Claim, its
Evidence, and a resolvable Source. The equal-weight map is the default
baseline, not a per-Run tuning knob. A weight change must replace the complete
five-dimension map of one Profile with a new Rubric Version, a short rationale,
and a same-file changelog; the new map MUST sum to `1.0` or be rejected.

Weight changes MUST NOT be made to change a specific competitor, Run, or
Report ranking. Before publishing a new Rubric Version, review it by replaying
one or two representative historical reports, including at least one `PARTIAL`
case. Record old/new score and rank changes and why they reflect the changed
product judgment. Replay is review-only: it creates no new Score Artifact,
does not modify historical Report/Manifest/Snapshot, and does not rescore old
Runs automatically. Unexplained ranking shifts or unacceptable `PARTIAL`
coverage changes require revising or abandoning the proposed version.

Every Score Artifact and Report Score section declares its self-contained
Rubric Version. A new Rubric Version affects only new Runs or an explicitly
requested re-score, which produces new Artifacts without changing history.

### 7.6 Native Chart Template Registry

The approved native Renderer supports a closed registry covering every current
Profile visualization ID:

| Renderer kind | Visualization IDs |
|---|---|
| `matrix` | `feature_matrix`, `feature_ux_matrix`, `capability_matrix`, `integration_security_coverage` |
| `scatter` | `positioning_map` |
| `bar` | `momentum_comparison`, `ecosystem_momentum`, `cost_performance`, `pricing_comparison` |
| `line` | `oss_activity` |
| `distribution` | `sentiment_distribution` |

Each Chart Spec declares a registered `chart_id`, its fixed `renderer_kind`, a
registered data contract, title, description, and local style/layout values.
Matrix rows require `competitor_id`, `dimension_id`, `value`, and
`evidence_refs`; scatter points require `competitor_id`, `x_value`, `y_value`,
axis labels, and `evidence_refs`; bars require category/value, optional series,
and `evidence_refs`; lines require timestamp/value, optional series, and
`evidence_refs`; distributions require bucket/count and `evidence_refs`.

The Renderer emits static local SVG only: it MUST include `viewBox`, `role`,
`<title>`, `<desc>`, and local static geometry/text; it MUST NOT include
script, `foreignObject`, event handlers, remote/image href, external CSS, or
network dependency. An unregistered ID/kind or mismatched data contract fails
closed as invalid Chart Spec; the Renderer must not silently substitute a
different kind or a PNG fallback.
