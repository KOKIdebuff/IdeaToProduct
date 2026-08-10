# Product Discovery SkillGraph — System / Workflow Spec v0.2

> 文档类型：Implementation Specification  
> 状态：FROZEN / Current Technical Specification  
> 版本：v0.2 / target contract `0.2.0`  
> 依赖 PRD：已冻结的 Product Discovery SkillGraph PRD v0.2  
> 历史基线：SPEC v0.1 / immutable contract baseline `0.1.0`  
> 当前事实来源：SPEC v0.2 = SPEC v0.1 Baseline + 本文明确 Amendment  
> 交付边界：本文档冻结语言中立的 v0.2 Contract；不表示 Runtime、Schema、Skill、Fixture、真实 Research 或生产部署已经完成。Phase 3 Traceability 通过前必须 `STOP IMPLEMENTATION`；Python 仅作为首个参考实现建议

---

# 1. Spec 目标

本文档定义 Product Discovery SkillGraph v0.2 的目标实现规范，包括：

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
- Adaptive Idea Shaping
- Interactive Skill / Attempt Checkpoint
- Interaction Waiting / Submit / Resume
- Idea Clarity、Completion、Early Exit 与最大轮次

本 Spec 优先保证：

1. 可实现；
2. 可验证；
3. 可恢复；
4. 可扩展；
5. 不绑定某个特定 LLM / Agent Executor。

v0.2 的规范交付继续遵循：

`Core Workflow + Product Profile + Project Research Contract = Effective Workflow`

- Core Workflow 定义不可删除的产品发现骨架；
- Product Profile 调整研究支路启用状态、优先级、来源、阈值、必选图表和扩展节点；
- Project Research Contract 为当前项目定义具体问题，并记录经 Research Scope Gate 批准的调整；
- 本文所有公共 Workflow、Schema、CLI 和 API 使用语言中立的 `snake_case` 字段；Python 只作为非规范性参考实现。

v0.2 的机器示例统一使用目标版本 `0.2.0`。当前根目录已验证的 Schema、Workflow、Skill、Subgraph、Template 与 Fixture 继续作为不可变 `0.1.0` Baseline；未来实现必须通过 Version Registry 加载完整 `0.2.0` Bundle，不得把 v0.1 实例静默解释为 v0.2，也不得通过原地替换版本常量破坏 v0.1 回归闭包。

## 1.1 Consolidation and Precedence Rules

- 本文是唯一 Current Technical Specification；同一工程语义发生冲突时，`SPEC v0.2 > SPEC v0.1 > existing code`；
- 本文明确修改或新增的契约覆盖 v0.1；本文未涉及的 Runtime、Graph、Schema、Verification、安全、预算和恢复能力全部继承 v0.1；
- v0.1 文档与 `0.1.0` Contract Tree 保持不可变，继续用于历史决策、Architecture Baseline、回归验证和只读审计；
- 冻结本文不等于批准开发。只有 `PRD Status = FROZEN`、`SPEC Status = FROZEN` 且 Phase 3 Traceability = PASS，才允许进入 P0 Implementation；
- P0 只实现一条集成链，不分别实现 v0.1 与 v0.2，不维护双 Runtime。

---

# 2. Architecture Overview

```text
┌─────────────────────────────────────────────────────────┐
│                    User / Host Agent                    │
└───────────────────────────┬─────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────┐
│                    Orchestrator                         │
│ registry / version / dependency / gate / retry / route  │
└───────────────────────────┬─────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────┐
│              Version-selected Workflow DAG             │
│ skill / subgraph / verifier / human_gate                │
└───────────────────────────┬─────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────┐
│     Artifact Repository + Runtime State + Audit Logs     │
│ artifact / state / attempt / event / decision / manifest│
└─────────────────────────────────────────────────────────┘
```

---

# 3. Runtime Responsibilities

Orchestrator 只负责：

- Resolve `contract_version` through the Version Registry
- Validate a complete single-version Contract Bundle and explicit legacy references
- Load workflow
- Resolve dependencies
- Evaluate conditions
- Mark READY nodes
- Schedule runnable nodes
- Run independent nodes in parallel
- Pass Artifact references
- Persist Attempt result
- Persist versioned Interaction Checkpoint
- Open and resume Interactive Skill input without creating a Human Gate
- Run verifier
- Open Human Gate
- Retry failed / insufficient nodes
- Invalidate downstream on approved input changes
- Resume workflow from persisted state
- Validate idempotent Interaction Response and resume the same Attempt
- Fail Closed on unsupported cross-version State or mixed-version references

Orchestrator 不负责：

- 自己做竞品研究；
- 自己输出市场结论；
- 自己决定产品方向；
- 自己生成未经过 Skill 的 Artifact。

Orchestrator 必须区分两类用户等待：

- `Interactive Input`：帮助 Skill 理解用户，属于同一 Attempt 的执行过程；
- `Human Gate`：阻止系统未经授权跨越正式产品决策，产生 Gate Decision。

Interactive Input 不得调用 Gate Contract、写入 `current_gate` 或生成 Product Direction Decision。

唯一技术架构为：Host / User 调用单一 Orchestrator；Orchestrator 根据 Registry 选择一个完整 Workflow Bundle；Workflow 调度 Skill、Subgraph、Verifier 和 Human Gate；所有持久结果进入 Artifact Repository、Runtime State、Attempt History、Event Log、Decision Log 与 Current Manifest。不存在 v0.1 Runtime 与 v0.2 Runtime 两条实现链。

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
- `condition` 不是 v0.2 Workflow Schema 的合法字段；
- `activation` 不是 v0.2 Workflow Schema 的合法字段；
- 条件未命中时，节点标记为 `SKIPPED`，并记录 `CONDITION_NOT_MATCHED`，不能一直停留在 `PENDING`。

### Fan-out

一个上游节点产生多个并行后继。

### Fan-in

多个 Research 节点全部完成后进入 Verify。

---

# 5. Workflow File

## 5.1 Version Registry and Bundle Resolution

未来实现必须提供：

```text
contracts/
├── registry.yaml
└── 0.2.0/
    ├── workflow.yaml
    ├── schemas/
    ├── profiles/
    ├── skills/
    ├── subgraphs/
    ├── templates/
    └── fixtures/
```

`contracts/registry.yaml` 的规范语义为：

```yaml
registry:
  default_new_run_version: 0.2.0
  path_resolution: repository_root_relative
  versions:
    0.1.0:
      status: immutable_baseline
      bundle_root: .
      new_runs_allowed: false
      resume_allowed: false
      audit_allowed: true
    0.2.0:
      status: current
      bundle_root: contracts/0.2.0
      new_runs_allowed: true
      resume_allowed: true
      audit_allowed: true
```

Registry 与 Bundle 规则：

- 新建 Run 的默认且唯一允许版本为 `0.2.0`；Host 省略 `contract_version` 时由 Registry 填入 `0.2.0`，显式请求其他版本时 Fail Closed；
- `bundle_root` 一律相对于 Repository Root 解析，不相对于 `contracts/registry.yaml` 所在目录解析；
- 一个 Run 的 Workflow、Schema、Profile、Skill、Subgraph、Template、Fixture、State、Attempt 与 Manifest 必须从同一 Bundle 解析；Bundle 内所有 `$ref` 和 `@version` 引用必须属于 `contract_version`；
- 禁止在当前目录优先、父目录回退或跨树搜索中隐式解析引用；任何跨 Bundle 引用只能经过第 50.5 节的 `legacy_input_refs` 接口，且保持只读；
- Registry 选择 Contract，不选择第二套 Runtime；单一 Orchestrator 只执行所选 Bundle；
- `0.2.0` Bundle 必须是完整闭包，不能把本文未修改的 v0.1 基线契约留在根目录后再运行时跨树拼装。
- “可回滚”表示保留不可变 Bundle 和部署回退证据；它不授权当前 v0.2 Runtime 新建或恢复 v0.1 Run。

## 5.2 Current Workflow

规范路径：

`contracts/0.2.0/workflow.yaml`

```yaml
workflow:
  id: product-discovery
  version: 0.2.0
  schema_version: 0.2.0

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

v0.2 的 Adaptive Idea Shaping 完全位于现有 `idea` Skill 内部。`idea.kind` 必须继续是 `skill`，不得改为 `subgraph`，不得在 `idea` 与 `contract` 之间插入 Brainstorming Node 或 `HUMAN GATE #0`。Idea Interaction 的等待和恢复属于 Attempt 生命周期，不改变 DAG 拓扑。

