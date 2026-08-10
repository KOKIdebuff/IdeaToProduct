# PRD Consolidation Report

> Date: 2026-08-10  
> Phase: Phase 1 — PRD Consolidation  
> PRD Status: **FROZEN**

## 1. Current Source of Truth

- Historical Baseline: `PRD_v0.1.md`，作为原始产品基线与 diff 参照，保持不变。
- Amendment + Current Source of Truth: `PRD_v0.2.md`。
- Precedence: v0.2 明确修改的需求优先于 v0.1；v0.2 未涉及的 v0.1 需求继承有效。
- Audit Record: `PRD_CHANGELOG.md` 记录每个稳定需求单元的最终决策。

当前产品需求不再解读为“v0.1 阶段→v0.2 阶段”，而是一个已合并的 P0 Product Baseline。

## 2. Consolidation Result

Changelog 共覆盖 90 个稳定需求单元：

| Status | Count |
|---|---:|
| Added | 10 |
| Modified | 32 |
| Inherited | 48 |
| Deprecated | 0 |
| Conflict | 0 |
| Unclear | 0 |

冻结条件已满足：没有未决 Conflict、没有未决 Unclear，也没有任何 v0.1 已批准能力被静默删除。

## 3. Major v0.2 Changes

- Adaptive Idea Shaping 成为 P0 MUST 入口，将 Raw Idea 分类为 `CLEAR | PARTIAL | VAGUE`。
- `idea-intake` 是唯一顶层 Idea Shaping Node；Clarification、Controlled Brainstorming、Adaptive Product Discovery Interview 和 Assumption Challenge 是内部动态 Interaction Method。
- Interaction Method 可根据信息缺口重复、跳过或提前停止，不得被硬编码为固定 Workflow Step。
- Idea Shaping 最终只生成统一 `idea_definition`；不新增 Idea Shaping Subgraph、Human Gate #0、`brainstorm_result` 或 `interview_result`。
- 引入 Completion Criteria、Early Exit、`max_rounds = 8`、`PARTIAL_RESEARCHABLE` 和 `INSUFFICIENT_PRODUCT_CONTEXT`。
- Critical Assumption、Researchable Unknown 和 Research Seed 必须可追溯地派生 Research Question。
- Interactive Input 与 Governance Gate 明确分离，Idea Definition 与 Research 后 Product Definition 明确分离。
- 原 Core Workflow、四种 Product Profile、Research / Verification / Retry、Artifact、Human Gate 和 Build Readiness 能力全部继承。

## 4. Frozen Product Behavior

### 4.1 Input and Interaction

- User Input: 自然语言 Raw Idea。
- `CLEAR`: 默认 0 次追问；只有阻断 Research Contract 的关键歧义时最多 1 次。
- `PARTIAL`: 每轮只解决一个当前最高价值 Unknown，每轮后重新评估 Completion。
- `VAGUE`: 可动态使用 Controlled Brainstorming 或 Adaptive Product Discovery Interview，必须保留拒绝、修改和自由输入。
- Interaction 不是 Human Gate，不生成 Gate Decision，不占用 `current_gate`。

### 4.2 Idea Shaping Completion

Idea Shaping 在 Problem、Primary User、Primary Scenario、Core Value、Mechanism、Critical Assumptions、Major Unknowns 和 Research Question Derivation 达到最低条件后立即 Early Exit。

- 可派生有意义研究问题：输出 `idea_definition`，必要时标记 `PARTIAL_RESEARCHABLE`。
- 无法形成可研究方向：保存部分定义，输出 `INSUFFICIENT_PRODUCT_CONTEXT` 并暂停。
- 任何情况都不得通过编造字段满足 Completion。

### 4.3 Research and Decision Boundaries

