# Product Discovery SkillGraph — System / Workflow Spec v0.1

> 文档类型：Implementation Specification  
> 状态：Draft / Implementation-Ready Design Baseline  
> 版本：v0.1  
> 依赖 PRD：Product Discovery SkillGraph PRD v0.1
> 交付边界：本文档定义语言中立、可直接实现的 Contract，不表示 Runtime、真实 Research 或生产部署已经完成；Python 仅作为首个参考实现建议

---

# 1. Spec 目标

本文档定义 Product Discovery SkillGraph v0.1 的实现规范，包括：

- Runtime 架构
- Workflow Graph
- Node / Edge 模型
- Skill Contract
- Artifact Contract
- Evidence / Claim / Decision Schema
- Human Gate
- Verification / Loop
- Competitor Research Subgraph
- Competitor Dataset 与可视化 Pipeline
- State Machine
- Event Log
- Error Handling
- Versioning
- Directory Layout
- P0 Test / Acceptance

本 Spec 优先保证：

1. 可实现；
2. 可验证；
3. 可恢复；
4. 可扩展；
5. 不绑定某个特定 LLM / Agent Executor。

v0.1 的规范交付遵循：

`Core Workflow + Product Profile + Project Research Contract = Effective Workflow`

- Core Workflow 定义不可删除的产品发现骨架；
- Product Profile 调整研究支路启用状态、优先级、来源、阈值、必选图表和扩展节点；
- Project Research Contract 为当前项目定义具体问题，并记录经 Research Scope Gate 批准的调整；
- 本文所有公共 Workflow、Schema、CLI 和 API 使用语言中立的 `snake_case` 字段；Python 只作为非规范性参考实现。

---

# 2. Architecture Overview

```text
┌─────────────────────────────────────────────────────────┐
│                    User / Host Agent                    │
└───────────────────────────┬─────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────┐
│                    Orchestrator                         │
│ graph scheduler / dependency / gate / retry / routing   │
└───────────────────────────┬─────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────┐
│                       Skills                            │
│ research / normalize / analyze / verify / decide        │
└───────────────────────────┬─────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────┐
│                  Artifact Repository                    │
│ json / yaml / csv / md / chart spec / svg / png         │
└───────────────────────────┬─────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────┐
│                    Runtime State                        │
│ state.json / event-log.jsonl / decision-log.jsonl       │
└─────────────────────────────────────────────────────────┘
```

---

# 3. Runtime Responsibilities

Orchestrator 只负责：

- Load workflow
- Resolve dependencies
- Evaluate conditions
- Mark READY nodes
- Schedule runnable nodes
- Run independent nodes in parallel
- Pass Artifact references
- Persist Attempt result
- Run verifier
- Open Human Gate
- Retry failed / insufficient nodes
- Invalidate downstream on approved input changes
- Resume workflow from persisted state

Orchestrator 不负责：

- 自己做竞品研究；
- 自己输出市场结论；
- 自己决定产品方向；
- 自己生成未经过 Skill 的 Artifact。

---

# 4. Core Domain Model

## 4.1 Node

```yaml
id: competitor
kind: subgraph
subgraph: competitor-research
depends_on:
  - gate_research
required: true
```

`kind`:

- skill
- subgraph
- human_gate
- verifier
- router
- external_input

## 4.2 Edge

支持：

### Dependency

```yaml
depends_on:
  - market
```

### Conditional Execution

```yaml
depends_on:
  - verify
when:
  node: verify
  verification_result: FAIL
```

语义约束：

- `depends_on` 只表示拓扑依赖；
- `when` 只表示该依赖满足后是否启用节点；
- 使用 `when.node` 时，该节点必须同时出现在 `depends_on` 中；
- OR 条件统一使用 `when.any_of`，其中每个 predicate 的 `node` 都必须出现在 `depends_on` 中；
- 每个 predicate 必须且只能使用与上游节点类型匹配的一个结果字段：`node_status`、`verification_result`、`gate_decision`、`feasibility_result` 或 `proof_outcome`；值可以是单值或列表；
- `condition` 不是 v0.1 Workflow Schema 的合法字段；
- `activation` 不是 v0.1 Workflow Schema 的合法字段；
- 条件未命中时，节点标记为 `SKIPPED`，并记录 `CONDITION_NOT_MATCHED`，不能一直停留在 `PENDING`。

### Fan-out

一个上游节点产生多个并行后继。

### Fan-in

多个 Research 节点全部完成后进入 Verify。

---

# 5. Workflow File

建议：

`workflow.yaml`

```yaml
workflow:
  id: product-discovery
  version: 0.1.0
  schema_version: 0.1.0

policies:
  max_retries_per_node: 2
  max_global_research_cycles: 2
  max_parallel: 4
  automated_attempt_timeout_minutes: 20
  max_sources_per_research_node: 50
  automated_run_timeout_minutes: 120

nodes:
  idea:
    kind: skill
    skill: idea-intake
    required: true

  contract:
    kind: skill
    skill: research-contract
    depends_on: [idea]
    required: true

  gate_research:
    kind: human_gate
    gate: research-scope
    depends_on: [contract]

  competitor:
    kind: subgraph
    subgraph: competitor-research
    depends_on: [gate_research]
    required: true
    configurable_by_profile: true

  users:
    kind: skill
    skill: user-evidence
    depends_on: [gate_research]
    required: true
    configurable_by_profile: true

  market:
    kind: skill
    skill: market-landscape
    depends_on: [gate_research]
    required: true
    configurable_by_profile: true

  technology:
    kind: skill
    skill: oss-tech-landscape
    depends_on: [gate_research]
    required: true
    configurable_by_profile: true

  research_verifier:
    kind: verifier
    skill: research-verifier
    depends_on:
      - competitor
      - users
      - market
      - technology

  research_gap:
    kind: skill
    skill: research-gap
    depends_on: [research_verifier, evidence_waiver]
    when:
      any_of:
        - node: research_verifier
          verification_result: FAIL
        - node: evidence_waiver
          gate_decision: REQUEST_MORE_RESEARCH
    loop:
      retry_targets_from: artifacts/03-analysis/research-gap.yaml
      invalidate_from_gap: true
      always_invalidate:
        - research_verifier
        - evidence_waiver
      return_to: research_verifier

  evidence_waiver:
    kind: human_gate
    gate: evidence-waiver
    depends_on: [research_verifier]
    required: false
    when:
      node: research_verifier
      verification_result: PARTIAL

  research_synthesis:
    kind: skill
    skill: research-synthesis
    depends_on: [research_verifier, evidence_waiver]
    when:
      any_of:
        - node: research_verifier
          verification_result: PASS
        - node: evidence_waiver
          gate_decision: PARTIAL_ACCEPTED

  opportunity:
    kind: skill
    skill: opportunity-mapping
    depends_on: [research_synthesis]

  gate_direction:
    kind: human_gate
    gate: product-direction
    depends_on: [opportunity]

  definition:
    kind: skill
    skill: product-definition
    depends_on: [gate_direction]

  feasibility:
    kind: skill
    skill: feasibility-review
    depends_on: [definition]

  proof:
    kind: skill
    skill: proof-planner
    depends_on: [feasibility]
    when:
      node: feasibility
      feasibility_result: BLOCKED

  proof_result:
    kind: external_input
    contract: proof-result
    depends_on: [proof]
    when:
      node: proof
      node_status: VERIFIED
    wait_status: WAITING_FOR_EXTERNAL
    on_submit:
      validate: proof-result.schema.json
      invalidate: [feasibility]
      return_to: feasibility

  scope:
    kind: skill
    skill: mvp-scope
    depends_on: [feasibility]
    when:
      node: feasibility
      feasibility_result:
        - FEASIBLE
        - CONDITIONALLY_FEASIBLE

  gate_scope:
    kind: human_gate
    gate: mvp-scope
    depends_on: [scope]

  prd:
    kind: skill
    skill: prd-generator
    depends_on: [gate_scope]

  prd_consistency_verifier:
    kind: verifier
    skill: prd-consistency-verifier
    depends_on: [prd]

  build_readiness_verifier:
    kind: verifier
    skill: build-readiness-verifier
    depends_on: [prd_consistency_verifier]
    trigger_on_terminal_events:
      - CRITICAL_RESEARCH_BLOCKER
      - FEASIBILITY_NOT_FEASIBLE
      - REQUIRED_PROOF_FAILED
      - PRD_CONSISTENCY_FAILED
```

Core Workflow 中以下节点不可被 Profile 删除：`idea`、`contract`、`gate_research`、`research_verifier`、`research_gap`、`evidence_waiver`、`research_synthesis`、`opportunity`、`gate_direction`、`definition`、`feasibility`、`proof`、`proof_result`、`scope`、`gate_scope`、`prd`、`prd_consistency_verifier`、`build_readiness_verifier`。条件节点可以不激活，但仍必须保留在合成后的图定义中。

`competitor`、`users`、`market`、`technology` 是 Profile 可配置研究支路。Profile 禁用支路时，Runtime 将其标记为 `SKIPPED`，原因是 `PROFILE_DISABLED`，并保存 Profile ID、版本和 Research Contract Decision；Build Readiness 只检查 Effective Workflow 中的 required 支路。