`competitor`、`users`、`market`、`technology` 是 Profile 可配置研究支路。Profile 禁用支路时，Runtime 将其标记为 `SKIPPED`，原因是 `PROFILE_DISABLED`，并保存 Profile ID、版本和 Research Contract Decision；Build Readiness 只检查 Effective Workflow 中的 required 支路。

`research_synthesis` 的 `when.any_of` 继续沿用 v0.1 对“PASS 或已接受 PARTIAL”这一汇合条件的规范表达。Runtime 不得把 `PARTIAL` 自动转换为 `PARTIAL_ACCEPTED`。

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

Interactive Skill：

```text
READY
 ↓
RUNNING
 ↓
WAITING_FOR_USER
 ↓  submit_interaction_response
RUNNING
 ↓  zero or more additional rounds
COMPLETED
 ↓
VERIFYING
 ↓
VERIFIED
```

语义约束：

- `WAITING_FOR_USER` 可以用于 Human Gate Node 或 Interactive Skill Node，但二者通过 Node Kind、`current_gate` 和 `current_interaction` 分型；
- Interactive Skill 等待不产生 Gate Decision，不把 Skill Node 置为 `APPROVED`；
- 用户回复后恢复同一 `attempt_id`，不增加 `attempt_count`；
- 只有显式 Retry 才创建新 Attempt；
- Workflow 仅在没有其他可运行节点且存在 required Interactive Input 时进入 `WAITING_FOR_USER`。

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

v0.2 在 v0.1 State Contract 上增加 Interaction 状态。以下示例表示 Partial / Vague Idea 正在等待用户，尚未生成 Research Contract：

```json
{
  "schema_version": "0.2.0",
  "workflow_id": "product-discovery",
  "workflow_version": "0.2.0",
  "run_id": "run_20260809_001",
  "state_version": 3,
  "workflow_status": "WAITING_FOR_USER",
  "readiness_status": null,
  "current_gate": null,
  "current_interaction": {
    "node_id": "idea",
    "attempt_id": "ATT-IDEA-001",
    "method": "clarification",
    "question_id": "IQ-001",
    "round": 1,
    "checkpoint_ref": "runtime/attempts/ATT-IDEA-001/checkpoints/CP-0002.json"
  },
  "global_research_cycle": 0,
  "profile_ref": "developer_tool@0.2.0",
  "research_contract_ref": null,
  "nodes": {
    "idea": {
      "status": "WAITING_FOR_USER",
      "attempt_count": 1,
      "active_attempt_id": "ATT-IDEA-001",
      "interaction_checkpoint_ref": "runtime/attempts/ATT-IDEA-001/checkpoints/CP-0002.json",
      "artifact_refs": []
    },
    "contract": {
      "status": "PENDING",
      "attempt_count": 0,
      "artifact_refs": []
    }
  }
}
```

State Contract 规则：

- `current_interaction` 与 `current_gate` 是独立字段；同一个 Run 在 v0.2 Idea Shaping 路径中不得同时设置二者；
- `current_interaction.method` 必须是 `clarification | controlled_brainstorming | adaptive_product_discovery_interview | assumption_challenge`；它由 `idea-intake` 选择并供 Host 展示，客户端回复不得覆盖；
- `research_contract_ref` 在 `contract` Node 产生有效 Artifact 前允许为 `null`；Contract 完成后必须指向 Current Manifest 中的有效 Research Contract；
- `active_attempt_id` 和 `interaction_checkpoint_ref` 只在 Interactive Skill 为 `RUNNING | WAITING_FOR_USER` 时出现；
- Interaction Checkpoint 是 Runtime Ref，不是 Artifact Ref；
- 对现有已进入 Research 的状态，`current_interaction` 为 `null`。

下列 v0.1 示例只保留为历史 Schema 与只读审计参考，不是 v0.2 Idea Shaping 初始状态，也不允许由当前 Runtime 恢复；尝试恢复时必须返回 `SCHEMA_VERSION_UNSUPPORTED` 并保留原数据：

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
  skill_version: 0.2.0
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

## 8.1 Interactive Attempt

v0.2 Attempt Status 使用：

```text
RUNNING | WAITING_FOR_USER | COMPLETED | FAILED
```

同一 Interactive Attempt 可以由多个自动执行片段组成。`started_at` 在首次执行时写入；`finished_at` 仅在 `COMPLETED | FAILED` 时写入；进入 `WAITING_FOR_USER` 时保持为空。

Interaction Checkpoint 保存到：

```text
runtime/attempts/<attempt_id>/checkpoints/<checkpoint_id>.json
```

规范结构：

```yaml
interaction_state:
  schema_version: 0.2.0
  checkpoint_id: CP-0002
  attempt_id: ATT-IDEA-001
  checkpoint_version: 2
  round: 1
  unresolved_dimensions: [user, scenario, value, mechanism]
  current_method: clarification
  target_unknown_id: UNK-USER-001
  target_dimension: user
  selection_rationale: "Target user blocks scenario and research-question derivation."
  method_history:
    - round: 1
      method: clarification
      target_unknown_id: UNK-USER-001
  current_question:
    id: IQ-001
    dimension: user
    prompt: "你更想优先帮助哪类大学生？"
    options:
      - id: A
        label: 应届毕业生
        description: 聚焦第一次全职求职的流程与信息差。
      - id: B
        label: 有实习目标的低年级学生
        description: 聚焦实习准备、岗位发现与申请节奏。
    recommendation:
      option_id: A
      rationale: 应届生求职触发点和结果更明确，更容易形成首个 Research Contract。
    allow_freeform_answer: true
  answers: []
  current_hypothesis:
    problem:
    target_users:
    scenario:
    value_proposition:
    solution:
  clarity:
    problem: LOW
    user: UNKNOWN
    scenario: UNKNOWN
    value: LOW
    mechanism: LOW
    overall: PARTIAL
  completion_status: IN_PROGRESS
```

Checkpoint 规则：

- 每次提出问题、接受回复和更新 Hypothesis 都生成新版本，历史版本 append-only；
- `round` 表示已发出的主问题数，发出问题时递增；重复读取或幂等重放不递增；
- `current_question` 必须是单个对象或 `null`，禁止用数组发送问卷；
- `current_method`、目标 Unknown / Dimension、选择理由和 `method_history` 必须随 Checkpoint 版本持久化；方法历史只记录同一 Attempt 内部调用，不形成 Workflow Node、Attempt 或 Artifact 历史；
- `answers` 保存结构化回复，不保存或依赖完整聊天 Transcript；
- Checkpoint 不进入 Artifact Repository、Current Manifest、Decision Log 或 Research 输入；
- Workflow State 只保存最新 `checkpoint_ref`；恢复时由 Orchestrator 验证版本与归属后提供给 Executor。

## 8.2 Clarity and Completion Model

```text
dimension_clarity = UNKNOWN | LOW | MEDIUM | HIGH
idea_path = CLEAR | PARTIAL | VAGUE
completion_status =
  IN_PROGRESS |
  SUFFICIENT |
  PARTIAL_RESEARCHABLE |
  INSUFFICIENT_PRODUCT_CONTEXT
```

- `CLEAR`：Problem、User、Scenario、Value、Mechanism 均达到可研究清晰度，且没有阻止 Research Question 生成的关键缺口；
- `PARTIAL`：至少存在一个稳定的 Problem、User、Scenario 或 Direction 锚点，但一个或多个核心维度仍是 `UNKNOWN | LOW`；
- `VAGUE`：输入主要是领域或技术标签，没有稳定的 Problem / User / Scenario 锚点；
- Clarity 描述输入质量，不表示假设已获得 Evidence；
- `confidence.overall` 只表达系统对用户意图理解的定性信心，不表示市场或方案真实性；
- 禁止使用没有公开方法论的 `83/100` 等伪精确分数。

## 8.3 Question Selection and Convergence

同一 `idea` Attempt 内部支持以下动态 Interaction Method：

```text
clarification
controlled_brainstorming
adaptive_product_discovery_interview
assumption_challenge
```

这些 Method 可以按信息缺口重复、跳过或切换，不存在固定执行序列。它们不是顶层 Workflow Skill，不得创建独立 Node、Subgraph、Attempt、Gate、Decision 或业务 Artifact。唯一正式业务输出仍是 `idea_definition`。

每轮必须先运行 Completion Check，再选择问题。未完成时按以下顺序选择 Highest-Value Question：

