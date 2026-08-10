# PRD Version Consolidation

> Baseline: `PRD_v0.1.md`  
> Amendment / Current Source of Truth: `PRD_v0.2.md`  
> Consolidation rule: v0.2 明确修改优先；v0.2 未涉及的 v0.1 需求继承；缺席不等于废弃。  
> Status vocabulary: `Added | Modified | Deprecated | Inherited | Conflict | Unclear`

## 1. Classification Rules

- `Added`：v0.2 引入的新产品能力或新规范性边界。
- `Modified`：v0.2 对 v0.1 的意义、范围、验收或优先级做了实质修改。
- `Deprecated`：仅当 v0.2 明确停止某项能力时使用；本次合并没有废弃任何已批准的 v0.1 产品能力。
- `Inherited`：v0.2 未改变，继续按 v0.1 执行。
- `Conflict / Unclear`：只用于未解决问题；冻结时必须为零。

## 2. Requirement Decisions

| Requirement ID / Topic | v0.1 | v0.2 | Final Decision | Status | Source Sections |
|---|---|---|---|---|---|
| DOC-AUTHORITY | v0.1 是 Implementation-Ready Design Baseline | v0.2 原为 Adaptive Idea Shaping Draft | v0.1 作为不可变历史 Baseline；v0.2 作为 Amendment + Current Source of Truth | Modified | v0.1 header; v0.2 header, §1.1 |
| PRODUCT-PURPOSE | 将模糊 Idea 拆成可编排 Discovery Graph | 先澄清为可研究 Product Hypothesis | 保留 Discovery Graph，并将 Adaptive Idea Shaping 固定为入口 | Modified | §1 |
| BACKGROUND | 假设 Idea 可直接结构化 | 识别 Raw Idea 可能不达 Research Input Quality | 必须先评估清晰度，禁止静默补全产品事实 | Modified | §2 |
| VISION | Idea 经可审计 Discovery 后进入开发 | 先形成可研究 Hypothesis | 以“Think clearly → Research objectively”为统一产品愿景 | Modified | §3 |
| POSITIONING | Idea → Research → PRD Graph | Idea → Idea Shaping → Research → PRD Graph | 采用 v0.2 定位，后续 Discovery 主干不变 | Modified | §4 |
| USERS | Primary / Extended / Secondary Users | 用户分层未改 | 完整继承 v0.1 | Inherited | §5 |
| JTBD | 研究、证据、方向、可行性与 PRD | 原 JTBD 未被取消 | 继承原 JTBD，入口增加“把 Idea 想清楚到足以研究” | Modified | §6 |
| G1 | 标准化 Idea → PRD | 标准化 Idea → Idea Shaping → PRD | 以 v0.2 目标为准，Clarity Evaluation 是 Research 前置条件 | Modified | §7.1 G1 |
| G2 | Research 拆为可复用 Skills | 未修改 | 继承 | Inherited | §7.1 G2 |
| G3 | 支持并行 Research | 未修改 | 继承 | Inherited | §7.1 G3 |
| G4 | 重大结论 Evidence-backed | 未修改 | 继承 | Inherited | §7.1 G4 |
| G5 | Dataset-first 竞品分析与 Profile 可视化 | 未修改 | 继承 | Inherited | §7.1 G5 |
| G6 | Verification Loop | 未修改 | 继承 | Inherited | §7.1 G6 |
| G7 | 有限 Human Gates | Idea Interaction 不是 Gate | 继承原 Gate，并禁止新增 Human Gate #0 | Modified | §7.1 G7; FR-03 |
| G8 | 三态 Build Readiness | 未修改 | 继承 | Inherited | §7.1 G8 |
| NON-GOALS | 不编码、不部署、不自修改等 | 增加非通用 Brainstorming、不提前 Feature-ize、不重构后续 Pipeline | 保留原非目标；允许 Idea Shaping 内部受约束的 Brainstorming / Interview | Modified | §8 |
| CORE-MODEL | Node / Edge / Skill / Attempt / Artifact / Gate / Loop 等 | 新增交互语义 | 原概念全部继承；增加非独立调度的 Interaction Method | Modified | §9 |
| INTERACTION-METHOD | 无独立定义 | 存在 Clarification / Brainstorming / Interview / Challenge | 作为 `idea-intake` 内部动态方法，可重复或跳过，不创建 Node / Subgraph / Gate / Artifact | Added | §9; FR-01 |
| CORE-WORKFLOW | `idea-intake` 直接生成 Idea Definition | `idea-intake` 内增 Clarity + Adaptive Shaping | 保留唯一 Core DAG，只扩展入口 Skill 内部行为 | Modified | §10 |
| FLOW-A | 输入 Idea 后直接结构化 | Clear / Partial / Vague 自适应流程 | 采用 v0.2 Flow A，动态方法无固定顺序，最终只输出 `idea_definition` | Modified | §11.1 |
| FLOW-B | Gate 后并行 Research，Verifier 控制后续 | 未修改 | 继承 | Inherited | §11.2 |
| FLOW-C | Synthesis → Opportunity → Direction Gate | 未修改 | 继承 | Inherited | §11.3 |
| FLOW-D | Product Definition → Feasibility → MVP → PRD → Readiness | 未修改 | 继承 | Inherited | §11.4 |
| FR-01 | 非交互 Idea Intake | Adaptive Idea Shaping | 完整覆盖为 Clarity、动态方法、Completion、Early Exit 与安全收束；节点 ID 仍是 `idea-intake` | Modified | §12 FR-01 |
| FR-01-METHODS | 无 | Clarification / Controlled Brainstorming / Adaptive Product Discovery Interview / Assumption Challenge | Agent 按信息缺口选择，不得硬编码固定序列 | Added | §12 FR-01 Dynamic Interaction Methods |
| FR-02 | 生成 Research Contract | 要求从 Assumption / Unknown / Research Seed 派生并保留 `origin_refs` | 继承原字段并增加可追溯派生 | Modified | §12 FR-02 |
| FR-03 | 三类标准 Gate + Evidence Waiver | 明确 Interaction Input 不是 Gate | 保留原 Gate Contract，Idea Shaping 不新增 Gate Decision | Modified | §12 FR-03 |
| FR-04 | 并行 Research | 未修改 | 继承 | Inherited | §12 FR-04 |
| FR-05 | Competitor Discovery | 未修改 | 继承 | Inherited | §12 FR-05 |
| FR-06 | Competitor Deep Dive | 未修改 | 继承 | Inherited | §12 FR-06 |
| FR-07 | Competitor Dataset | 未修改 | 继承 | Inherited | §12 FR-07 |
| FR-08 | Profile-specific Visualization | 未修改 | 继承；产品 UI 层实现归 P1，数据/图表 Artifact Contract 仍属 P0 | Inherited | §12 FR-08; §20 |
| FR-09 | Score Transparency | 未修改 | 继承 | Inherited | §12 FR-09 |
| FR-10 | User Evidence | 未修改 | 继承 | Inherited | §12 FR-10 |
| FR-11 | Market Landscape | 未修改 | 继承 | Inherited | §12 FR-11 |
| FR-12 | OSS / Technical Landscape | 未修改 | 继承 | Inherited | §12 FR-12 |
| FR-13 | Research Verification | 未修改 | 继承 | Inherited | §12 FR-13 |
| FR-14 | Research Gap | 未修改 | 继承 | Inherited | §12 FR-14 |
| FR-15 | Loop Policy | 未修改 | 继承 | Inherited | §12 FR-15 |
| FR-16 | Research Synthesis | 未修改 | 继承 | Inherited | §12 FR-16 |
| FR-17 | Opportunity Mapping | 未修改 | 继承 | Inherited | §12 FR-17 |
| FR-18 | Product Definition | 增强与 Idea Definition 的边界 | 保留 Research 后的 Evidence-backed Product Decision，禁止 Idea Shaping 提前生成 | Modified | §12 FR-18; §14 |
| FR-19 | Feasibility Review | 未修改 | 继承 | Inherited | §12 FR-19 |
| FR-20 | Proof Planner | 未修改 | 继承 | Inherited | §12 FR-20 |
| FR-21 | MVP Scope | 未修改 | 继承 | Inherited | §12 FR-21 |
| FR-22 | PRD Generation | 未修改 | 继承 | Inherited | §12 FR-22 |
| FR-23 | Decision Log | 未修改 | 继承；Interaction Response 不写成 Product Direction Decision | Modified | §12 FR-23; FR-03 |
| FR-24 | Workflow State | 支持 Pause / Resume / Retry / Invalidation | 增加同一 Interactive Attempt 的 Waiting / Resume / Checkpoint / Idempotency | Modified | §12 FR-24 |
| PROFILE-CORE | 四种 Profile 共用 Core Workflow | 增加不得放宽 Idea Shaping 诚实性与轮次上限 | 继承原合成规则并增加 v0.2 约束 | Modified | §13 |
| PROFILE-DEVELOPER-TOOL | Developer Tool 默认值 | 未修改 | 继承 | Inherited | §13.1 |
| PROFILE-AI-AGENT | AI / Agent Product 默认值 | 未修改 | 继承 | Inherited | §13.2 |
| PROFILE-CONSUMER | Consumer App 默认值 | 未修改 | 继承 | Inherited | §13.3 |
| PROFILE-B2B | B2B SaaS 默认值 | 未修改 | 继承 | Inherited | §13.4 |
| PROFILE-EXTENSION | 受约束扩展，不得删除核心节点 | 不得用扩展规避 Idea Shaping 边界 | 继承原规则并禁止放宽 v0.2 约束 | Modified | §13.5 |
| ARTIFACTS | Artifact-only state、append-only、Current Manifest、Source Index | 明确 Checkpoint 非业务 Artifact，Idea Shaping 只产生 `idea_definition` | 继承原体系；禁止 `idea_brief` / `brainstorm_result` / `interview_result` 等新 Artifact | Modified | §14 |
| BUILD-READINESS | 三态质量门槛 | 未改变终态和不可豁免项 | 完整继承 | Inherited | §15 |
| UI-SURFACES | 五个可选关键页面 | 原路线后移 | 五个 UI Surface 与 Better Chart Renderer 归 P1 SHOULD，不影响 P0 Artifact / Visualization Contract | Modified | §16; §20.2 |
| NFR-01 | 可追溯性 | 未修改 | 继承 | Inherited | §17 NFR-01 |
| NFR-02 | 不依赖完整聊天上下文恢复 | 增加 Interactive Working State / Checkpoint | 保留原原则并扩展到 Idea Shaping | Modified | §17 NFR-02 |
| NFR-03 | 输入不变时避免重复写入 | 增加 `question_id` 回复幂等与冲突拒绝 | 采用 v0.2 扩展 | Modified | §17 NFR-03 |
| NFR-04 | 可扩展性 | 未修改 | 继承 | Inherited | §17 NFR-04 |
| NFR-05 | 模型无关 | 未修改 | 继承 | Inherited | §17 NFR-05 |
| NFR-06 | 关键产品决策不得自动批准 | Idea Recommendation 不是 Gate / Evidence / Validated Claim | 继承人机边界并增加 Interaction 限制 | Modified | §17 NFR-06 |
| NFR-07 | 安全边界 | 未修改 | 继承 | Inherited | §17 NFR-07 |
| NFR-08 | 运行预算与超时 | 用户等待不计自动超时，Idea Shaping 最多 8 主问题 | 采用 v0.2 扩展，Host 只能收紧上限 | Modified | §17 NFR-08 |
| NFR-09 | Fixture / Live 结果诚实性 | Clarity / Confidence 不表示 Problem / Market / Solution 已验证 | 采用 v0.2 扩展 | Modified | §17 NFR-09 |
| NFR-10 | 实现中立 | 未修改 | 继承 | Inherited | §17 NFR-10 |
| METRIC-IDEA-SHAPING | 无 | Clear / Partial / Vague / Negative Acceptance 指标 | 纳入 P0 产品成功指标 | Added | §18 Idea Shaping Quality |
| METRICS-BASELINE | Workflow Completion / Traceability / Research Quality / Decision / Recovery / Efficiency | 未取消 | 完整继承 | Inherited | §18 |
| R1 | Research 表面完整但事实错误 | 未修改 | 继承 | Inherited | §19 R1 |
| R2 | Agent 编造数据 | 未修改 | 继承 | Inherited | §19 R2 |
| R3 | Score 主观化 | 未修改 | 继承 | Inherited | §19 R3 |
| R4 | Workflow 过重 | 未修改 | 继承 | Inherited | §19 R4 |
| R5 | 无限 Research | 未修改 | 继承 | Inherited | §19 R5 |
| R6 | PRD 与前序决策漂移 | 未修改 | 继承 | Inherited | §19 R6 |
| R7 | Fixture 被误当真实研究 | 未修改 | 继承 | Inherited | §19 R7 |
| R8 | 外部恶意指令或敏感信息 | 未修改 | 继承 | Inherited | §19 R8 |
| R9 | 无 | Clear Idea 被过度追问 | 纳入 P0 风险与 Early Exit 缓解 | Added | §19 R9 |
| R10 | 无 | Solution / Feature 过早锁定 | 纳入 P0 风险与 Assumption Challenge | Added | §19 R10 |
| R11 | 无 | Recommendation / Confirmatory Bias | 纳入 P0 风险，用户保留拒绝、修改和自由输入 | Added | §19 R11 |
| R12 | 无 | Interactive State 丢失或重复消费 | 纳入 P0 风险与 Checkpoint / Idempotency 缓解 | Added | §19 R12 |
| R13 | 无 | Idea Definition 与 Product Definition 越界 | 纳入 P0 风险并使用 Hypothesis 语义 | Added | §19 R13 |
| R14 | 无 | Idea Shaping 无限循环 | 纳入 P0 风险，使用 Early Exit 和 `max_rounds` | Added | §19 R14 |
| SCOPE-P0 | v0.1 契约基线 | v0.2 原文只声明 Idea Shaping 设计交付 | 合并为一个 P0 MUST：全部未覆盖 v0.1 能力 + 完整 Idea Shaping Amendment | Modified | §20.1 |
| SCOPE-P1 | v0.1 将 UI Graph 等列为后续候选 | v0.2 将其后移评估 | UI Surface Layer、Better Chart Renderer、Incremental Research 固定为 P1 SHOULD | Modified | §20.2 |
| SCOPE-FUTURE | v1.0 候选能力 | Vendor-specific Adapter 后移 | Vendor / Distributed Adapter、Collaboration、Templates、Workflow Library、Versioned Decisions、Benchmark 等归 Future | Modified | §20.3 |
| ACCEPTANCE-FIXTURE | 5 个确定性 Fixture | 未取消 | 继承并与 Idea Shaping Fixture 共同构成 P0 验收 | Inherited | §21.1 |
| ACCEPTANCE-SHAPING | 无 | Clear / Partial / Vague 和 Negative Acceptance | 纳入 P0；增加动态方法、统一状态、无新 Artifact / Gate 验收 | Added | §21.2 |
| ACCEPTANCE-LIVE | Developer Tool Live Research Chain | 入口增加 Clarity / Fast Path | 保留原 Live Chain，首先验证 Idea Shaping 入口行为 | Modified | §21.3 |
| FINAL-PRINCIPLES | 重要判断可追溯且经人确认 | 先澄清 Idea，再客观研究 | 合并为“Think clearly → Research objectively → Evidence → Decision → Build”，严格分离 Idea Shaping / Research / Direction Gate | Modified | §22 |

## 3. Resolved Conflicts and Unclear Items

| Item | Resolution | Final Status |
|---|---|---|
| v0.1 和 v0.2 可能被误解为两个实现阶段 | 改为单一 Consolidated P0，禁止分别实现 | Resolved |
| Brainstorming / Adaptive Interview 是否为独立流程 | 定义为 `idea-intake` 内部动态 Interaction Method | Resolved |
| 旧 v0.2 路线图中 UI / Incremental Research / Vendor Adapter 归属 | UI 体验与 Incremental Research 归 P1，Vendor Adapter 归 Future | Resolved |

Unresolved `Conflict`: **0**  
Unresolved `Unclear`: **0**  
Deprecated approved v0.1 capability: **0**