`research_synthesis` 的 `when.any_of` 是 v0.1 对“PASS 或已接受 PARTIAL”这一汇合条件的规范表达。Runtime 不得把 `PARTIAL` 自动转换为 `PARTIAL_ACCEPTED`。

`trigger_on_terminal_events` 是 Build Readiness Verifier 的受限系统触发器，不是普通 Skill 可用的条件语法。触发后，未进入的下游节点先以 `SKIPPED / TERMINAL_BRANCH_NOT_SELECTED` 收束，Build Readiness Verifier 再根据当前全部有效 Artifact 输出 `NOT_READY`。因此 critical Research、`NOT_FEASIBLE`、required Proof 失败或 PRD Consistency 失败不会让 Workflow 停在无终态的位置。

---

# 6. State / Result / Decision Model

不同领域的枚举不得混用。

## 6.1 Node Status

```text
PENDING
READY
RUNNING
COMPLETED
VERIFYING
VERIFIED
WAITING_FOR_USER
WAITING_FOR_EXTERNAL
APPROVED
BLOCKED
FAILED
RETRY_READY
SKIPPED
INVALIDATED
```

`PARTIAL` 不是 Node Status。

## 6.2 Verification Result

```text
PASS
PARTIAL
FAIL
```

## 6.3 Gate Decision

通用：

```text
APPROVE
MODIFY
CANCEL
```

Product Direction：

```text
SELECT_OTHER
REQUEST_MORE_RESEARCH
```

Evidence Waiver：

```text
PARTIAL_ACCEPTED
REQUEST_MORE_RESEARCH
CANCEL
```

`PARTIAL_ACCEPTED` 只是一条 Gate Decision；Gate Node 成功处理后进入 `APPROVED`。

## 6.4 Feasibility Result

```text
FEASIBLE
CONDITIONALLY_FEASIBLE
BLOCKED
NOT_FEASIBLE
```

## 6.5 Workflow Status

```text
CREATED
RUNNING
WAITING_FOR_USER
WAITING_FOR_EXTERNAL
PAUSED
COMPLETED
CANCELLED
FAILED
```

## 6.6 Readiness Status

```text
READY_FOR_BUILD
READY_WITH_ACCEPTED_RISKS
NOT_READY
```

## 6.7 Node Transitions

主路径：

```text
PENDING
  ↓
READY
  ↓
RUNNING
  ↓
COMPLETED
  ↓
VERIFYING
  ↓
VERIFIED
```

失败：

```text
RUNNING
  ↓
FAILED
  ↓
RETRY_READY
  ↓
RUNNING
```

Human Gate：

```text
READY
 ↓
WAITING_FOR_USER
 ↓
APPROVED
```

External Input：

```text
READY
 ↓
WAITING_FOR_EXTERNAL
 ↓
COMPLETED
 ↓
VERIFYING
 ↓
VERIFIED
```

修改上游决策：

```text
VERIFIED
 ↓
INVALIDATED
```

`SKIPPED` 只可由 `PROFILE_DISABLED`、`CONDITION_NOT_MATCHED` 或 optional 节点的已批准 Skip 产生。对于依赖计算，`SKIPPED` 只有在该节点不是 Effective Workflow 的 required 节点时才视为已满足依赖。

---

# 7. Runtime State Schema

`runtime/state.json`

```json
{
  "schema_version": "0.1.0",
  "workflow_id": "product-discovery",
  "workflow_version": "0.1.0",
  "run_id": "run_20260808_001",
  "state_version": 1,
  "workflow_status": "RUNNING",
  "readiness_status": null,
  "current_gate": null,
  "global_research_cycle": 1,
  "profile_ref": "developer_tool@0.1.0",
  "research_contract_ref": "ART-CONTRACT-001@1",
  "nodes": {
    "idea": {
      "status": "VERIFIED",
      "attempt_count": 1,
      "artifact_refs": [
        "artifacts/00-intake/idea-definition.yaml"
      ]
    },
    "competitor": {
      "status": "RUNNING",
      "attempt_count": 1,
      "artifact_refs": []
    }
  }
}
```

---

# 8. Attempt Model

每次 Skill 执行都生成 Attempt。

```yaml
attempt:
  id: ATT-00017
  run_id: run_20260808_001
  node_id: competitor
  skill_id: competitor-research
  skill_version: 0.1.0
  started_at:
  finished_at:
  status: COMPLETED
  input_artifacts:
    - ...
  output_artifacts:
    - ...
  executor:
    adapter_type: host_agent
    adapter_id:
    model_id:
  input_fingerprint:
  usage:
    automated_duration_seconds:
    source_count:
    input_tokens:
    output_tokens:
    estimated_cost:
  error:
    code:
    message:
```

目的：

- Retry 可追踪；
- 不覆盖历史 Attempt；
- Artifact 可知道由哪个 Attempt 生成。

---

# 9. Standard Skill Contract

每个 `skills/<skill>/SKILL.md` 必须声明以下 sections：

```markdown
# Skill: <id>

## Purpose

## Trigger

## Inputs

## Reads

## Tasks

## Required Outputs

## Evidence Rules

## Completion Criteria

## Verification

## Failure Conditions

## Retry Strategy

## Forbidden Behavior

## Permissions

## Budget

## Executor Requirements

## Next
```

机器可读部分必须放在：

`skill.yaml`

```yaml
skill:
  id: competitor-discovery
  version: 0.1.0
  type: research

inputs:
  required:
    - idea_definition
    - research_contract

reads:
  - artifacts/00-intake/idea-definition.yaml
  - artifacts/01-contract/research-contract.yaml

writes:
  - artifacts/02-research/competitors/candidates.json

output_contracts:
  - artifact_type: competitor_candidates
    write: artifacts/02-research/competitors/candidates.json
    schema_ref: schemas/competitor.schema.json#/$defs/competitor_candidates
    template_ref: null

evidence:
  required: true
  provenance_required: true

permissions:
  external_access: read_only
  workspace_write:
    - artifacts/02-research/competitors/
  secrets: forbidden

budget:
  timeout_minutes: 20
  max_sources: 50

executor:
  allowed_adapter_types:
    - fixture
    - manual
    - host_agent

completion:
  direct_competitors:
    min_if_available: 3
  source_types:
    min: 2

on_failure:
  - emit_research_gap
```

`output_contracts` 是所有 v0.1 `skill.yaml` 的必填数组。每项必须声明 `artifact_type`、`write` 和支持可选 JSON Pointer 的仓库内 `schema_ref`；`template_ref` 可以为 `null`，或指向 `templates/*.md`。`output_contracts[*].write` 去重后的集合必须与顶层 `writes` 完全一致，避免出现未声明写入或没有输出契约约束的写路径。Template 只约束 Markdown 表达层，不替代结构化 Artifact Schema。

---

# 10. Artifact Contract

所有 Artifact 必须带 Metadata Header。

YAML 示例：

```yaml
artifact:
  id: ART-001
  type: idea_definition
  schema_version: 0.1.0
  produced_by:
    skill: idea-intake
    attempt: ATT-00001
  created_at:
  supersedes: null
  status: active
```

Artifact 原则：

- append history，不静默覆盖；
- 当前有效版本由 `runtime/current-manifest.json` 指向；
- 下游读取明确版本；
- schema_version 必填；
- 允许 partial / null；
- Artifact、Attempt、Event 与 Decision 都是 append-only；
- 单个 Run 只允许一个 Orchestrator Writer；
- 写入新版本后，先 `fsync` / flush 临时文件，再通过同一文件系统内的原子 rename / replace 更新目标文件和 Current Manifest；
- Crash 发生在 Manifest 更新前时，旧指针继续有效；孤立的新版本由恢复流程登记，不得静默删除。

`artifact.schema.json` 是基础 Metadata Header 契约：它严格校验 `artifact` Header，但允许 Artifact Type 在顶层增加自己的 Payload 字段。后续 `idea`、`competitor`、`research`、`chart` 等类型 Schema 必须通过组合方式进一步约束这些字段，不能放宽基础 Header。

---

# 11. Directory Layout