1. 优先解决后续问题依赖的上游 Unknown；
2. 再解决会显著改变产品方向的 Unknown；
3. 再解决当前最不确定的核心维度；
4. 同级按 `problem → user → scenario → value → mechanism → alternatives → assumptions` 稳定排序；
5. 目标完全相同时，根据目标类型选择最适合的方法；仍完全相同时按 Method ID 字典序作为确定性 tie-breaker。该排序只解决相同候选，不构成固定方法流程。

这等价于优先考虑 `Impact × Uncertainty × Dependency`，但不要求暴露无方法论的数值分数。Assumption Challenge 参与相同选择过程，不另设固定轮数。

Assumption Challenge 至少检查：

- 用户是否真的存在该 Problem；
- 当前 Workaround 是否已经足够；
- Solution 是否被过早锁定；
- Idea 是否只是一个 Feature；
- 技术能力是否被误认为用户价值；
- 是否存在 Platform-native Risk；
- User 与 Buyer 是否被混为一谈。

无 Evidence 时，检查结果只能写入 Critical Assumption、Unknown 或 Research Seed，不能直接宣布 Idea 有效或无效。

当候选方向合理存在时：

- 提供 2–4 个实质不同的选项；
- Recommendation 必须引用其中一个 Option 并给出简短理由；
- `allow_freeform_answer: true` 时 Host 必须展示 Other / 自定义；
- 用户可以只选 Option、只自由输入，或选择后附加修改文本；
- Problem、User、Scenario、Value 尚不清楚前，禁止询问颜色、完整 Feature List、商业模式或详细技术架构。

Method 选择语义：

- `clarification`：已有稳定锚点，但单个阻塞性表述、边界或术语需要明确；
- `controlled_brainstorming`：Vague / Partial Idea 缺少可比较的 framing 时，生成 2–4 个 framing options，并仍只提出一个主问题；不得生成完整 Feature List；
- `adaptive_product_discovery_interview`：需要根据上一轮回答渐进探索 Problem、User、Scenario、Value 或 Mechanism，后续问题必须由最新 Checkpoint 派生；
- `assumption_challenge`：当前方向被高影响、低可信假设支配时，以一个问题检验或改写该假设；
- 每轮 Completion Check 已满足 `SUFFICIENT | PARTIAL_RESEARCHABLE` 时必须立即停止，不得为了执行预设 Interview 或覆盖全部 Method 而继续提问。

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

## Interaction Model (optional)

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
  version: 0.2.0
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

`interaction` 是可选对象。缺失时 Skill 保持 v0.1 非交互语义，不允许临时请求用户输入。`idea-intake` 的 v0.2 配置为：

```yaml
interaction:
  mode: adaptive
  supported_methods:
    - clarification
    - controlled_brainstorming
    - adaptive_product_discovery_interview
    - assumption_challenge
  selection_policy: highest_value_gap
  user_input_allowed: true
  one_question_at_a_time: true
  recommendation_enabled: true
  choice_generation_enabled: true
  allow_freeform_answer: true
  max_rounds: 8
  early_exit_when_sufficient: true
```

存在 `interaction` 时：

- `mode` v0.2 只接受 `adaptive`；
- `supported_methods` 必须恰好覆盖四个规范 Method，`selection_policy` 必须为 `highest_value_gap`；方法可以重复、跳过或切换，不得被解释为数组顺序执行；
- `user_input_allowed`、`one_question_at_a_time` 和 `allow_freeform_answer` 必须为 `true`；
- `max_rounds` 是该 Skill 的硬上限，Host 可以在 Create Run 时提供更低上限，但 Profile 与 Research Contract 无权放宽；
- `early_exit_when_sufficient` 必须为 `true`；
- `recommendation_enabled` 或 `choice_generation_enabled` 不表示每轮必须制造选项；只有存在合理候选时才生成，无法诚实提供候选时可以提出一个开放式主问题；
- Interactive Skill 仍是 `kind: skill`，不得据此创建 Human Gate 或 Subgraph。

`output_contracts` 是全部 23 个 `0.2.0` `skill.yaml` 的必填数组。每项必须声明 `artifact_type`、`write`、支持可选 JSON Pointer 的 Bundle 内 `schema_ref`，以及可为 `null` 或指向 `templates/*.md` 的 `template_ref`。`output_contracts[*].write` 去重后的集合必须与顶层 `writes` 完全一致；Template 只约束 Markdown 表达层，不替代结构化 Artifact Schema。空输出 Skill 必须显式使用空数组，不能省略该字段。

---

# 10. Artifact Contract

所有 Artifact 必须带 Metadata Header。

YAML 示例：

```yaml
artifact:
  id: ART-001
  type: idea_definition
  schema_version: 0.2.0
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

v0.2 明确排除：Interaction Checkpoint 不带 Artifact Metadata Header，不注册新的 Artifact Type，不写入 Current Manifest。它属于 Attempt Runtime State；只有完成或达到安全收束条件后生成的 `idea_definition` 才是下游可读取的业务 Artifact。

---

# 11. Directory Layout

以下树描述完整 `contracts/0.2.0/` Bundle 的内容形状；实际实现时它位于第 5.1 节 Registry 指定的 Bundle Root。现有仓库根目录同形契约继续表示不可变 `0.1.0`，不得原地改造成 v0.2。

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
│       └── <attempt-id>/
│           └── checkpoints/
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

完整 v0.2 Bundle 必须包含 23 个 Standard Skill Contract；`competitor-verifier` 是第 23 个 Skill，不能以内嵌 Verifier 逻辑替代其 `SKILL.md`、`skill.yaml` 和 `output_contracts`。

五个 v0.2 Markdown Template 必须以可安全解析的 YAML front matter 开头：

```yaml
---
template:
  id: competitor-report
  version: 0.2.0
  artifact_type: competitor_report
---
```

`template.id` 必须等于文件名去掉 `.md` 后的 stem，`version` 固定为 `0.2.0`。规范映射为：`competitor-report.md → competitor_report`、`synthesis.md → research_synthesis`、`product-definition.md → product_definition`、`feasibility.md → feasibility_review`、`prd.md → prd`。Skill 通过 `output_contracts[*].template_ref` 引用 Template；Template 只负责 Markdown 结构，不替代或放宽同一输出的 `schema_ref`。

---

# 12. Idea Definition Schema

```yaml
artifact:
  type: idea_definition
  schema_version: 0.2.0

idea:
  original:
  normalized_summary:

problem:
  statement:
  trigger:
  current_alternative:
  pain_hypothesis:

target_users:
  primary: []
  secondary: []

scenario:
  primary_context:
  trigger:
  desired_outcome:

jtbd:
  functional:
  emotional:
  social:

value_proposition:
  core_value:
  why_better_hypothesis:

solution:
  direction_hypothesis:
  alternatives_considered: []
  core_mechanism:

scope:
  initial_boundary:
  non_goals: []

assumptions:
  - id:
    type: problem
    claim:
    status: unvalidated
    criticality: high

unknowns:
  - id:
    dimension: user
    question:
    researchable: true

research_seeds:
  competitor_questions: []
  user_questions: []
  market_questions: []
  technology_questions: []

clarity:
  problem: LOW
  user: UNKNOWN
  scenario: UNKNOWN
  value: LOW
  mechanism: LOW
  overall: PARTIAL

confidence:
  overall: low
  basis:

shaping:
  mode: PARTIAL
  rounds_used: 3
  completion_outcome: PARTIAL_RESEARCHABLE