- Research Contract 必须先由 Idea Definition 中的 Assumption / Unknown / Research Seed 派生。
- 只有 Research Scope Gate 批准后才能启动大规模 Research。
- Competitor、User Evidence、Market 和 OSS / Technical 支路可根据 Effective Workflow 并行。
- Research Verifier、Evidence Waiver、Research Gap 和定向 Retry 决定是否能进入 Synthesis。
- Product Direction Gate、MVP Scope Gate 与条件式 Evidence Waiver 保持原治理语义。
- 最终输出是基于已批准 Artifact 的 PRD，并由独立 Verifier 输出 `READY_FOR_BUILD | READY_WITH_ACCEPTED_RISKS | NOT_READY`。

## 5. Product Profiles and Artifact Boundary

- P0 保留 `developer_tool`、`ai_agent_product`、`consumer_app`、`b2b_saas` 四种 Profile。
- Profile 只能调整研究支路、优先级、Source、门槛和图表，不得删除 Core Workflow 或放宽 Idea Shaping 诚实性 / 最大轮次约束。
- Artifact 仍是业务状态载体；Conversation 不是唯一状态。
- Interactive Checkpoint 是 Runtime Working State，不是业务 Artifact，不进入 Current Manifest。
- Idea Shaping 的唯一正式 Artifact 是 `idea_definition`；Research 后的正式产品决策仍由 `product_definition` 表达。

## 6. Frozen Scope

### P0 MUST

- 所有未被 v0.2 覆盖的 v0.1 Baseline 能力。
- 完整 Adaptive Idea Shaping Amendment、交互恢复语义、统一 Idea Definition 和对应正反验收。
- Core Workflow、四 Profile、Research Contract、Research Subgraph、Evidence / Verification / Retry、Gate、Artifact / State、Feasibility、MVP、PRD 与 Readiness。

### P1 SHOULD

- Discovery Graph、Artifact Inspector、Competitor Analysis Dashboard、Decision Gate 和 Build Readiness UI。
- Better Chart Renderer。
- Incremental Research。

### Future / Not Implemented

- Vendor-specific / Distributed / Cloud Executor Adapters。
- Team Collaboration、Multi-user Approval、Organization Templates、Workflow Library、Versioned Decisions、Discovery Benchmark / Evaluation Suite。
- Managed Hosting、SaaS 多租户、企业级权限和通用 Marketplace。

## 7. Resolved and Remaining Issues

Resolved:

- 已消除“v0.1 与 v0.2 分别实现”的版本范围歧义。
- 已确定 Brainstorming / Adaptive Product Discovery Interview 是 Idea Shaping 内部动态方法。
- 已确定 UI 体验与 Incremental Research 归 P1，Vendor Adapter 等归 Future。

Remaining `Conflict`: **0**  
Remaining `Unclear`: **0**

## 8. Validation Evidence

- `PRD_v0.1.md` SHA-256: `4F30AF7AD396F618BD3A06F82194CD8BB9A2D1FC378C04D3CD7986EE843CBF94`。
- `PRD_v0.1.md` 在 Phase 1 前后 Git diff 为空。
- v0.1 的 G1–G8、FR-01–FR-24、NFR-01–NFR-10 和 R1–R8 都在 Changelog 中存在唯一决策。
- Changelog Status 全部属于允许枚举，且 `Conflict / Unclear = 0`。
- `PRD_v0.2.md` 已包含 FROZEN 状态、版本优先级、唯一 Workflow、动态 Idea Shaping 方法、P0 / P1 / Future 范围与正反验收。

## 9. Phase Boundary

本次 Phase 1 执行没有读取或修改 SPEC，没有检查现有代码，没有实现 Runtime，也没有授权开始 P0 Coding。

**Recommendation: PRD PHASE 1 COMPLETE — ELIGIBLE TO ENTER PHASE 2 SPEC CONSOLIDATION.**

Phase 2 必须作为独立后续任务开始；在 SPEC 冻结且 PRD ↔ SPEC Traceability 通过前，仍然是 `STOP IMPLEMENTATION`。