```text
product-discovery/
├── README.md
├── workflow.yaml
│
├── subgraphs/
│   └── competitor-research.yaml
│
├── profiles/
│   ├── developer-tool.yaml
│   ├── ai-agent-product.yaml
│   ├── consumer-app.yaml
│   └── b2b-saas.yaml
│
├── skills/
│   ├── idea-intake/
│   │   ├── SKILL.md
│   │   └── skill.yaml
│   ├── research-contract/
│   ├── competitor-discovery/
│   ├── competitor-ranking/
│   ├── competitor-deep-dive/
│   ├── competitor-normalizer/
│   ├── competitor-analysis/
│   ├── competitor-visualization/
│   ├── competitor-verifier/
│   ├── user-evidence/
│   ├── market-landscape/
│   ├── oss-tech-landscape/
│   ├── research-verifier/
│   ├── research-gap/
│   ├── research-synthesis/
│   ├── opportunity-mapping/
│   ├── product-definition/
│   ├── feasibility-review/
│   ├── proof-planner/
│   ├── mvp-scope/
│   ├── prd-generator/
│   ├── prd-consistency-verifier/
│   └── build-readiness-verifier/
│
├── schemas/
│   ├── common.schema.json
│   ├── workflow.schema.json
│   ├── subgraph.schema.json
│   ├── artifact.schema.json
│   ├── idea.schema.json
│   ├── source.schema.json
│   ├── evidence.schema.json
│   ├── claim.schema.json
│   ├── competitor.schema.json
│   ├── research.schema.json
│   ├── decision.schema.json
│   ├── profile.schema.json
│   ├── run-policy.schema.json
│   ├── gate.schema.json
│   ├── verification.schema.json
│   ├── executor-request.schema.json
│   ├── executor-result.schema.json
│   ├── proof-result.schema.json
│   ├── artifact-manifest.schema.json
│   ├── readiness-result.schema.json
│   ├── chart.schema.json
│   ├── skill.schema.json
│   └── workflow-state.schema.json
│
├── templates/
│   ├── competitor-report.md
│   ├── synthesis.md
│   ├── product-definition.md
│   ├── feasibility.md
│   └── prd.md
│
├── runtime/
│   ├── state.json
│   ├── current-manifest.json
│   ├── event-log.jsonl
│   ├── decision-log.jsonl
│   └── attempts/
│
├── fixtures/
│   ├── codex-progress-observability/
│   ├── api-dependency-change-monitor/
│   ├── support-ticket-agent/
│   ├── shared-household-planner/
│   └── vendor-security-questionnaire-saas/
│
└── artifacts/
    ├── 00-intake/
    ├── 01-contract/
    ├── 02-research/
    │   └── source-index.json
    ├── 03-analysis/
    ├── 04-decisions/
    ├── 05-product/
    ├── 06-feasibility/
    └── 07-prd/
```

五个 v0.1 Markdown Template 必须以可安全解析的 YAML front matter 开头：

```yaml
---
template:
  id: competitor-report
  version: 0.1.0
  artifact_type: competitor_report
---
```

`template.id` 必须等于文件名去掉 `.md` 后的 stem，`version` 固定为 `0.1.0`。规范映射为：`competitor-report.md → competitor_report`、`synthesis.md → research_synthesis`、`product-definition.md → product_definition`、`feasibility.md → feasibility_review`、`prd.md → prd`。Skill 通过 `output_contracts[*].template_ref` 引用 Template；Template 只负责 Markdown 结构，不替代或放宽同一输出的 `schema_ref`。

---

# 12. Idea Definition Schema

```yaml
artifact:
  type: idea_definition

idea:
  original:

problem:
  statement:

target_users:
  primary: []
  secondary: []

proposed_solution: []

assumptions:
  - id:
    claim:
    status: unvalidated

unknowns: []

non_goals: []

confidence:
  overall: low
```

---

# 13. Research Contract Schema

```yaml
artifact:
  type: research_contract

profile_ref: developer_tool@0.1.0

effective_research:
  competitor: required
  users: required
  market: required
  technology: required

research_questions:
  competitors: []
  users: []
  market: []
  technology: []

required_evidence:
  competitor_count: 5
  primary_sources: 8
  user_evidence_items: 15
  oss_projects: 5

required_visualizations:
  - feature_matrix
  - positioning_map
  - momentum_comparison
  - oss_activity

profile_adjustments:
  - field:
    profile_default:
    requested_value:
    rationale:
    decision_id:

run_policy:
  max_parallel: 4
  automated_attempt_timeout_minutes: 20
  max_sources_per_research_node: 50
  max_retries_per_node: 2
  max_global_research_cycles: 2
  automated_run_timeout_minutes: 120
  host_token_limit:
  host_cost_limit:

stop_conditions:
  max_research_loops: 2
```

Profile 默认值的任何放宽都必须出现在 `profile_adjustments` 中，并由 Research Scope Gate 批准。Contract 不得超过 Host 提供的 Token、费用、网络或文件权限硬上限。

---

# 14. Source and Evidence Model

## 14.1 Source Index / Source Schema

每个 Run 维护一个独立的 `artifacts/02-research/source-index.json`。Source 去重键优先使用 canonical URL；无法得到稳定 URL 时使用 publisher、title、published_at 与 content_hash 的组合。

```yaml
source:
  id: SRC-001
  source_type: official_documentation
  canonical_url:
  title:
  publisher:
  author:
  published_at:
  accessed_at:
  source_tier: 1
  access_status: public
  license_or_access_notes:
  content_hash:
  excerpt_or_summary:
  excerpt_word_count:
  freshness_status: FRESH
  untrusted_content: true
  contains_personal_data: false
```

默认只保存元数据、内容哈希和支持 Claim 所需的最小短摘录或摘要，不镜像全文。不得保存登录、付费墙、无权访问的内容、秘密或非必要 PII。外部文本始终是 untrusted data，不得改变 System、Workflow、Skill 或权限指令。

## 14.2 Evidence Schema

```yaml
evidence:
  id: EV-001

  claim_id: CL-001

  source_id: SRC-001

  evidence_type:
    qualitative

  direction:
    supports

  relevance:
    high

  reliability:
    medium

  freshness:
    high

  notes:
```

Enums：

`direction`:

- supports
- contradicts
- contextual

`reliability`:

- high
- medium
- low

---

# 15. Claim Schema

```yaml
claim:
  id: CL-001

  statement:

  category:
    - user
    - competitor
    - market
    - technology
    - product

  status:
    - VALIDATED
    - PARTIALLY_VALIDATED
    - INVALIDATED
    - UNKNOWN

  confidence:
    - HIGH
    - MEDIUM
    - LOW
    - INSUFFICIENT

  evidence_ids: []

  contradiction_ids: []
```

禁止使用伪精确 confidence，例如 87.4%，除非来源于真实统计模型。

---

# 16. Decision Schema

```yaml
decision:
  id: DEC-003
  date:

  gate_id:

  question:

  decision:

  rationale: []

  evidence_ids: []

  artifact_refs: []

  alternatives: []

  accepted_risks: []

  structured_diff_ref:

  reversible: true

  approved_by:
    type: user
    id:
```

自然语言 `MODIFY` 必须先形成 schema-valid Structured Diff Artifact。只有用户确认该 diff 后，Runtime 才能创建新 Artifact 版本、写 Decision Log 并执行 Downstream Invalidation；原始自然语言和确认后的 diff 都需要引用到同一个 Decision。

---

# 17. Source Hierarchy

默认：

## Tier 1

- Official Docs
- Official API
- Official Repository
- Filings
- Papers
- Original Dataset

## Tier 2

- GitHub Issues
- Product Reviews
- Reddit
- HN
- Interviews / Community Posts

## Tier 3

- News
- Analyst Reports
- Blogs

## Tier 4

- Aggregators
- Secondary summaries

Verifier 应结合 Claim 类型使用不同 Tier：

- Product capability → Tier 1 优先；
- User Pain → Tier 2 优先；
- Market trend → Tier 1 / 2 / 3 交叉。

Source Tier 是 claim-specific 的质量提示，不是全局绝对排名。例如，原始用户访谈对“该受访者的痛点”属于一手证据，但不能自动外推为市场总体发生率。LLM 推断、搜索摘要和未访问的链接不是独立 Source；只能标记为 derived analysis 或 discovery lead。

---

# 18. Competitor Research Subgraph

顶层 `competitor` 是 `kind: subgraph`，绑定 `subgraphs/competitor-research.yaml`。Orchestrator 将 Subgraph 视为一个顶层依赖单元，但必须持久化其内部 Node、Attempt、Artifact、Verification 和 Retry 状态。

`subgraphs/competitor-research.yaml` 必须通过 `schemas/subgraph.schema.json`。v0.1 Subgraph 的根形状固定为：

```yaml
subgraph:
  id: competitor-research
  version: 0.1.0
  schema_version: 0.1.0

inputs: []

output_contracts:
  - artifact_type: competitor_report
    producer: visualization

nodes: {}
```

顶层只允许 `subgraph`、`inputs`、`output_contracts` 和 `nodes`。每个输出项必须声明 `artifact_type` 和存在于 `nodes` 中的 `producer`；内部 Node 复用 `workflow.schema.json#/$defs/node` 的 kind/implementation 形状，并额外接受 Subgraph DAG、Skill 引用和输出 Producer 的跨文件语义检查。

内部固定实现映射为：`discovery → competitor-discovery`、`candidate_ranking → competitor-ranking`、`deep_dive → competitor-deep-dive`、`normalizer → competitor-normalizer`、四个 `*_analysis → competitor-analysis`、`visualization → competitor-visualization`、`competitor_verifier → competitor-verifier`。`competitor_verifier` 是 required、唯一终点的内部 `kind: verifier` 节点；它不新增顶层 Core Workflow Node。`competitor-verifier` 因此是目录蓝图中的第 23 个 Standard Skill Contract。

Subgraph 的 `competitor_verification` 输出必须由 `competitor_verifier` 产生；对应 Skill 的 `output_contracts` 必须引用 `schemas/verification.schema.json#/$defs/competitor_verification`。该输出契约负责要求内部 `retry_targets` 并将 `return_to` 固定为 Subgraph Node ID `competitor_verifier`，避免把 Retry/Return 控制字段误放进通用 Subgraph Node Shape。