```

规范约束：

- `assumptions[].type` 只接受 `user | problem | behavior | solution | market | technical`；
- Idea Definition 中的 Assumption Status 只能是 `unvalidated`；Research 后的 `VALIDATED | PARTIALLY_VALIDATED | INVALIDATED | UNKNOWN` 属于 Claim / Research Synthesis，不回写成 Idea Definition 事实；
- `unknowns[].researchable: false` 的项继续保留为 Limitation，不强制生成 Research Question；
- `clarity` 的五个维度使用 `UNKNOWN | LOW | MEDIUM | HIGH`，`overall` 使用 `CLEAR | PARTIAL | VAGUE`；
- `shaping.completion_outcome` 使用 `SUFFICIENT | PARTIAL_RESEARCHABLE | INSUFFICIENT_PRODUCT_CONTEXT`；
- `rounds_used` 是发出的主问题数，范围为 `0..max_rounds`；
- v0.1 `proposed_solution` 的 v0.2 结构映射是 `solution.direction_hypothesis`，该映射不增加验证状态；
- 空值、Unknown 和 Partial 是合法结果，禁止为满足字段完整性编造内容。

## 12.1 Completion Criteria

Idea Shaping 在以下条件满足时可以完成：

```text
Problem         = defined OR explicitly_unknown
Primary User    = defined OR explicitly_unknown
Primary Scenario= defined OR explicitly_unknown
Core Value      = hypothesis available
Core Mechanism  = hypothesis available
Critical Assumptions = recorded
Major Unknowns       = recorded
Research Questions   = derivable
```

达到条件后必须 Early Exit，不要求完成所有维度或固定轮数。

路径收束规则：

- `CLEAR` 默认零次交互；仅存在阻止 Research Question / Contract 生成的歧义时允许一次 `clarification`，不得连续追问；
- `PARTIAL` 按最新信息缺口渐进选择 Method，并在达到 Completion Criteria 时立即结束；
- `VAGUE` 可以动态使用 Controlled Brainstorming 或 Adaptive Product Discovery Interview，也可切换到 Clarification / Assumption Challenge；用户始终可以拒绝选项、修改选项或自由输入；
- 所有路径共享同一 Completion Criteria、同一 Attempt 状态和同一 `idea_definition` 输出。

达到 `max_rounds = 8` 时：

- Research Questions 可派生：发布 Idea Definition，`completion_outcome: PARTIAL_RESEARCHABLE`，Idea Node 正常完成；
- Research Questions 不可派生：仍保存部分 Idea Definition，`completion_outcome: INSUFFICIENT_PRODUCT_CONTEXT`，Executor 返回可恢复 `FAILED`，Idea Node 为 `BLOCKED`，Workflow 为 `PAUSED`，Contract Node 保持 `PENDING`；
- 后续用户主动补充上下文时通过显式 Retry 创建新 Attempt，旧 Attempt 不得继续发出第 9 个问题。

## 12.2 Boundary with Product Definition

Idea Definition 是 Research 前 Hypothesis Model，可以包含 JTBD、Value、Direction、Mechanism 和 Alternatives Hypothesis，但不得包含：

- Validated Differentiation；
- Evidence-backed Positioning；
- Final Product Boundary；
- Confirmed Product Direction。

上述内容只能由 Research Synthesis、Opportunity Mapping、Product Direction Gate 和 Product Definition 产生。

---

# 13. Research Contract Schema

```yaml
artifact:
  type: research_contract

profile_ref: developer_tool@0.2.0

effective_research:
  competitor: required
  users: required
  market: required
  technology: required

research_questions:
  competitors:
    - id: RQ-COMP-01
      question:
      origin_refs: [ASM-001, "research_seeds.competitor_questions[0]"]
  users:
    - id: RQ-USER-01
      question:
      origin_refs: [UNK-001]
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

## 13.1 Research Question Derivation

规范数据链：

```text
Idea Assumption / Unknown / Research Seed
→ Research Question
→ Research Node
→ Evidence / Claim
→ VALIDATED | PARTIALLY_VALIDATED | INVALIDATED | UNKNOWN
```

派生规则：

- 每个 Critical Assumption 必须映射至少一个 Research Question，或记录明确的 `not_researchable_reason`；
- 每个 `researchable: true` 的 Major Unknown 必须映射至少一个 Research Question；
- Research Seed 可以补充问题，但不得把 Seed 或 Hypothesis 标为事实；
- 每个 Research Question 必须包含一个或多个 `origin_refs`；
- 合并重复问题时保留全部来源引用；
- `researchable: false` 的 Unknown 保留在 Contract Limitation，不强制映射到 Research Node；
- Research Contract 继续由 Research Scope Gate 批准；
- Research 结果写入 Claim / Synthesis，不把 Idea Definition 原地改写为 Evidence-backed Fact；
- v0.2 不增加 `return_to_idea_shaping` 顶层回边。若关键假设被推翻，由 Research Synthesis 记录结果并由 Opportunity Mapping 生成新方向。

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

`subgraphs/competitor-research.yaml` 必须通过同一 Bundle 的 `schemas/subgraph.schema.json`。根形状固定为：

```yaml
subgraph:
  id: competitor-research
  version: 0.2.0
  schema_version: 0.2.0

inputs: []

output_contracts:
  - artifact_type: competitor_report
    producer: visualization
  - artifact_type: competitor_verification
    producer: competitor_verifier

nodes: {}
```

顶层只允许 `subgraph`、`inputs`、`output_contracts` 和 `nodes`。每个输出必须声明存在于 `nodes` 中的 `producer`；内部 Node 复用 `workflow.schema.json#/$defs/node` 的 kind / implementation 形状，并接受 Subgraph DAG、Skill 引用与输出 Producer 的跨文件闭包校验。

内部 Node ID 与 Skill ID 必须分型：Node ID 统一为 `snake_case`，Skill ID 继续使用连字符。固定映射为：`discovery → competitor-discovery`、`candidate_ranking → competitor-ranking`、`deep_dive → competitor-deep-dive`、`normalizer → competitor-normalizer`、四个 `*_analysis → competitor-analysis`、`visualization → competitor-visualization`、`competitor_verifier → competitor-verifier`。Runtime Target、`retry_targets`、`return_to` 和 `producer` 只使用 Node ID；Skill Invocation 只使用 Skill ID。

```text
discovery
        ↓
candidate_ranking
        ↓
 ┌──────┼──────┬──────┐
 ↓      ↓      ↓      ↓
deep   deep   deep   deep
A      B      C      D
 └──────┼──────┴──────┘
        ↓
normalizer
        ↓
competitor-dataset
        ↓
 ┌────────────┬────────────┬────────────┬────────────┐
 ↓            ↓            ↓            ↓
feature_     traction_     review_      pricing_
analysis     analysis      analysis     analysis
 └────────────┴──────┬─────┴────────────┘
                     ↓
               visualization
                     ↓
           competitor_verifier
          ↙         ↓          ↘
        FAIL      PARTIAL      PASS
         ↓          ↓           ↓
 targeted retry  propagate    report
```

Subgraph Contract：

- 输入：Idea Definition、Research Contract、Profile 与 Source Index；
- 输出：candidate set、ranking、每个入选竞品的 Deep Dive、normalized dataset、analysis、Profile-required visualizations、competitor report 与 verification result；
- `candidate_ranking` 必须保存 selection methodology 与被排除候选的理由；
- Deep Dive 使用 fan-out / fan-in，并受 `max_parallel` 约束；
- `competitor_verifier` 是 required、唯一终点的内部 `kind: verifier` Node，不新增顶层 Core Workflow Node；
- Verifier 的 gap 必须包含内部 `retry_targets` 和 `return_to: competitor_verifier`；`competitor-verifier` Skill 的 `output_contracts` 必须引用 `schemas/verification.schema.json#/$defs/competitor_verification`；
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
  "schema_version": "0.2.0",
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

## 32.1 Interactive Input Is Not a Gate

Idea Shaping 中的 Question、Option、Recommendation 和 User Response 是 Skill Execution Input，不是 Gate Contract：

- 不新增 `HUMAN GATE #0` 或 `idea_confirmation` Gate；
- Interactive Skill Node 在等待时是 `WAITING_FOR_USER`，回复后回到 `RUNNING`，不会进入 `APPROVED`；
- `current_gate` 必须保持 `null`，当前问题写入独立 `current_interaction`；
- User Response 写入 Attempt Checkpoint 与 Event Log，不写 Gate Decision；
- 用户选择候选 Direction 只更新 `solution.direction_hypothesis`，不构成正式 Product Direction Decision；
- Profile Extension 不得以“Idea Shaping 需要交互”为由插入额外 Gate。

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
{"ts":"","event":"INTERACTION_METHOD_SELECTED","node":"idea","attempt":"ATT-IDEA-001","method":"clarification","target_unknown_id":"UNK-USER-001"}
{"ts":"","event":"INTERACTION_REQUESTED","node":"idea","attempt":"ATT-IDEA-001","method":"clarification","question_id":"IQ-001","round":1}
{"ts":"","event":"INTERACTION_RESPONSE_RECORDED","node":"idea","attempt":"ATT-IDEA-001","question_id":"IQ-001"}
{"ts":"","event":"ATTEMPT_RESUMED","node":"idea","attempt":"ATT-IDEA-001"}
{"ts":"","event":"IDEA_SHAPING_EARLY_EXIT","node":"idea","attempt":"ATT-IDEA-001","round":3}
{"ts":"","event":"IDEA_SHAPING_MAX_ROUNDS_REACHED","node":"idea","attempt":"ATT-IDEA-002","round":8}
{"ts":"","event":"LEGACY_INPUT_ACCEPTED","source_contract_version":"0.1.0","ref_type":"evidence","content_hash":"sha256:0000000000000000000000000000000000000000000000000000000000000000","matrix_rule":"evidence_seed_v1"}
{"ts":"","event":"LEGACY_INPUT_REJECTED","source_contract_version":"0.1.0","ref_type":"prd","content_hash":"sha256:0000000000000000000000000000000000000000000000000000000000000000","reason":"WORKFLOW_DRIVING_ARTIFACT_BLOCKED"}
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