```text
discovery
    ↓
candidate_ranking
    ↓
deep_dive
    ↓
normalizer
    ↓
 ┌──────────────┬────────────────┬─────────────┬────────────────┐
 ↓              ↓                ↓             ↓
feature_      traction_        review_       pricing_
analysis      analysis         analysis      analysis
 └──────────────┴────────┬───────┴─────────────┘
                         ↓
                   visualization
                         ↓
                competitor_verifier
                ↙        ↓        ↘
              FAIL    PARTIAL    PASS
               ↓         ↓         ↓
       targeted retry  propagate  report
```

Subgraph Contract：

- 输入：Idea Definition、Research Contract、Profile 与 Source Index；
- 输出：candidate set、ranking、每个入选竞品的 Deep Dive、normalized dataset、analysis、Profile-required visualizations、competitor report 与 verification result；
- `candidate_ranking` 必须保存 selection methodology 与被排除候选的理由；
- Deep Dive 使用 fan-out / fan-in，并受 `max_parallel` 约束；
- Verifier 的 gap 必须包含内部 `retry_targets` 和 `return_to: competitor_verifier`；
- 顶层 Subgraph 只有在内部 required 节点结束后才能产生 `PASS | PARTIAL | FAIL`。

---

# 19. Competitor Candidate Schema

```json
{
  "competitors": [
    {
      "id": "cmp_001",
      "name": "Example",
      "category": "direct",
      "homepage": null,
      "repository": null,
      "relevance_reason": "",
      "source_ids": []
    }
  ]
}
```

`category`:

- direct
- indirect
- substitute
- adjacent
- platform_risk

---

# 20. Competitor Deep Dive Schema

```yaml
competitor:
  id:
  name:
  category:

positioning:
  description:

target_users: []

product:
  core_workflow: []
  features: []
  integrations: []
  ux_model:

business:
  pricing:
  license:
  monetization:

traction:
  github_stars:
    value:
    observed_at:
    source_id:
  star_growth_30d:
    value:
    method:
    source_ids: []
  contributors:
  releases_90d:

user_feedback:
  positive: []
  negative: []

strengths: []
weaknesses: []

strategic_threat:
  level:
  reasoning:

source_ids: []
```

所有时变 metric 必须带 `observed_at`。

---

# 21. Competitor Dataset

最终统一：

```json
{
  "schema_version": "0.1.0",
  "generated_at": "",
  "competitors": [
    {
      "id": "cmp_001",
      "name": "Product A",
      "category": "direct",
      "metrics": {
        "feature_coverage": {
          "value": 0.78,
          "source": "derived"
        },
        "github_stars": {
          "value": 13000,
          "observed_at": "",
          "source_ids": ["SRC-001"]
        },
        "star_growth_30d": {
          "value": 0.21,
          "source_ids": ["SRC-002", "SRC-003"]
        },
        "sentiment_positive": {
          "value": 0.64,
          "sample_size": 81,
          "method": "classified_review_sample"
        }
      }
    }
  ]
}
```

缺失：

```json
{"value": null}
```

禁止填充虚构平均值。

---

# 22. Scoring Methodology

例如：

`analysis/scoring-methodology.yaml`

```yaml
score:
  id: momentum_score
  version: 0.1

normalization:
  method: min_max
  range: [0, 100]

weights:
  star_growth_30d: 0.35
  contributor_growth_30d: 0.25
  release_activity_90d: 0.20
  issue_activity_30d: 0.20

missing_values:
  strategy: renormalize_available_weights

minimum_required_metrics: 2
```

若只有 1 个有效指标，不计算综合 Momentum Score，标记：

`INSUFFICIENT_DATA`

---

# 23. Visualization Pipeline

```text
competitor-dataset.json
         ↓
analysis metrics
         ↓
chart data
         ↓
chart-spec.json
         ↓
renderer
         ↓
SVG / PNG
         ↓
insight.md
```

推荐内部采用 declarative Chart Spec。

可使用：

- Vega-Lite
- 兼容宿主环境的其他 JSON Chart Spec

但必须保留 renderer-independent 的 `data.json`。

---

# 24. Chart Artifact Contract

```text
visualizations/
└── momentum-comparison/
    ├── data.json
    ├── chart-spec.json
    ├── chart.svg
    ├── chart.png
    └── insight.md
```

`insight.md`：

```yaml
chart:
  id: chart_momentum_001
  type: momentum_comparison

observation:

interpretation:

product_implication:

confidence: MEDIUM

evidence_ids:
  - EV-001
  - EV-014

limitations: []
```

---

# 25. Profile-Specific Competitor Visualizations

所有 Profile 都必须先生成 normalized competitor dataset。默认图表 Contract：

| Profile | Required visualizations |
|---|---|
| `developer_tool` | `feature_matrix`、`positioning_map`、`momentum_comparison`、`oss_activity` |
| `ai_agent_product` | `capability_matrix`、`positioning_map`、`cost_performance`、`ecosystem_momentum` |
| `consumer_app` | `feature_ux_matrix`、`positioning_map`、`pricing_comparison` 或 `sentiment_distribution`；第三张由 Research Contract 预选 |
| `b2b_saas` | `feature_matrix`、`positioning_map`、`pricing_comparison`、`integration_security_coverage` |

Research Contract 可以在 Research Scope Gate 中说明理由后调整。运行中数据不足时必须产生 Gap 或 Evidence Waiver，不能自动降低图表数量。

## 25.1 Feature Coverage Matrix

数据必须来源于统一 Feature Taxonomy。

示例：

```yaml
features:
  - id: graph
    label: Execution Graph

coverage:
  cmp_a:
    graph: 1.0
  cmp_b:
    graph: 0.5
```

建议取值：

- 0 = absent
- 0.5 = partial
- 1 = supported

不能仅依据模糊营销描述打分。

## 25.2 Positioning Map

必须记录坐标生成方法：

```yaml
axes:
  x:
    label: Runtime Control → Observability
    methodology:
  y:
    label: Low Automation → High Automation
    methodology:
```

若坐标来自人工 / LLM 定性编码，必须标记：

`derived_qualitative`

## 25.3 Momentum Comparison

优先使用变化量：

- Star Growth
- Contributor Growth
- Releases
- Issue Activity

而不是仅绝对 Stars。

## 25.4 Profile-Specific Charts

按上表和已批准的 Research Contract 生成。所有定性编码都必须标记 `derived_qualitative` 并引用 Evidence；没有足够数据时输出 `VISUALIZATION_DATA_INSUFFICIENT`，不得用 LLM 猜测补齐。

---

# 26. User Evidence Research

Artifact：

```json
{
  "items": [
    {
      "id": "UE-001",
      "pain": "execution opacity",
      "severity": 4,
      "frequency_signal": 3,
      "workaround": "manually inspect files",
      "willingness_signal": "unknown",
      "source_id": "SRC-090"
    }
  ]
}
```

注意：

`frequency_signal` 不是市场总体发生率，除非样本设计允许推断。

---

# 27. Market Landscape

建议输出：

```yaml
category:
  maturity:

why_now: []

why_not_now: []

drivers: []

barriers: []

business_model_patterns: []

platform_risks: []

unknowns: []
```

---

# 28. OSS / Technical Landscape

Schema：

```yaml
repositories:
  - id:
    name:
    url:
    stars:
    observed_at:
    license:
    maintenance:
    architecture_summary:
    reusable_components: []
    constraints: []

reuse_analysis:
  can_reuse: []
  should_not_rebuild: []
  should_not_copy: []
  differentiation_implications: []
```

---

# 29. Research Verifier

Verifier Input：

- Research Contract
- All required Research Artifacts
- Source Index
- Claims
- Required Visualization list

Checks：

```text
COVERAGE
SOURCE_PROVENANCE
SOURCE_QUALITY
FRESHNESS
CONTRADICTION
DATA_COMPLETENESS
VISUALIZATION_COMPLETENESS
```

Output：

```yaml
verification:
  overall: FAIL
  critical_issues: []
  non_critical_issues: []

sections:
  competitor:
    result: PASS

  users:
    result: FAIL
    issues:
      - code: INSUFFICIENT_WILLINGNESS_EVIDENCE

  market:
    result: PASS

  technology:
    result: PASS
```

判定规则：

- 每个 enabled section 读取 Research Contract 中的 required Artifact、最低 Evidence / Source 数量、Freshness、Contradiction 与 Visualization 门槛；
- 任一 required Artifact 缺失、Source provenance 缺失，或安全、合规、数据完整性、核心可行性 check 失败时，section 为 `FAIL`；
- 只有 non-critical check 未完全满足时，section 才可为 `PARTIAL`；
- 所有 required section 为 `PASS` 时 overall 为 `PASS`；任一 section 为 `FAIL` 时 overall 为 `FAIL`；否则 overall 为 `PARTIAL`；
- disabled section 不参与 overall，但必须有 `PROFILE_DISABLED` 记录；
- Verifier 不得使用加权总分掩盖 critical failure。

---

# 30. Research Gap Planner

输入 Verification Issues。

输出：

```yaml
gaps:
  - id: GAP-01
    issue_code: INSUFFICIENT_WILLINGNESS_EVIDENCE
    target_skill: user-evidence
    required_action:
      - search adoption intent
      - search workaround behavior
    reuse_artifacts:
      - existing-user-evidence.json
    invalidate:
      - research_verifier
      - evidence_waiver
      - research_synthesis
    retry_targets:
      - users
    return_to: research_verifier
```