v0.2：

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
INSUFFICIENT_PRODUCT_CONTEXT
SCHEMA_VERSION_UNSUPPORTED
```

Skill Failure 必须结构化：

```yaml
error:
  code: INSUFFICIENT_EVIDENCE
  recoverable: true
  retry_target: users
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
| `INSUFFICIENT_PRODUCT_CONTEXT` | 保存部分 Idea Definition；Idea Node `BLOCKED`，Workflow `PAUSED`，Contract 保持 `PENDING` | 不自动重试；用户补充上下文后显式 Retry，旧 Attempt 不再继续提问 |
| `SCHEMA_VERSION_UNSUPPORTED` | 拒绝创建或恢复不受支持版本的 Run，并保留原始数据 | 不自动迁移、不消耗 Attempt；需要受测迁移器或匹配版本 Runtime |

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

v0.2 强制规则：

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
  version: 0.2.0

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

v0.2 沿用四种 v0.1 Profile 默认值：

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
init --idea <text|file> --profile <id> [--contract-version 0.2.0] [--legacy-input-refs <file>] --idempotency-key <key>
status --run-id <id>
run --run-id <id> --idempotency-key <key>
pause --run-id <id> --idempotency-key <key>
resume --run-id <id> --idempotency-key <key>
interaction submit --run-id <id> --node-id <id> --attempt-id <id> --question-id <id> [--option <id>] [--text <text|file>] --idempotency-key <key>
gate submit --run-id <id> --gate-id <id> --decision <value> [--input <json>] --idempotency-key <key>
retry --run-id <id> --node-id <id> --idempotency-key <key>
proof submit --run-id <id> --proof-id <id> --input <file> --idempotency-key <key>
inspect --run-id <id> --artifact-id <id>
cancel --run-id <id> --idempotency-key <key>
export --run-id <id> --artifact prd
```

所有命令 stdout 输出统一 Response Envelope；诊断信息写 stderr。退出码：`0` 成功，`2` 输入 / Schema 错误，`3` 状态或 Gate 冲突，`4` 权限 / 安全拒绝，`5` Executor / Source 临时失败，`6` Run 完成但 `NOT_READY`，`10` 未分类内部错误。

CLI 与 API 共享第 50.5 节的版本与 Legacy Ref 规则。`interaction submit` 不接受 Method 参数；Host 只能提交 Option / Freeform Response，不能指定 Brainstorming 或 Interview Method。

---

# 50. Normative Runtime API

## 50.1 Operations and Envelopes

```text
create_run
get_run_state
run_ready_nodes
pause_run
resume_run
submit_interaction_response
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
| `create_run` | `idea`、`profile_id`、可选且只能为 `0.2.0` 的 `contract_version`、可选 `legacy_input_refs`、可选 Contract override | `run_id`、已解析 `contract_version`、初始 State；Clear Fast Path 可返回 Idea / Contract refs，Partial / Vague 可返回含当前 Method 的 `current_interaction` 且 Contract ref 为 `null` |
| `get_run_state` | `run_id` | 当前 State、包含 `method` 的 Current Interaction、Current Gate、Readiness、`contract_version`、`state_version` |
| `run_ready_nodes` | `run_id`、可选 `node_ids` | 已调度 Attempt IDs 与更新后的 State |
| `pause_run` / `resume_run` | `run_id` | 更新后的 Workflow Status |
| `submit_interaction_response` | `node_id`、`attempt_id`、`question_id`、可选 `selected_option_id`、可选 `freeform_text`；后二者至少一个非空 | Accepted Response ref、同一 Attempt 的 Resume schedule 与更新后的 State |
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
  "api_version": "0.2.0",
  "run_id": "run_20260809_001",
  "idempotency_key": "client-generated-key",
  "expected_state_version": 12,
  "payload": {}
}
```

`create_run` 时 `run_id` 省略或为 `null`，且不提供 `expected_state_version`；其他 mutating operation 必须提供二者。

Response envelope：

```json
{
  "api_version": "0.2.0",
  "request_id": "REQ-001",
  "ok": true,
  "state_version": 13,
  "data": {},
  "error": null
}
```

`expected_state_version` 不匹配返回 `STATE_VERSION_CONFLICT`；重复 Idempotency Key 但 Payload 不同返回 `IDEMPOTENCY_CONFLICT`。读取接口不要求 Idempotency Key。`get_source` 只返回 Source Index 中允许留存的元数据与最小摘录，不代理下载外部全文。

Interaction Response 规则：

- `selected_option_id` 与 `freeform_text` 至少一个非空；允许二者同时存在，用于表达“选择后修改”；
- 请求不得包含 `method`、`current_method` 或任何 Method override；Method 由 `idea-intake` 基于 Checkpoint 选择，Host 只展示而不代替 Skill 调度；
- `question_id` 必须等于 State 中的 Current Interaction；过期问题按 State Version Conflict 拒绝；
- 同一 Idempotency Key 和相同 Payload 返回原结果，不重复写 Checkpoint 或增加 Round；
- 同一 `question_id` 已接受不同回复时返回 `IDEMPOTENCY_CONFLICT`，禁止覆盖；
- 接受回复后 Orchestrator 先 append Checkpoint / Event，再将 Node 置为 `RUNNING` 并恢复同一 Attempt；
- Interaction Response 不生成 Decision ref。

## 50.2 Executor Adapter Contract

v0.2 继续只定义三种参考 Adapter Type：

- `fixture`：从版本化 Fixture 生成确定性 Artifact，只用于测试，不得形成真实研究 Claim；
- `manual`：输出结构化执行说明并进入外部等待，用户提交结果后继续；
- `host_agent`：由 Host Agent 在显式权限和预算内执行 Skill。

OpenAI、Anthropic 或其他厂商专用 Adapter 不属于 v0.2 规范范围。

Executor Request：

```yaml
executor_request:
  schema_version: 0.2.0
  run_id:
  node_id:
  attempt_id:
  adapter_type: host_agent
  skill_ref: competitor-discovery@0.2.0
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

Interactive Resume Request 在上述字段外增加：

```yaml
executor_request:
  schema_version: 0.2.0
  run_id: run_20260809_001
  node_id: idea
  attempt_id: ATT-IDEA-001
  adapter_type: host_agent
  skill_ref: idea-intake@0.2.0
  input_artifact_refs: []
  profile_ref: developer_tool@0.2.0
  research_contract_ref: null
  interaction_resume:
    checkpoint_ref: runtime/attempts/ATT-IDEA-001/checkpoints/CP-0003.json
    question_id: IQ-001
    selected_option_id: A
    freeform_text: "先聚焦应届毕业生，但优先解决申请流程失控而不是简历优化。"
  permissions:
    external_access: none
    workspace_write_paths: [artifacts/00-intake/]
  budget:
    timeout_minutes: 20
    max_sources: 0
    token_limit:
    cost_limit:
```

`interaction_resume` 在首次调用时必须缺失，在 Resume 时必须存在。它只能引用同一 Run / Node / Attempt 的最新已接受 Checkpoint。

Executor Result：

```yaml
executor_result:
  schema_version: 0.2.0
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

等待用户的 Result：

```yaml
executor_result:
  schema_version: 0.2.0
  run_id: run_20260809_001
  node_id: idea
  attempt_id: ATT-IDEA-001
  status: WAITING_FOR_USER
  output_artifact_refs: []
  source_upserts: []
  interaction_request:
    method: clarification
    question_id: IQ-001
    round: 1
    dimension: user
    prompt: "你更想优先帮助哪类大学生？"
    options:
      - id: A
        label: 应届毕业生
        description: 聚焦第一次全职求职。
      - id: B
        label: 寻找实习的低年级学生
        description: 聚焦实习准备与申请。
    recommendation:
      option_id: A
      rationale: 触发点和结果更明确。
    allow_freeform_answer: true
  interaction_checkpoint:
    checkpoint_id: CP-0002
    checkpoint_version: 2
    round: 1
    current_method: clarification
    target_unknown_id: UNK-USER-001
    selection_rationale: "Target user blocks scenario and research-question derivation."
    completion_status: IN_PROGRESS
  usage:
    automated_duration_seconds: 8.5
    source_count: 0
    input_tokens: 120
    output_tokens: 180
    estimated_cost:
  error: null
```

Executor 只能返回 Artifact、Source Upsert 或 Interaction Checkpoint 提案；由 Orchestrator 完成 Schema、安全、路径、版本和预算验证后才能写入规范存储。Executor 无权直接修改 Runtime State、Event Log、Decision Log 或 Current Manifest。

v0.2 `executor_result.status` 接受 `COMPLETED | WAITING_FOR_USER | FAILED`：

- `COMPLETED`：`error` 必须为 `null`，`interaction_request` 和 `interaction_checkpoint` 必须缺失；
- `WAITING_FOR_USER`：`error` 必须为 `null`，最终 `output_artifact_refs` 必须为空，且必须携带一个 Interaction Request 和一个 Checkpoint；
- `WAITING_FOR_USER` 的 `interaction_request.method` 与 Checkpoint `current_method` 必须相同，且只接受 `clarification | controlled_brainstorming | adaptive_product_discovery_interview | assumption_challenge`；
- `FAILED`：必须携带符合 Error Taxonomy 的结构化 Error；`INSUFFICIENT_PRODUCT_CONTEXT` 可以同时引用一个部分 Idea Definition，但不得触发 Contract Node；
- 取消和自动执行超时仍映射为 `FAILED`；用户等待本身不是超时或失败。

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

Human Gate、Interactive Skill 用户等待与 External Proof 等待时间不计入 `automated_run_timeout_minutes`。Interactive Attempt 的每个自动执行片段仍累计到 Attempt / Run 自动耗时。Profile / Research Contract 可以在 Host 硬上限内收紧或申请调整；放宽默认值必须显示在 Research Scope Gate 并写入 Decision Log。Idea Shaping 的 `max_rounds` 不属于 Run Policy，不能由 Profile 或 Research Contract 放宽。

## 50.4 Current Manifest Contract

```json
{
  "schema_version": "0.2.0",
  "run_id": "run_20260809_001",
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

Current Manifest 是有效 Artifact 版本的唯一指针真相源；Event Log 提供审计与恢复历史，不能覆盖 Manifest 的当前有效版本。v0.2 只支持单 Orchestrator Writer，不定义多进程锁或 SQLite 后端。

v0.2 继续只支持单 Orchestrator Writer。Interaction Checkpoint 不得出现在 `current_artifacts` 中；它由 Workflow State 的 `current_interaction.checkpoint_ref` 和 Attempt History 引用。Idea Shaping 完成后，只有最终或安全收束的 `idea_definition` 才能成为 Current Artifact。

## 50.5 v0.1 → v0.2 Version Compatibility

版本策略冻结为“并行契约树 + Version Registry”；不采用单套 Schema 混合兼容、原地升级、v0.1 → v0.2 自动 Run 迁移或双 Runtime。

- 根目录 Contract Tree 是不可变 `0.1.0` Baseline，仅支持历史验证与只读审计；`contracts/0.2.0/` 是完整 Current Bundle；
- 新建 Run 默认且只允许 `contract_version: 0.2.0`；所有 `$ref`、Skill/Profile Ref、Schema Version 和 Workflow Version 必须在同一 Bundle 闭包内；
- 当前 Runtime 不允许新建或恢复 v0.1 Run。遇到 v0.1 in-flight State 时返回 `SCHEMA_VERSION_UNSUPPORTED`，保留原始数据并 Fail Closed；不得猜测、补齐或隐式迁移 Interaction State；
- v0.1 Artifact、Attempt、State、Event、Decision 和 Manifest 保持不可变；P0 不实现跨版本 Run Migration，该能力归 P1+；
- 只理解 `COMPLETED | FAILED` 的旧 Executor Adapter 遇到 `WAITING_FOR_USER` 时必须 Fail Closed，不能误判为完成。

`create_run.legacy_input_refs` 的每项必须具有：

```yaml
legacy_input_refs:
  - source_contract_version: 0.1.0
    ref_type: evidence
    ref: runs/legacy-run/artifacts/02-research/evidence/EV-001.json
    content_hash: sha256:0000000000000000000000000000000000000000000000000000000000000000
    purpose: seed_current_research
```

兼容引用规则：

1. Orchestrator 先使用 `source_contract_version` 对应的只读 Schema 验证原对象与 `content_hash`，再检查显式 Compatibility Matrix；未登记版本、类型、用途或校验失败一律拒绝；
2. Compatibility Matrix 默认拒绝。Source、Evidence、Claim 和明确登记为兼容的 Research Artifact 可以作为只读 Seed；接受不表示其结论在 v0.2 中有效；
3. `idea_definition`、Research Contract、Product Definition、Decision、MVP、PRD、Readiness、State、Attempt、Event 与 Manifest 默认禁止跨版本直接复用；
4. 旧引用不得写入 v0.2 Current Manifest，不得直接改变 Node Status、Gate Decision、Verification Result 或 Readiness；
5. 被接受的 Evidence 必须重新经过 v0.2 Freshness、Provenance、安全与 Verification；来源是旧 Run 不构成有效性豁免；
6. 每个接受或拒绝结果写入 Event Log，包含来源版本、Ref、内容哈希、用途、Matrix Rule 和理由；不修改原始 v0.1 数据。

Compatibility Matrix 的最小语义：

| Legacy ref type | Default | v0.2 use |
|---|---|---|
| Source / Evidence / Claim | Reject unless explicitly registered | Read-only research seed；必须重新验证 |
| Compatible Research Artifact | Reject unless type + purpose registered | Read-only research seed；不得驱动状态 |
| Idea / Contract / Product / Decision / MVP / PRD / Readiness | Reject | 不允许跨版本复用 |
| State / Attempt / Event / Manifest | Reject | 只读审计，不允许恢复或导入 |

---

# 51. Testing Strategy

本节定义未来参考 Runtime 的验收 Contract；当前 v0.2 文档交付不表示这些 Runtime 测试已经执行。

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
- Idea Clarity qualitative classification
- Highest-Value Question selection and stable tie-breaking
- Dynamic Method selection across all four enum values, including repeat / skip and stable Method ID tie-breaking
- Early Exit and `max_rounds`
- Interaction Checkpoint versioning and Resume
- User-wait timeout exclusion and automated-segment accumulation
- Registry resolution, same-Bundle reference closure and unsupported v0.1 State rejection
- Legacy Ref source-version validation, default-deny matrix and v0.2 re-verification

## 51.3 Contract Tests

每个 Skill 至少验证：

- Required Inputs
- Required Outputs
- `output_contracts` required fields and exact equality with the top-level `writes` set
- Artifact Schema
- Forbidden missing evidence
- Source Index reference integrity
- Executor Request / Result
- Gate Structured Diff confirmation
- Profile composition and Extension constraints
- Run Policy enforcement
- Optional Interaction Model and `max_rounds` enforcement
- Dynamic `supported_methods` / `selection_policy` and required `interaction_request.method`
- Executor `WAITING_FOR_USER` conditional fields
- Interaction Response choice / freeform constraints
- Idea Definition Assumption / Unknown / Clarity constraints
- Research Question `origin_refs` integrity
- 23 Skill contracts, Subgraph Schema, producer / verifier references and five parseable Template front matters
- All Bundle-local refs resolve to one `contract_version`; Legacy Refs cannot enter Current Manifest

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

### Adaptive Idea Shaping — Clear

完整 Idea 初始评估后 0 次追问；只有阻止 Research Contract 的关键歧义时最多 1 次。达到 Completion Criteria 后立即 Early Exit。

### Adaptive Idea Shaping — Partial

部分 Idea 每轮只提出一个最高价值主问题，在预期 2–5 轮内形成 `SUFFICIENT | PARTIAL_RESEARCHABLE` Idea Definition。

### Adaptive Idea Shaping — Vague

抽象 Idea 可动态选择 Controlled Brainstorming / Adaptive Interview / Clarification / Assumption Challenge，获得 2–4 个候选 framing、Recommendation 与 Freeform 入口；方法可重复、跳过且无固定顺序；不得脑补用户或输出 Feature List；最多 8 轮后收束。

### Dynamic Interaction Method

相同 Idea 和 Checkpoint 输入产生确定性的目标与 Method；Method 出现在 Skill Config、Checkpoint、Executor Result、State 和 Host Response 中，但不形成独立 Node / Attempt / Gate / Artifact，客户端不能覆盖 Method。

### Interactive Resume

Idea Attempt 在 `WAITING_FOR_USER` 时退出进程 → 从 State 和最新 Checkpoint 恢复 → 接受回复 → 使用同一 `attempt_id` 继续；恢复过程不读取完整聊天 Transcript，不增加 Attempt Count。

### Max Rounds — Researchable Partial

第 8 个问题后仍有 Unknown，但可派生 Research Questions → 输出 `PARTIAL_RESEARCHABLE` → Contract 可继续。

### Max Rounds — Insufficient Context

第 8 个问题后仍无法界定可研究方向 → 保存部分 Idea Definition → `INSUFFICIENT_PRODUCT_CONTEXT` → Idea `BLOCKED` / Workflow `PAUSED` / Contract `PENDING`。

### Interaction Is Not Gate

Idea Node 等待时 `current_interaction` 非空、`current_gate` 为空，不产生 Gate Decision；回复后 Node 回到 `RUNNING` 而不是 `APPROVED`。

### Interaction Idempotency

相同 Question、Idempotency Key 和 Payload 重放不增加 Round 或 Checkpoint；冲突 Payload 被拒绝。

### Profile Composition

四个 Profile 的 enabled / optional / disabled Research、required visualizations 与 Extension DAG 均符合 Contract；Consumer Technology 默认 optional，并在 Effective Contract 明确禁用时记录 `PROFILE_DISABLED`。

### Source and Security

Source 去重、STALE、无权访问、PII、Secret、路径逃逸和外部 Prompt Injection 均按 Contract 处理。

### Executor and Budget

Executor timeout、cancel、retry、Idempotency、State Version Conflict、Source / Token / Cost 上限均可复现。

### Version Registry and Legacy Ref

v0.2 新 Run 默认选择完整 `0.2.0` Bundle；混版 `$ref` 被拒绝；v0.1 in-flight State 返回 `SCHEMA_VERSION_UNSUPPORTED` 且原数据不变。未登记 Legacy Ref 默认拒绝；登记的 Evidence 仅作为只读 Seed，并重新经过 Freshness、Provenance 和 Verification。

## 51.5 Required Negative Tests — v0.2

1. Clear Idea 被连续追问 8 次：Fail。
2. 用户无法确定 Target User 时 Agent 自动编造：Fail。
3. Problem 未定义时直接输出完整 Feature List：Fail。
4. Unknown 被写成 Validated Fact：Fail。
5. 发出第 9 个主问题：Fail。
6. Idea Interaction 被实现为 Human Gate：Fail。
7. Resume 必须依赖完整聊天上下文：Fail。
8. 同一 `question_id` 接受两个冲突回复：Fail。
9. `PARTIAL_RESEARCHABLE` 没有可派生 Research Question：Fail。
10. Idea Definition 包含 Validated Differentiation、Evidence-backed Positioning、Final Product Boundary 或 Confirmed Product Direction：Fail。
11. Clarification、Controlled Brainstorming、Adaptive Interview 或 Assumption Challenge 被实现成固定顺序的顶层 Workflow Step：Fail。
12. Idea Interaction 生成 `brainstorm_result`、`interview_result` 或其他独立业务 Artifact：Fail。
13. Completion 已满足，仍为执行预设 Interview 或覆盖全部 Method 而继续提问：Fail。

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

## 52.2 Adaptive Idea Shaping Fixture Suite

该 Suite 与基线业务 Fixture 同属统一 P0 Contract Bundle 和一条集成实现链；可以按测试类别分别统计，但不得解释为“先实现 v0.1、再实现 v0.2”：

| Fixture ID | Path | Input | Expected Interaction |
|---|---|---|---|
| `idea_shaping_clear` | `CLEAR` | 明确 Problem、User、Scenario、Value 和 Mechanism 的 Coding Agent Observability Tool | 默认 0 次；阻塞性歧义时最多 1 次 |
| `idea_shaping_partial` | `PARTIAL` | “我想做一个帮助大学生找工作的 AI” | 预期 2–5 轮，产出可研究 Idea Definition |
| `idea_shaping_vague` | `VAGUE` | “我想做一个 Agent 产品” | 提供 framing / recommendation / freeform，最多 8 轮后收束 |

每个 Fixture 必须保存：Raw Idea、每轮 Interaction Result、Checkpoint、User Response、最终 Idea Definition、Research Contract 与 Expected Negative Assertions。Fixture 只验证契约和行为，不代表真实用户、市场或技术验证。

## 52.3 Live Developer Tool Acceptance

输入：

> 我想做一个读取项目目录并自动展示 Codex / Claude Code 当前执行进度的工具。

这是系统要分析的 Product Idea，不表示 Product Discovery Runtime 自身接管 Codex / Claude Code Runtime。

Live Chain 先验证 Idea Clarity 与 Fast Path，再使用 `host_agent` Executor 和真实可访问 Source，验证：Source provenance、Freshness、Profile-required Artifacts、Research Gap、Gate、PRD Consistency 与三态 Readiness。不得对易变的研究正文、实时指标或排名做 Golden Snapshot。

---

# 53. Recommended P0 Build Order

P0 只允许以下一条集成开发链；每一步同时满足继承的 v0.1 基线与 v0.2 Amendment，不存在“v0.1 实现完成后再追加 v0.2”的第二阶段。

## Step 1

实现 Version Registry、完整 `0.2.0` Contract Bundle，以及 Workflow、Schema、23 个 Skill、Competitor Subgraph、5 个 Template 和 Fixture 的单版本引用闭包。该步必须保留根目录 `0.1.0` Baseline 不变，并建立混版拒绝、v0.1 Fail Closed 与 Legacy Ref 静态契约测试。

## Step 2

实现单一 Orchestrator、Version-selected DAG、Node / Attempt / Interaction / Gate / Retry State Machine、单写者 Artifact Storage、Current Manifest、Event / Decision Log、恢复、语言中立 CLI / API，以及 `fixture | manual | host_agent` 三类通用 Adapter。

## Step 3

实现 `idea-intake` 的动态 Interaction Method、Completion-first 选择、Checkpoint / Submit / Resume、最大轮次与安全收束；只生成统一 Idea Definition。随后独立生成 Research Contract，并在 Research Scope Gate 获批前阻断全部 Research。

## Step 4

实现完整 Competitor Research Subgraph：discovery、candidate ranking、deep dive fan-out / fan-in、normalization、analysis、visualization 与唯一 `competitor_verifier`，并验证 Producer / Retry Target / Return Target 闭包。

## Step 5

实现 User Evidence、Market、OSS / Technical Research，以及 Research Verifier、Evidence Waiver、Gap Loop 和 Synthesis；Research 支路按 Profile 并行，Verifier 与 Synthesis 按依赖串行。

## Step 6

实现 Opportunity、Product Definition、Feasibility、External Proof import / re-review 与 MVP Scope，保持 Product Direction Gate 和 MVP Scope Gate 的阻断语义。

## Step 7

实现 PRD Generator、PRD Consistency Verifier、Build Readiness Verifier、完整 Fixture Suite 与一条 Live Developer Tool Acceptance；只有最终 Verifier 可以写入三态 Readiness。

这样能最早验证核心抽象：

> Skill → Artifact → Evidence → Verification → Next / Retry

本文只冻结顺序，不授权执行上述步骤。Phase 3 Traceability PASS 前继续 `STOP IMPLEMENTATION`。

---

# 54. Frozen Scope Boundary

## 54.1 P0 MUST

- 完整 `0.2.0` Contract Bundle、Version Registry 与 v0.1 immutable audit / Fail Closed；
- Core Workflow、四 Product Profile、Research Contract、Research / Evidence / Verification / Retry、三类标准 Human Gate、条件式 Evidence Waiver、Artifact / State / Resume / Recovery / Budget / Security；
- `idea-intake` Adaptive Idea Shaping、四种动态 Interaction Method、Checkpoint / Submit / Resume、安全收束、统一 `idea_definition` 与 Research Question 溯源；
- Competitor Subgraph、User / Market / Technical Research、Opportunity、Product Definition、Feasibility、MVP、PRD 与三态 Readiness；
- 单写者存储、语言中立 CLI / API、三类通用 Adapter、Fixture Suite 与 Live Acceptance。

## 54.2 P1 SHOULD

- UI Graph；
- Artifact Inspector；
- Better Chart Renderer；
- Incremental Research。

## 54.3 Future / Not Implemented

- 跨版本 Run Migration 属于 P1+ 候选，不在冻结 P1 SHOULD 或 P0；
- Vendor-specific / Distributed Executor Adapters、Cloud Queue、Distributed Workers、SQLite / Multi-writer Storage；
- Team Collaboration、Organization Templates、Workflow Library、Versioned Decisions、Benchmark / Evaluation Suite；
- Dynamic self-modifying graph、Automatic Skill Generation、RL、Long-term Organization Memory、Multi-user RBAC；
- Autonomous Coding、Automatic Deployment、Arbitrary Tool Marketplace、Full External Page Mirroring；
- General-purpose Chat / Brainstorming Platform、Automatic Startup Idea Generation / Scoring、Idea Marketplace；
- Feature-list generation before Problem / User / Scenario / Value clarity、New Idea Confirmation Human Gate、`return_to_idea_shaping` top-level back edge。

P1 / Future 能力不得通过“顺手实现”进入 P0。Vendor-specific Adapter 与分布式能力不得被三类通用 Adapter 的接口抽象解释为已承诺实现。

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

- 与本地、可审计、可恢复的 v0.2 边界一致；
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

## ADR-13：Interactive Skill 不等于 Human Gate

原因：

- Interaction 解决“系统是否理解用户”；
- Human Gate 解决“系统是否被授权跨越关键决策”；
- 混用会污染 Gate Count、Decision Log、State Transition 和治理语义。

## ADR-14：Working State 使用 Attempt Checkpoint

原因：

- Idea Shaping 需要跨进程恢复当前问题、回答历史和 Working Hypothesis；
- 这些数据是临时执行状态，不是下游业务 Artifact；
- 版本化、append-only Checkpoint 同时满足恢复、审计和不污染 Current Manifest。

## ADR-15：Idea Definition 与 Product Definition 分离

原因：

- Idea Definition 是 Research 前 Hypothesis Model；
- Product Definition 是 Research 后经 Gate 选择的 Evidence-backed Decision；
- 分离可以防止 Agent 先下结论再让 Research 证明自己的结论。

## ADR-16：Clarity 使用定性等级

原因：

- 当前没有足以支撑百分制的校准方法、数据集或可靠性模型；
- `UNKNOWN | LOW | MEDIUM | HIGH` 足以支持路径选择和问题优先级；
- 避免向用户展示伪精确的 `83/100`。

## ADR-17：Dynamic Interaction Method 是 Skill 内部策略

原因：

- Clarification、Controlled Brainstorming、Adaptive Interview 与 Assumption Challenge 都服务于同一 Idea Hypothesis 的信息补全；
- 将方法提升为 Node / Subgraph / Gate 会制造固定顺序、额外 Attempt 与业务 Artifact，并改变冻结的 Core Workflow；
- Method 写入 Checkpoint 和 Event 已足以恢复与审计，同时保留运行时动态选择能力。

## ADR-18：并行 Contract Tree + Version Registry

原因：

- 保留已验证 `0.1.0` 闭包和回归能力，避免原地升级破坏历史实例；
- 完整 `0.2.0` Bundle 和单版本解析规则可防止混版实例；
- Registry 由单一 Runtime 解析，不形成双 Runtime 或两次实现链，并支持明确 Fail Closed 与回滚边界。

## ADR-19：Legacy Input 只读、默认拒绝、重新验证

原因：

- 允许复用可追溯的 Source / Evidence 线索，同时避免旧 Decision / State 静默驱动新 Run；
- 来源版本验证、内容哈希和 Compatibility Matrix 使接受范围显式可审计；
- v0.2 Freshness、Provenance 与 Verification 复核防止把历史有效性误当当前有效性。

---

# 56. Definition of Done — Frozen Current Technical Specification

## 56.1 当前文档冻结条件

- [x] SPEC v0.2 已合并 SPEC v0.1 Baseline 与 v0.2 Amendment，成为 FROZEN Current Technical Specification；不宣称 Runtime 已实现
- [x] Core Workflow、四 Product Profile 与 Research Contract 的合成规则无歧义
- [x] Node Status、Verification Result、Gate Decision、Feasibility Result、Workflow Status、Readiness Status 分型完成
- [x] 3 个标准 Gate 与条件式 Evidence Waiver Gate 契约完整
- [x] Research Gap 与 External Proof 回环可由 Workflow Schema 表达
- [x] Competitor Research 定义为 Dataset-first Subgraph
- [x] Source、Evidence、Executor、Profile、Run Policy、Storage、CLI / API、Security 与 Readiness Contract 完整
- [x] PRD Consistency Verifier 与 Build Readiness Verifier 独立
- [x] 公共机器字段与内部 Node ID 统一为 `snake_case`，Skill ID 与 Node ID 映射明确
- [x] 5 个 Fixture + 1 条 Live Developer Tool 验收设计完整
- [x] 所有 YAML / JSON 示例通过静态解析验证
- [x] `CLEAR | PARTIAL | VAGUE`、定性 Clarity、Completion、Early Exit 与 `max_rounds` 语义完整
- [x] One Question、Recommendation、Choice、Freeform、Progressive Disclosure 和 Assumption Challenge 规则完整
- [x] Interactive Attempt Waiting / Resume / Checkpoint / Idempotency / Timeout 语义无悬空引用
- [x] Interaction 与 Human Gate、Attempt Checkpoint 与 Artifact、Idea Definition 与 Product Definition 分型完成
- [x] Idea Definition → Research Contract 的 `origin_refs` 派生规则完整
- [x] 四种 Dynamic Interaction Method 已进入 Skill、Checkpoint、Executor、State / API 和 Test Contract，且不形成固定序列
- [x] Version Registry、完整并行 Contract Tree、v0.1 Fail Closed 与 Legacy Ref 默认拒绝策略已冻结
- [x] 23 个 Skill 的 `output_contracts`、Subgraph Schema、五个 Template 与 Producer / Verifier 引用闭包已回灌
- [x] Clear / Partial / Vague 与 13 个 Negative Acceptance 场景已设计

## 56.2 未来参考 Runtime 完成条件

以下项目不因文档完成而自动视为已实现：

- [ ] Workflow 可从 Idea 跑到 PRD，并支持 DAG、Pause / Resume、Retry、Invalidation 与单写者恢复
- [ ] 四 Product Profile 的 Contract 和 Fixture Test 全部通过
- [ ] Claim → Evidence → Source 可追踪，Unknown / null 不被自动补全
- [ ] Profile-required Visualization 与 Score Methodology 可追踪
- [ ] Partial Waiver、Critical Gap、External Proof 与三态 Readiness 场景通过
- [ ] PRD Consistency 与 Build Readiness 独立验证通过
- [ ] 一条真实 Developer Tool Research 链路通过 Live Acceptance
- [ ] Version Registry、`0.1.0` 回归闭包、完整 `0.2.0` Bundle 与混版拒绝通过测试
- [ ] v0.1 in-flight State 以 `SCHEMA_VERSION_UNSUPPORTED` Fail Closed；Legacy Ref 接受 / 拒绝和重新验证通过测试
- [ ] `idea.schema.json`、Interaction Skill / State / Executor Contract 与正反 Fixtures 落地
- [ ] 同一 Interactive Attempt 可跨进程 Resume，不依赖完整 Chat Transcript
- [ ] 用户等待不消耗自动超时，自动片段耗时正确累计
- [ ] Clear / Partial / Vague、Early Exit、Max Rounds 与 Insufficient Context 端到端场景通过
- [ ] Idea Interaction 不产生 Human Gate 或 Product Direction Decision
- [ ] 四种 Dynamic Interaction Method 可重复、跳过、确定性选择，并且不产生独立 Node / Attempt / Artifact

---

# 57. 核心实现原则

系统实现时始终维持以下边界：

```text
Agent = Executor
Skill = Capability Contract
Workflow = Process
Artifact = Persistent State
Attempt Checkpoint = Recoverable Working State
Evidence = Grounding
Verifier = Quality Control
Gate = Human Decision
Loop = Recovery / Research Expansion
```

最重要的不是“让 Agent 一次脑补出更完整的产品或报告”，而是确保：

> 模糊 Idea 先被诚实地澄清为可研究 Hypothesis；每一个重要产品判断都知道从哪里来、为什么成立、谁确认过、证据不足时回到哪里，以及什么时候才允许进入开发。