执行 Gap 会增加 `global_research_cycle`；目标 Node 的一次实际重跑会增加其 Attempt Count。每次 Gap 都失效旧的 Research Verification 与 Evidence Waiver 状态，再按 gap 明确的依赖范围失效下游；既有 Attempt、Source 和未受影响 Artifact 保留。

---

# 31. Loop Algorithm

伪代码：

```text
if verifier == PASS:
    continue

if verifier == PARTIAL:
    if any issue is critical:
        treat as FAIL
    else:
        open evidence_waiver gate
        if decision == REQUEST_MORE_RESEARCH:
            gap_plan()
        if decision == PARTIAL_ACCEPTED:
            continue to synthesis
        if decision == CANCEL:
            cancel run

if verifier == FAIL:
    if retry_count < max_retries:
        run(targeted_gap_nodes)
        verify_again
    else:
        if remaining gaps are non-critical:
            open evidence_waiver gate
        else:
            readiness = NOT_READY
```

禁止：

```text
while evidence_not_enough:
    research_everything_again()
```

---

# 32. Human Gate Contract

Gate Artifact：

```yaml
gate:
  id: gate_direction
  status: WAITING_FOR_USER
  gate_type: product_direction

question:
  "Which product direction should be selected?"

options:
  - id: A
  - id: B

recommendation:
  option: B

input_artifact_refs: []

risks: []

proposed_structured_diff_ref:

allowed_actions:
  - APPROVE
  - SELECT_OTHER
  - REQUEST_MORE_RESEARCH
  - MODIFY
  - CANCEL
```

三个标准 Gate 分别是 Research Scope、Product Direction、MVP Scope；Evidence Waiver 是仅在 `PARTIAL` 时激活的条件式 Gate。

Evidence Waiver 只能展示 Verifier 明确分类为 non-critical 的 Issue，并允许 `PARTIAL_ACCEPTED | REQUEST_MORE_RESEARCH | CANCEL`。接受时 Decision 必须保存 issue IDs、风险、Evidence、批准人和后续 Readiness 影响。

`MODIFY` 流程：

1. 保存用户原始自然语言；
2. Executor 生成 schema-valid Structured Diff；
3. 向用户展示字段级 diff 和影响范围；
4. 用户确认后写 Decision Log 和新 Artifact 版本；
5. Runtime 计算并执行精确 Downstream Invalidation。

未经第 4 步确认，不得改变任何有效 Artifact 或节点状态。

---

# 33. Downstream Invalidation

如果用户修改：

- Research Contract → invalidate 所有受影响 Research；
- Evidence Waiver → invalidate Synthesis 及其下游；
- Product Direction → invalidate Product Definition / Feasibility / Proof / MVP / PRD / final verifiers；
- External Proof Result → invalidate Feasibility 及其下游并返回 Feasibility；
- MVP Scope → invalidate PRD 与 final verifiers。

算法原则：

```text
Changed Artifact
↓
Find dependent nodes
↓
Mark INVALIDATED
↓
Preserve historical attempts
↓
Re-run only affected graph
```

---

# 34. Research Synthesis Contract

Input：

- Verified Research Artifacts，或带 Evidence Waiver Decision 的 non-critical Partial Artifacts
- Claim Registry
- Contradictions
- Accepted Risk Decisions

Output：

```yaml
validated: []
partially_validated: []
invalidated: []
unknown: []
contradictions: []
opportunities: []
risks: []
```

Synthesis 不允许：

- 新增无 Evidence 的关键事实；
- 直接添加 MVP Features。

---

# 35. Opportunity Mapping

输出最多 4 个方向。

```yaml
opportunities:
  - id: OPP-A
    name:
    description:

    scores:
      pain_strength:
      differentiation:
      feasibility:
      timing:
      defensibility:
      mvp_cost:

    evidence_ids: []

recommended:
  id: OPP-B
  rationale: []
```

评分算法应保存在 `opportunity-methodology.yaml`。

---

# 36. Product Definition

输出：

```yaml
product:
  name:
  problem:
  target_user:
  jtbd:
  value_proposition:
  differentiation:
  core_object:
  core_workflow:
  product_boundary:
  non_goals:
  success_definition:
```

---

# 37. Feasibility Review

```yaml
feasibility:
  result: CONDITIONALLY_FEASIBLE

dimensions:
  data_availability:
  api_availability:
  platform_constraints:
  architecture:
  security:
  performance:
  operations:
  implementation_cost:

blockers: []

critical_assumptions: []

proof_required: []
```

---

# 38. Proof Planner

```yaml
proof:
  id: PROOF-01

question:

hypothesis:

experiment:
  steps: []

inputs: []

pass_criteria: []

fail_criteria: []

expected_artifacts: []
```

Proof 本身由外部人员或 Coding Agent 执行。Product Discovery Runtime 生成计划后将 `proof_result` 节点置为 `WAITING_FOR_EXTERNAL`，不执行命令、不编写 Spike。

`proof-result.schema.json`：

```yaml
proof_result:
  proof_id: PROOF-01
  submitted_at:
  submitted_by:
  outcome: PASS
  artifact_refs: []
  evidence_ids: []
  observed_results: []
  limitations: []
  executor_notes:
```

`outcome` 为 `PASS | FAIL | INCONCLUSIVE`。提交后必须先验证 Schema 与 Evidence，再失效 Feasibility 及其下游并重新运行 Feasibility Review。required Proof 为 `FAIL`、`INCONCLUSIVE` 或缺失时不得进入 MVP Scope。

---

# 39. MVP Scope Contract

```yaml
phase:
  id: phase_1

goal:

must_have: []

should_have: []

later: []

non_goals: []

success_metrics: []

exit_criteria: []
```

P0 要求 Non-goals 必须非空。

---

# 40. PRD Generation and Final Verifiers

## 40.1 PRD Generator Guardrails

PRD Generator 只能读取 Approved / Verified Artifact。

生成后必须运行独立的 `prd-consistency-verifier`。Generator 不得验证自己的输出。

检查：

- 新 P0 Feature 是否有 approved source；
- Non-goals 是否被重新引入；
- Product Direction 是否漂移；
- Feasibility blocker 是否被忽略；
- Success Metrics 是否保留；
- Open Questions 是否被误写成事实。

若失败：

`PRD_INCONSISTENT_WITH_APPROVED_DISCOVERY`

该错误不可由 Human Gate 跳过。修复输入或重新生成 PRD 后，必须再次运行 Verifier。

## 40.2 Build Readiness Verifier

输入：PRD Consistency Result、Effective Workflow、Research Verification、Evidence Waiver Decisions、Feasibility、Proof Results、MVP Scope 与所有 required Artifact 状态。

```yaml
readiness:
  status: READY_WITH_ACCEPTED_RISKS
  passed_checks: []
  accepted_risk_decision_ids: []
  blocking_issues: []
  evaluated_at:
```

- `READY_FOR_BUILD`：所有 required check 通过，且无 accepted evidence gap；
- `READY_WITH_ACCEPTED_RISKS`：所有 critical check 通过，只存在 Evidence Waiver 接受的 non-critical gap；
- `NOT_READY`：存在 critical research / security / compliance / data / feasibility blocker、required Proof 未通过、PRD 不一致或 required Artifact 缺失。

Build Readiness Verifier 是唯一可以写入 `readiness_status` 的节点。

触发规则：

| Trigger | Expected readiness |
|---|---|
| `prd_consistency_verifier` 完成 | 按全部门槛计算三态结果 |
| `CRITICAL_RESEARCH_BLOCKER` | `NOT_READY` |
| `FEASIBILITY_NOT_FEASIBLE` | `NOT_READY` |
| `REQUIRED_PROOF_FAILED` | `NOT_READY` |
| `PRD_CONSISTENCY_FAILED` | `NOT_READY` |

任何终止分支都必须由该 Verifier 写入 Readiness Result Artifact；Runtime 或其他 Skill 不得直接修改 `readiness_status`。

---

# 41. Event Log

`runtime/event-log.jsonl`

示例：

```jsonl
{"ts":"","event":"NODE_READY","node":"competitor"}
{"ts":"","event":"ATTEMPT_STARTED","node":"competitor","attempt":"ATT-17"}
{"ts":"","event":"ARTIFACT_WRITTEN","artifact":"ART-45"}
{"ts":"","event":"NODE_COMPLETED","node":"competitor"}
{"ts":"","event":"VERIFICATION_FAILED","node":"research_verifier","issue":"GAP-01"}
```

Event Log 主要用于：

- Debug
- Resume
- Audit
- UI Timeline

---

# 42. Decision Log

`runtime/decision-log.jsonl`

不可只存在最终文档里。

示例：

```json
{
  "decision_id":"DEC-3",
  "question":"Should Phase 1 control agent execution?",
  "decision":"No",
  "evidence_ids":["EV-12","EV-34"],
  "reversible":true
}
```

---

# 43. Error Taxonomy

v0.1：

```text
INPUT_INVALID
ARTIFACT_MISSING
SCHEMA_INVALID
SOURCE_UNAVAILABLE
INSUFFICIENT_EVIDENCE
RESEARCH_LIMIT_REACHED
DEPENDENCY_NOT_READY
GATE_NOT_APPROVED
VISUALIZATION_DATA_INSUFFICIENT
EXECUTOR_FAILED
PROOF_RESULT_INVALID
PROOF_REQUIRED_FAILED
BUDGET_EXCEEDED
SECURITY_POLICY_VIOLATION
STATE_VERSION_CONFLICT
IDEMPOTENCY_CONFLICT
PRD_INCONSISTENT_WITH_APPROVED_DISCOVERY
```

Skill Failure 必须结构化：

```yaml
error:
  code: INSUFFICIENT_EVIDENCE
  recoverable: true
  retry_target: user-evidence
  consumes_node_attempt: true
  consumes_global_research_cycle: false
  next_action: RETRY_NODE
  details:
```

错误映射：

| Error | Runtime action | Budget / retry effect |
|---|---|---|
| `INPUT_INVALID`、`SCHEMA_INVALID` | Node `BLOCKED`，等待修正输入 | 不自动重试 |
| `ARTIFACT_MISSING`、`DEPENDENCY_NOT_READY` | 阻塞当前节点并定位 / 失效上游 | 不消耗 Research Cycle |
| `SOURCE_UNAVAILABLE`、`EXECUTOR_FAILED` | 按 Node Retry Policy 重试 | 消耗 Node Attempt |
| `INSUFFICIENT_EVIDENCE`、`VISUALIZATION_DATA_INSUFFICIENT` | 生成 Gap 并定向重跑 | 消耗 Global Research Cycle；实际重跑也消耗 Attempt |
| `RESEARCH_LIMIT_REACHED` | non-critical → Evidence Waiver；critical → `NOT_READY` | 禁止继续自动重试 |
| `GATE_NOT_APPROVED` | 保持 `WAITING_FOR_USER`，或按 `CANCEL` 结束 | 不消耗 Attempt |
| `PROOF_RESULT_INVALID` | 拒绝外部输入，继续等待 | 不消耗 Research Cycle |
| `PROOF_REQUIRED_FAILED` | Feasibility 保持 `BLOCKED`，Readiness 为 `NOT_READY` | 不可豁免 |
| `BUDGET_EXCEEDED` | 暂停自动调度，等待在 Host 硬上限内调整 Contract | 不自动放宽预算 |
| `SECURITY_POLICY_VIOLATION` | 立即停止相关 Executor，Run 进入 `FAILED` | 不自动重试 |
| `STATE_VERSION_CONFLICT` | 拒绝写入并返回最新 `state_version` | 客户端重新读取后决定是否重提 |
| `IDEMPOTENCY_CONFLICT` | 拒绝同 Key 的不同 Payload | 客户端必须使用新 Key |
| `PRD_INCONSISTENT_WITH_APPROVED_DISCOVERY` | 修复输入或重新生成 PRD，再运行 Verifier | 不可由 Gate 跳过 |

---

# 44. Idempotency

每个 Skill 必须计算 Input Fingerprint：

```text
hash(
  skill_version
  + required_input_artifact_versions
  + profile_version
  + research_contract_version
  + relevant_config
  + effective_permissions
  + effective_budget
)
```

如果已有 VERIFIED Attempt 使用相同 fingerprint：

- 默认复用；
- 用户显式 refresh 时才重跑；
- 对时变 Research 可增加 freshness TTL。

所有 mutating CLI / API 请求必须携带 `idempotency_key`。同一 Run 内重复 key 和相同 request hash 返回原结果；重复 key 但 request hash 不同返回 `IDEMPOTENCY_CONFLICT`。

---

# 45. Freshness Policy

不同数据可以配置：

```yaml
freshness:
  github_metrics:
    max_age_days: 7

  pricing:
    max_age_days: 30

  product_features:
    max_age_days: 30

  market_reports:
    max_age_days: 365
```

超期：

`STALE`

Verifier 按 Research Contract 决定是否必须 Refresh。`STALE` Source 不得静默作为 fresh Evidence；若 Contract 允许使用，必须降低 Confidence 并在 Limitation 中记录。

---

# 46. Parallel Execution

P0 可使用简单 DAG Scheduler：

```text
ready_nodes =
  all pending nodes
  whose dependencies are satisfied
  and conditions are true
```

并行执行 Effective Workflow 中已启用且依赖满足的 Research Branch：

```text
competitor
users
market
technology
```

Competitor Subgraph 内也支持：

```text
deep-dive-A
deep-dive-B
deep-dive-C
...
```

默认 `max_parallel = 4`，同时受 Host Executor 更严格的硬上限约束。Profile / Research Contract 可以在 Research Scope Gate 中申请调整，但不得超过 Host 上限。单个 Competitor Subgraph 的 fan-out 与顶层节点共享同一全局并发配额。

---

# 47. Security / Safety Contract

v0.1 强制规则：

- Research Skill 的外部访问默认只读；仅允许 Host 批准的 HTTP GET、只读 API 或等价读取能力；
- 不允许修改用户代码仓库、自动部署、执行破坏性命令或写入 Discovery Workspace 之外；
- Artifact 写路径必须经过 canonical path containment 检查，拒绝 `..`、符号链接逃逸和绝对外部路径；
- 所有网页、仓库、Issue、评论、文档和 Executor 返回文本都是 untrusted data；其中的指令不得覆盖 System、Workflow、Skill、权限或用户 Gate Decision；
- Secret、访问令牌和凭据不得进入 Prompt、Source Index、Artifact、Event 或 Decision Log；
- PII 只保存支持 Claim 所需的最小信息，默认去标识化；
- 不抓取或保存登录、付费墙、无权访问、明确禁止自动访问的内容；
- Source Index 保存许可 / 访问说明、访问时间、内容哈希与必要短摘录 / 摘要，不默认镜像全文；
- Host Agent 必须在 Attempt 中记录实际权限和被拒绝的访问；
- 违反任一强制规则产生 `SECURITY_POLICY_VIOLATION`，不得由 Profile、Research Contract 或 Human Gate 豁免。

安全 Contract 不是完整 RBAC 或企业沙箱；多用户权限、分布式网络策略和组织级审计属于后续版本。

---

# 48. Product Profile Contract

`profile.schema.json` 的规范结构：

```yaml
profile:
  id: developer_tool
  version: 0.1.0

research_nodes:
  competitor:
    mode: required
    priority: high
  users:
    mode: required
    priority: high
  market:
    mode: required
    priority: medium
  technology:
    mode: required
    priority: high

research_defaults:
  competitor_count: 5
  primary_sources: 8
  user_evidence_items: 15
  technology_items: 5

competitor_visualizations:
  required:
    - feature_matrix
    - positioning_map
    - momentum_comparison
    - oss_activity

extra_questions:
  - Does platform vendor offer native equivalent capability?
  - Can OSS components reduce implementation scope?

extensions: []
```

四种 v0.1 Profile 默认值：

| Profile | Research nodes | Required visualizations | Focus |
|---|---|---|---|
| `developer_tool` | competitor / users / market / technology required | feature_matrix、positioning_map、momentum_comparison、oss_activity | OSS、架构、集成、平台风险 |
| `ai_agent_product` | 四支 required | capability_matrix、positioning_map、cost_performance、ecosystem_momentum | Models / APIs、Papers、Agent Frameworks、平台原生能力 |
| `consumer_app` | competitor / users / market required；technology optional | feature_ux_matrix、positioning_map 固定必选；pricing_comparison、sentiment_distribution 二选一 | App Store、Social、Reviews、Pricing、UX |
| `b2b_saas` | 四支 required | feature_matrix、positioning_map、pricing_comparison、integration_security_coverage | Buyer/User split、Security、Integrations、Procurement |

Consumer App 的 `technology` 默认是 `optional`。只有 Project Research Contract 在 Research Scope Gate 中将其禁用时，Effective Workflow 才将该节点记录为 `SKIPPED / PROFILE_DISABLED`。Consumer App 的前两张图固定必选，第三张图通过 Profile 的 `choose_one` 约束声明候选项，并由 Research Contract 在 Gate 前预选。Profile 默认门槛使用 5 个竞品、8 个主要来源、15 条用户 Evidence 和 5 个 OSS / Technical 项；disabled 节点不适用的门槛写 `N/A`，optional 节点仅在未启用时写 `N/A`，不能填 0 伪装完成。

```yaml
competitor_visualizations:
  required:
    - feature_ux_matrix
    - positioning_map
  choose_one:
    options:
      - pricing_comparison
      - sentiment_distribution
    selected_by: research_contract
```

Profile Extension：

```yaml
extensions:
  - id: paper_landscape
    node:
      kind: skill
      skill: paper-landscape
    insert_after: gate_research
    before: research_verifier
    required: true
    config: {}
```

Extension 必须保持 DAG，不能删除 Core Node、改变 Readiness 的唯一写入者、绕过 Gate / Evidence / Source / Security Contract，或临时创建未在 Profile 中声明的 Human Gate。

---

# 49. Normative CLI Contract

CLI 是语言中立的操作 Contract；实现可以使用任意命令名映射，但必须提供下列等价能力、JSON 输出和退出码：

```text
init --idea <text|file> --profile <id> --idempotency-key <key>
status --run-id <id>
run --run-id <id> --idempotency-key <key>
pause --run-id <id> --idempotency-key <key>
resume --run-id <id> --idempotency-key <key>
gate submit --run-id <id> --gate-id <id> --decision <value> [--input <json>] --idempotency-key <key>
retry --run-id <id> --node-id <id> --idempotency-key <key>
proof submit --run-id <id> --proof-id <id> --input <file> --idempotency-key <key>
inspect --run-id <id> --artifact-id <id>
cancel --run-id <id> --idempotency-key <key>
export --run-id <id> --artifact prd
```

所有命令 stdout 输出统一 Response Envelope；诊断信息写 stderr。退出码：`0` 成功，`2` 输入 / Schema 错误，`3` 状态或 Gate 冲突，`4` 权限 / 安全拒绝，`5` Executor / Source 临时失败，`6` Run 完成但 `NOT_READY`，`10` 未分类内部错误。

---

# 50. Normative Runtime API

## 50.1 Operations and Envelopes

```text
create_run
get_run_state
run_ready_nodes
pause_run
resume_run
submit_gate_decision
submit_artifact_patch
submit_external_proof_result
retry_node
get_artifact
get_source
cancel_run
export_prd
```

Operation payload / result：

| Operation | Required payload | Result |
|---|---|---|
| `create_run` | `idea`、`profile_id`、可选 Contract override | `run_id`、初始 State、生成的 Idea / Contract refs |
| `get_run_state` | `run_id` | 当前 State、Current Gate、Readiness、`state_version` |
| `run_ready_nodes` | `run_id`、可选 `node_ids` | 已调度 Attempt IDs 与更新后的 State |
| `pause_run` / `resume_run` | `run_id` | 更新后的 Workflow Status |
| `submit_gate_decision` | `gate_id`、`decision`、Decision payload | Decision ref、受影响节点预览或结果 |
| `submit_artifact_patch` | base Artifact ref、Structured Diff ref、已确认 Decision ref | 新 Artifact ref 与 invalidated nodes |
| `submit_external_proof_result` | `proof_id`、Proof Result payload | Proof Artifact ref 与 Feasibility re-review schedule |
| `retry_node` | `node_id`、reason | 新 Attempt ref；超限时返回结构化错误 |
| `get_artifact` | `artifact_id`、可选 version | Schema-valid Artifact 或 not-found error |
| `get_source` | `source_id` | 允许留存的 Source metadata / minimal excerpt |
| `cancel_run` | `run_id`、reason | `CANCELLED` State；历史 Artifact 不删除 |
| `export_prd` | `run_id`、可选 format | PRD Artifact 与 Readiness Result refs |

Mutating request envelope：

```json
{
  "api_version": "0.1.0",
  "run_id": "run_20260808_001",
  "idempotency_key": "client-generated-key",
  "expected_state_version": 12,
  "payload": {}
}
```

`create_run` 时 `run_id` 省略或为 `null`，且不提供 `expected_state_version`；其他 mutating operation 必须提供二者。

Response envelope：

```json
{
  "api_version": "0.1.0",
  "request_id": "REQ-001",
  "ok": true,
  "state_version": 13,
  "data": {},
  "error": null
}
```

`expected_state_version` 不匹配返回 `STATE_VERSION_CONFLICT`；重复 Idempotency Key 但 Payload 不同返回 `IDEMPOTENCY_CONFLICT`。读取接口不要求 Idempotency Key。`get_source` 只返回 Source Index 中允许留存的元数据与最小摘录，不代理下载外部全文。

## 50.2 Executor Adapter Contract

v0.1 只定义三种参考 Adapter Type：

- `fixture`：从版本化 Fixture 生成确定性 Artifact，只用于测试，不得形成真实研究 Claim；
- `manual`：输出结构化执行说明并进入外部等待，用户提交结果后继续；
- `host_agent`：由 Host Agent 在显式权限和预算内执行 Skill。

OpenAI、Anthropic 或其他厂商专用 Adapter 不属于 v0.1 规范范围。

Executor Request：

```yaml
executor_request:
  schema_version: 0.1.0
  run_id:
  node_id:
  attempt_id:
  adapter_type: host_agent
  skill_ref: competitor-discovery@0.1.0
  input_artifact_refs: []
  profile_ref:
  research_contract_ref:
  permissions:
    external_access: read_only
    workspace_write_paths: []
  budget:
    timeout_minutes: 20
    max_sources: 50
    token_limit:
    cost_limit:
```

Executor Result：

```yaml
executor_result:
  schema_version: 0.1.0
  run_id:
  node_id:
  attempt_id:
  status: COMPLETED
  output_artifact_refs: []
  source_upserts: []
  usage:
    automated_duration_seconds:
    source_count:
    input_tokens:
    output_tokens:
    estimated_cost:
  error:
```

Executor 只能返回 Artifact 与 Source Upsert 提案；由 Orchestrator 完成 Schema、安全、路径和预算验证后才能写入规范存储。Executor 无权直接修改 Runtime State、Decision Log 或 Current Manifest。

v0.1 `executor_result.status` 只接受 `COMPLETED | FAILED`。`COMPLETED` 必须令 `error` 为 `null`；`FAILED` 必须携带符合 Error Taxonomy 的结构化 Error。取消和超时由 Runtime 映射为失败及相应 Error，而不是扩展 Node Status 枚举。

## 50.3 Run Policy Contract

```yaml
run_policy:
  max_parallel: 4
  automated_attempt_timeout_minutes: 20
  max_sources_per_research_node: 50
  max_retries_per_node: 2
  max_global_research_cycles: 2
  automated_run_timeout_minutes: 120
  host_token_limit:
  host_cost_limit:
```

Human Gate 与 External Proof 等待时间不计入 `automated_run_timeout_minutes`。Profile / Research Contract 可以在 Host 硬上限内收紧或申请调整；放宽默认值必须显示在 Research Scope Gate 并写入 Decision Log。

## 50.4 Current Manifest Contract

```json
{
  "schema_version": "0.1.0",
  "run_id": "run_20260808_001",
  "state_version": 13,
  "updated_at": "",
  "last_event_offset": 81,
  "current_artifacts": {
    "idea_definition": {
      "artifact_ref": "ART-001@1",
      "content_hash": ""
    }
  }
}
```

Current Manifest 是有效 Artifact 版本的唯一指针真相源；Event Log 提供审计与恢复历史，不能覆盖 Manifest 的当前有效版本。v0.1 只支持单 Orchestrator Writer，不定义多进程锁或 SQLite 后端。

---

# 51. Testing Strategy

本节定义未来参考 Runtime 的验收 Contract；当前 v0.1 文档交付不表示这些 Runtime 测试已经执行。

## 51.1 Static Specification Validation

- PRD / SPEC 术语、版本范围、Profile、Gate、Node 和 Readiness 一致；
- 所有 YAML / JSON 示例可解析；
- 所有机器字段为 `snake_case`；
- Workflow 的 `depends_on`、`when` 与 Loop Target 可解析且形成 DAG；
- Error Code、CLI Exit Code 与 API Error 映射无重复或悬空引用。

## 51.2 Unit

测试：

- State transition
- Dependency resolution
- Condition evaluation
- Invalidation
- Retry count
- Schema validation
- Score normalization
- Atomic manifest update and crash recovery
- Source canonicalization / deduplication
- Path containment and prompt-injection isolation
- Idempotency and state-version conflict

## 51.3 Contract Tests

每个 Skill 至少验证：

- Required Inputs
- Required Outputs
- Artifact Schema
- Forbidden missing evidence
- Source Index reference integrity
- Executor Request / Result
- Gate Structured Diff confirmation
- Profile composition and Extension constraints
- Run Policy enforcement

## 51.4 Workflow Tests

场景：

### Happy Path

所有 Research 一次 PASS。

### Research Retry

User Evidence FAIL → targeted retry → PASS。

### Partial Evidence Waiver

Verifier PARTIAL → Evidence Waiver → `PARTIAL_ACCEPTED` → Synthesis → final `READY_WITH_ACCEPTED_RISKS`。

### Critical Gap

Security / Compliance / Data Integrity / Core Feasibility gap → Evidence Waiver forbidden → `NOT_READY`。

### Gate Modification

自然语言修改 → schema-valid diff → 用户确认 → 新 Artifact 版本 → 仅相关 downstream invalidated。

### Missing Data

GitHub metric 缺失 → null，而非捏造。

### PRD Drift

PRD 新增未批准 P0 → verifier fail。

### External Proof

Feasibility BLOCKED → Proof Plan → WAITING_FOR_EXTERNAL → valid Proof Result → Feasibility re-review；invalid / failed required Proof 不得进入 Scope。

### Resume

运行至 Research 完成后退出 → 从 persisted state 恢复。

### Profile Composition

四个 Profile 的 enabled / optional / disabled Research、required visualizations 与 Extension DAG 均符合 Contract；Consumer Technology 默认 optional，并在 Effective Contract 明确禁用时记录 `PROFILE_DISABLED`。

### Source and Security

Source 去重、STALE、无权访问、PII、Secret、路径逃逸和外部 Prompt Injection 均按 Contract 处理。

### Executor and Budget

Executor timeout、cancel、retry、Idempotency、State Version Conflict、Source / Token / Cost 上限均可复现。

---

# 52. P0 Acceptance Test Design

## 52.1 Deterministic Fixture Suite

| Fixture ID | Profile | Idea |
|---|---|---|
| `codex_progress_observability` | `developer_tool` | 读取项目目录并展示 Coding Agent 执行进度 |
| `api_dependency_change_monitor` | `developer_tool` | 识别 API / 依赖变化并提示代码影响范围 |
| `support_ticket_agent` | `ai_agent_product` | 基于证据分流与总结支持工单 |
| `shared_household_planner` | `consumer_app` | 面向共同生活成员的共享计划与提醒产品 |
| `vendor_security_questionnaire_saas` | `b2b_saas` | 协助供应商安全问卷收集、证据关联与复核 |

Fixture 由 `fixture` Executor 产生版本化确定性 Artifact，用于状态、Contract、Profile、Gate、Loop、恢复和 Readiness 测试。所有 Schema、状态和安全 Contract Test 必须通过；至少 4 / 5 个 Fixture Idea 完成有效端到端 Workflow。Fixture Artifact 必须标记 Executor Type，不得作为真实产品研究证据。

Happy Path 期望：

```text
idea-intake                   VERIFIED
research-contract             VERIFIED
gate-research                 APPROVED

competitor                    VERIFIED
user-evidence                 VERIFIED
market                        VERIFIED
technology                    VERIFIED

research_verifier             VERIFIED / PASS
evidence_waiver               SKIPPED / CONDITION_NOT_MATCHED
research_synthesis            VERIFIED
opportunity                   VERIFIED

gate-direction                APPROVED
product-definition            VERIFIED
feasibility                   VERIFIED
mvp-scope                     VERIFIED
gate-scope                    APPROVED
prd                           VERIFIED
prd_consistency_verifier      VERIFIED / PASS
build_readiness_verifier      VERIFIED

readiness                     READY_FOR_BUILD
```

Developer Tool 竞品 Artifact 至少包含：

```text
competitor-dataset.json
feature-matrix/*
positioning-map/*
momentum-comparison/*
oss-activity/*
competitor-report.md
```

其他 Profile 按第 25 节的 required visualization Contract 验收。

## 52.2 Live Developer Tool Acceptance

输入：

> 我想做一个读取项目目录并自动展示 Codex / Claude Code 当前执行进度的工具。

这是系统要分析的 Product Idea，不表示 Product Discovery Runtime 自身接管 Codex / Claude Code Runtime。

Live Chain 使用 `host_agent` Executor 和真实可访问 Source，验证：Source provenance、Freshness、Profile-required Artifacts、Research Gap、Gate、PRD Consistency 与三态 Readiness。不得对易变的研究正文、实时指标或排名做 Golden Snapshot。

---

# 53. Recommended P0 Build Order

## Step 1

定义：

- workflow.yaml
- state schema
- skill schema
- artifact schema
- source / evidence / profile / gate / executor / run policy / readiness schemas

本 Step 只交付机器可读契约、规范实例与静态验证闭环；不表示 Step 2–7 的 Orchestrator、Runtime、Research Skill 或端到端 P0 已实现。为保证契约可解析，允许补充上述 Schema 直接引用的共享定义，但不得借此提前实现后续 Runtime 行为。

## Step 2

实现：

- Orchestrator
- Node states
- dependency resolution
- gates
- retries
- single-writer file storage / current manifest / event recovery
- language-neutral CLI / API
- fixture / manual / host_agent adapters

## Step 3

实现第一个完整 Research Subgraph：

`Competitor Research`

包括：

- discovery
- ranking
- deep dive
- normalization
- analysis
- visualization
- verification

## Step 4

加入：

- User Evidence
- Market
- OSS / Technical

## Step 5

实现：

- Research Verifier
- Evidence Waiver
- Gap Loop
- Synthesis

## Step 6

实现：

- Opportunity
- Product Definition
- Feasibility
- External Proof import / re-review
- MVP Scope

## Step 7

实现：

- PRD Generator
- PRD Consistency Verifier
- Build Readiness Verifier
- Five Fixture Suite and one Live Developer Tool acceptance

这样能最早验证核心抽象：

> Skill → Artifact → Evidence → Verification → Next / Retry

---

# 54. P0 不实现

- Dynamic self-modifying graph
- Automatic skill generation
- RL
- Long-term organization memory
- Multi-user RBAC
- Cloud queue
- Distributed workers
- Visual workflow editor
- End-user UI
- Autonomous coding
- Automatic deployment
- Arbitrary tool marketplace
- SQLite / multi-writer storage
- Vendor-specific LLM adapters
- Full external page mirroring

---

# 55. Architecture Decision Summary

## ADR-01：Graph 而非 Linear Pipeline

原因：

- Research 可并行；
- Verification 可回退；
- Feasibility 可产生条件分支；
- Human Gate 会暂停流程。

## ADR-02：Artifact 而非 Chat Context 作为状态

原因：

- 可恢复；
- 可审计；
- 可版本化；
- 可由不同 Agent 接续。

## ADR-03：Research 与 Decision 分离

原因：

- 降低 confirmation bias；
- 防止研究 Agent 自动证明自己的产品建议。

## ADR-04：竞品分析使用 Dataset-first

原因：

- 可重复生成图表；
- 数据与结论解耦；
- 可审计；
- 可后续增量更新。

## ADR-05：Human Gate 只放在关键决策点

原因：

- 保持用户控制；
- 避免每一步都打断。

## ADR-06：Unknown 是合法结果

原因：

- 防止 Agent 为了完成任务编造事实。

## ADR-07：Core Workflow + Profile + Research Contract

原因：

- 保持 Workflow 主干稳定；
- 让四种产品类型共享状态、Gate 与质量语义；
- 允许 Profile 调整策略、Research Contract 调整项目问题，而不复制整套 Workflow。

## ADR-08：状态、结果、决策与 Readiness 分型

原因：

- 防止 `PARTIAL`、`APPROVED`、`BLOCKED` 等字符串跨领域混用；
- 让 Workflow 条件和测试具有确定语义。

## ADR-09：Source Index 独立于 Evidence

原因：

- 支持去重、Freshness、访问许可、安全检查和统一审计；
- 避免在每条 Evidence 中重复或漂移来源信息。

## ADR-10：单写者文件存储

原因：

- 与本地、可审计、可恢复的 v0.1 边界一致；
- 通过 append-only 历史、原子 Current Manifest 更新避免静默覆盖；
- SQLite、多写者与分布式锁后置。

## ADR-11：Proof 外部执行

原因：

- Product Discovery Runtime 只规划、等待、导入结果并复审；
- 避免越界成为 Coding Runtime。

## ADR-12：生成与最终验证分离

原因：

- PRD Generator 不自证一致性；
- 只有 Build Readiness Verifier 能写三态 Readiness。

---

# 56. Definition of Done — v0.1 Design Baseline

## 56.1 当前文档基线完成条件

- [x] PRD / SPEC 明确声明 v0.1 是 Implementation-Ready Design Baseline，不宣称 Runtime 已实现
- [x] Core Workflow、四 Product Profile 与 Research Contract 的合成规则无歧义
- [x] Node Status、Verification Result、Gate Decision、Feasibility Result、Workflow Status、Readiness Status 分型完成
- [x] 3 个标准 Gate 与条件式 Evidence Waiver Gate 契约完整
- [x] Research Gap 与 External Proof 回环可由 Workflow Schema 表达
- [x] Competitor Research 定义为 Dataset-first Subgraph
- [x] Source、Evidence、Executor、Profile、Run Policy、Storage、CLI / API、Security 与 Readiness Contract 完整
- [x] PRD Consistency Verifier 与 Build Readiness Verifier 独立
- [x] 所有机器字段统一为 `snake_case`
- [x] 5 个 Fixture + 1 条 Live Developer Tool 验收设计完整
- [x] 所有 YAML / JSON 示例通过静态解析验证

## 56.2 未来参考 Runtime 完成条件

以下项目不因文档完成而自动视为已实现：

- [ ] Workflow 可从 Idea 跑到 PRD，并支持 DAG、Pause / Resume、Retry、Invalidation 与单写者恢复
- [ ] 四 Product Profile 的 Contract 和 Fixture Test 全部通过
- [ ] Claim → Evidence → Source 可追踪，Unknown / null 不被自动补全
- [ ] Profile-required Visualization 与 Score Methodology 可追踪
- [ ] Partial Waiver、Critical Gap、External Proof 与三态 Readiness 场景通过
- [ ] PRD Consistency 与 Build Readiness 独立验证通过
- [ ] 一条真实 Developer Tool Research 链路通过 Live Acceptance

---

# 57. 核心实现原则

系统实现时始终维持以下边界：

```text
Agent = Executor
Skill = Capability Contract
Workflow = Process
Artifact = Persistent State
Evidence = Grounding
Verifier = Quality Control
Gate = Human Decision
Loop = Recovery / Research Expansion
```

最重要的不是“让 Agent 一次写出更好的报告”，而是确保：

> 每一个重要产品判断都知道从哪里来、为什么成立、谁确认过、证据不足时回到哪里，以及什么时候才允许进入开发。
