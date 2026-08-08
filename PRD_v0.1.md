# Product Discovery SkillGraph — PRD v0.1

> 文档类型：Product Requirements Document  
> 状态：Draft / Implementation-Ready Design Baseline  
> 版本：v0.1  
> 产品代号：Product Discovery SkillGraph  
> 目标：将“Idea → 研究 → 证据 → 决策 → 可行性 → MVP → PRD”标准化为可重复执行的 Skill Graph  
> 交付边界：本文档定义可直接进入工程实现的产品基线，不表示 Runtime 已实现、已完成真实研究验证或已达到生产可用状态

---

## 1. 文档目的

本文档定义 Product Discovery SkillGraph 的产品目标、用户问题、核心价值、产品边界、用户流程、功能需求、质量门槛、验收标准和阶段规划。

本产品不是一个“自动写 PRD 的 Agent”，也不是一个“竞品分析 Prompt 集合”。它是一套面向产品前期 Discovery 阶段的标准化执行系统：将一个模糊 Idea 拆解为多个具有输入契约、输出 Artifact、证据要求、验证规则和依赖关系的 Skill 节点，并通过 Graph、Human Gate 和 Research Loop 驱动整个产品发现流程。

---

# 2. 产品背景

## 2.1 当前问题

产品从 Idea 到开发之间通常存在一段高不确定性的前期工作，包括：

- 问题定义
- 用户与痛点验证
- 竞品发现与深度分析
- 市场与趋势判断
- GitHub / OSS / 技术生态调研
- 技术可行性分析
- 产品定位与机会选择
- MVP 范围裁剪
- PRD / Spec 沉淀

现实中，这一阶段常见三种工作方式：

1. 由产品经理根据经验临场完成；
2. 把整个任务交给一个“万能研究 Agent”；
3. 使用多个零散 Prompt 分别完成调研、竞品分析、PRD 编写。

这些方式存在共同问题：

- 流程不可复用；
- 调研结果与产品决策混在一起；
- 不同项目每次都从头开始；
- Research Agent 容易边搜边下结论；
- 缺乏统一 Evidence 结构；
- 信息来源、数据新鲜度、结论可信度难以追溯；
- 竞品分析通常停留在文字与表格，没有结构化 Dataset；
- 无法标准化生成可视化图表；
- 没有明确的“证据不足 → 回到哪个节点继续研究”的机制；
- 缺少 Human Gate，容易让 Agent 自动做出不可逆产品决策；
- PRD 容易新增未经前序研究和决策确认的需求；
- 缺乏 READY_FOR_BUILD 的统一质量门槛。

## 2.2 核心机会

将产品 Discovery 从“依赖 Agent 临场思考”升级为：

> 可编排、可验证、可追溯、可中断恢复、可人工确认的 Product Discovery Graph。

系统的核心价值不在某个单独 Skill，而在以下组合：

**Skills + Graph + Artifact + Evidence + Verification + Human Gate + Loop**

---

# 3. 产品愿景

让任何一个软件 / AI / Developer Tool Idea 在进入开发之前，都可以通过一套标准化、可审计的 Discovery 流程完成研究与产品决策。

长期目标：

> 成为“一个 Idea 是否有资格进入开发”的标准化前置层。

---

# 4. 产品定位

## 4.1 一句话定义

**Product Discovery SkillGraph 是一套将 Idea → Research → Evidence → Decision → Feasibility → MVP → PRD 编码成可重复执行 Graph 的产品发现系统。**

## 4.2 不是什么

本产品不是：

- 单一竞品分析 Skill；
- 自动生成长篇报告的研究 Agent；
- 自动替用户决定产品方向的 Agent；
- 项目管理工具；
- 编码执行 Agent；
- 需求管理 SaaS；
- 自动接管 Codex / Claude Code 的 Runtime；
- 任意任务编排平台。

---

# 5. 目标用户

## 5.1 Primary User

### A. AI Agent / Developer Tool Builder

特征：

- 项目强依赖 GitHub、OSS、模型 API、Agent 平台生态；
- 传统市场竞品报告不足以支持产品与技术联合决策；
- 需要判断平台原生能力、开源替代和可复用技术资产带来的机会与风险。

核心需求：

- GitHub / OSS Landscape；
- 开源架构复用分析；
- 平台原生能力风险；
- 技术可行性与 Product Gap 联动；
- 将研究、决策与最终 PRD 保持可追溯一致。

## 5.2 Extended Users

### B. 独立开发者 / Vibe Coder

特征：

- 有 Idea，但产品研究能力有限；
- 容易过早进入编码；
- 习惯使用 Codex / Claude Code / ChatGPT；
- 需要明确“先研究什么、后做什么”。

核心需求：

- 快速把 Idea 结构化；
- 自动完成多源研究；
- 看到竞品数据和图表；
- 明确产品差异化与 MVP；
- 避免做已有成熟产品的重复方案。

### C. AI 产品经理 / 创业团队

特征：

- 同时评估多个方向；
- 需要高质量竞品、市场与技术研究；
- 需要把产品决策过程留痕；
- 希望 Agent 加速研究而不是替代决策。

核心需求：

- 标准化产品前期 SOP；
- 团队可复用；
- 决策依据可追溯；
- 可快速形成 PRD / Spec。

## 5.3 Secondary Users

- Hackathon 团队
- 企业创新团队
- 产品咨询团队
- 投研 / 产品战略人员
- AI Coding Agent 的高级使用者

---

# 6. 用户 Job-To-Be-Done

当我有一个产品 Idea，但不知道它是否值得做、应该怎么做时，

我希望系统能：

1. 先把 Idea 变成可研究的问题；
2. 自动从竞品、用户、市场、GitHub / OSS、技术等多个方向并行获取证据；
3. 把不同来源的数据结构化，而不是只输出散文；
4. 生成可视化竞品分析；
5. 告诉我哪些假设被验证、哪些被否定、哪些仍然未知；
6. 给出多个产品机会方向，而不是直接替我选择；
7. 在关键决策点让我确认；
8. 检查技术可行性；
9. 裁剪出真正能落地的 MVP；
10. 最终生成与前序决策一致的 PRD / Spec。

---

# 7. 产品目标

## 7.1 P0 Goals

### G1 — 标准化 Idea → PRD 流程

所有项目按照统一顶层 Graph 运行。

### G2 — 将 Research 拆为可复用 Skills

至少支持：

- Idea Intake
- Research Contract
- Competitor Research
- User Evidence Research
- Market Landscape
- OSS / Technical Landscape
- Research Verification
- Research Synthesis
- Opportunity Mapping
- Product Definition
- Feasibility Review
- MVP Scope
- PRD Generation

### G3 — 支持并行 Research

竞品、用户、市场、OSS / 技术研究可在 Research Gate 通过后并行执行。

### G4 — 所有重大结论 Evidence-backed

所有关键 Claim 可追溯到 Evidence 与 Source。

### G5 — 竞品分析必须数据化、按 Profile 可视化

竞品分析报告必须包含结构化 Dataset；必选图表的种类和数量由 Product Profile 给出默认值，并可由当前 Project Research Contract 在 Research Scope Gate 中说明理由后调整。

Developer Tool 默认至少包含：

- 结构化 Dataset；
- Feature Coverage Matrix；
- Positioning Map；
- Momentum Comparison；
- OSS Activity。

Pain、Sentiment、Pricing 等图表可由 Research Contract 作为额外要求加入，但不能替代 Developer Tool Profile 的 OSS Activity 默认要求。

### G6 — 支持 Verification Loop

研究不足时，只重跑缺失节点，而非全流程重做。

### G7 — 设置有限 Human Gates

默认 3 个标准 Gate：

1. Research Scope
2. Product Direction
3. MVP Scope

另有 1 个条件式 Gate：

4. Evidence Waiver，仅在 Research Verifier 返回 `PARTIAL` 且缺口可豁免时出现

### G8 — 输出三态 Build Readiness 判定

- 无未解决缺口时输出 `READY_FOR_BUILD`；
- 仅存在经 Evidence Waiver 明确接受的非关键缺口时输出 `READY_WITH_ACCEPTED_RISKS`；
- 存在未解决或不可豁免的关键缺口时输出 `NOT_READY`。

---

# 8. 非目标

v0.1 不做：

- 自动编码实现；
- 自动部署；
- 自学习 / 自修改 Workflow；
- RL；
- 自动无限生成 Skills；
- 多 Agent 市场；
- 企业级权限体系；
- SaaS 多租户；
- 长期组织知识图谱；
- 自动替用户确认 Human Gate；
- 复杂财务预测；
- 无来源的市场规模估算；
- 自动执行真实用户访谈；
- 作为通用工作流引擎。

---

# 9. 核心产品模型

整个系统由以下概念组成：

| 概念 | 定义 |
|---|---|
| Node | Workflow 中的 Skill、Subgraph、Verifier、Human Gate、Router 或 External Input |
| Edge | Dependency / Condition |
| Skill | 具有输入输出契约的能力节点 |
| Subgraph | 作为一个顶层节点被调度、内部拥有独立 DAG 的复合流程 |
| Attempt | 某个 Skill 的一次执行 |
| Artifact | Skill 的结构化输出 |
| Source | 外部来源的独立索引项，供 Evidence 通过 `source_id` 引用 |
| Evidence | 支持或反驳 Claim 的证据 |
| Claim | 系统当前相信或正在验证的判断 |
| Verification | 判断 Artifact / Evidence 是否达到继续条件 |
| Gate | 需要用户决策的节点 |
| Loop | 验证失败后的定向重试路径 |
| Workflow | 节点与边构成的完整流程 |
| Profile | 不同产品类型对应的研究配置 |
| Decision | 用户或系统产生的产品决策记录 |
| Executor | 执行 Skill Contract 并返回结构化结果的适配器 |

实际执行图遵循：

`Core Workflow + Product Profile + Project Research Contract = Effective Workflow`

- Core Workflow 固定产品发现的主干语义；
- Product Profile 调整研究节点启用状态、优先级、来源、验收门槛和必选图表；
- Project Research Contract 定义当前项目需要验证的具体问题与经用户确认的调整；
- 只有某类产品确实存在额外必经步骤时，才允许通过受约束的 Profile Extension 插入节点，不得复制整套 Workflow。

---

# 10. 顶层 Product Discovery Workflow

```text
IDEA
 ↓
idea-intake
 ↓
research-contract
 ↓
HUMAN GATE #1 — Research Scope
 ↓
effective research branches
(enabled by Product Profile + Research Contract)
 ↓
 ┌─────────────────┬─────────────────┬─────────────────┬──────────────────┐
 ↓                 ↓                 ↓                 ↓
competitor       user-evidence      market           technology
subgraph         research           research         research
 └─────────────────┴──────────┬──────┴─────────────────┘
                              ↓
                     research-verifier
                    ↙          ↓           ↘
                  FAIL       PARTIAL       PASS
                   ↓           ↓            ↓
            research-gap   EVIDENCE      research-synthesis
                   ↓       WAIVER GATE          ↑
            targeted retry   ↙     ↘            │
                   └────── retry  accepted ─────┘
                                      ↓
                               opportunity-map
                                      ↓
                           HUMAN GATE #2 — Direction
                                      ↓
                              product-definition
                                      ↓
                              feasibility-review
                         ↙              ↓               ↘
                  NOT_FEASIBLE       BLOCKED        FEASIBLE /
                       ↓               ↓            CONDITIONAL
                  NOT_READY       proof-planner          ↓
                                      ↓               mvp-scope
                           WAITING_FOR_EXTERNAL_PROOF     ↓
                                      ↓        HUMAN GATE #3 — Scope
                               proof-result               ↓
                                      └── re-review   prd-generator
                                                        ↓
                                           prd-consistency-verifier
                                                        ↓
                                           build-readiness-verifier
                                             ↙          ↓          ↘
                                         NOT_READY  READY_WITH_  READY_FOR_
                                                    ACCEPTED_     BUILD
                                                    RISKS
```

---

# 11. 核心用户流程

## 11.1 Flow A — 新 Idea

1. 用户输入 Idea。
2. 系统执行 Idea Intake。
3. 系统生成结构化 Problem / Target User / Solution Hypothesis / Assumptions / Unknowns。
4. 系统生成 Research Contract。
5. 用户确认研究范围。
6. 系统进入并行 Research。

## 11.2 Flow B — Research

Research Gate 通过后，根据 Effective Workflow 并行执行已启用的研究支路。默认候选包括：

- Competitor Research
- User Evidence
- Market Landscape
- OSS / Technical Landscape

Profile 禁用的支路不进入调度，但必须以 `SKIPPED` 状态记录 `PROFILE_DISABLED` 原因和生效的 Profile 版本。

完成后 Research Verifier 检查：

- Coverage
- Evidence
- Freshness
- Conflict
- Missing Data

若为 `FAIL`，Research Gap Planner 只重新触发需要补充的节点。若为 `PARTIAL`，仅当缺口被分类为非关键时才打开 Evidence Waiver Gate；用户可要求补研、接受风险或取消，系统不得静默放行。

## 11.3 Flow C — Product Direction

Research Synthesis 仅在 Verifier 为 `PASS`，或 Evidence Waiver 对非关键缺口形成 `PARTIAL_ACCEPTED` 决策后运行，并汇总：

- Validated
- Partially Validated
- Invalidated
- Unknown
- Contradictions
- Risks
- Opportunities

Opportunity Mapping 生成 2–4 个方向。

用户在 Human Gate #2 选择产品方向。

## 11.4 Flow D — Build Readiness

系统执行：

- Product Definition
- Feasibility Review
- 必要时生成 Proof / Spike Plan
- MVP Scope

用户确认 MVP Scope。

系统生成最终 PRD。

Proof Plan 由外部人员或 Coding Agent 执行；系统进入等待状态，导入符合契约的 Proof Result 后重新运行 Feasibility Review，不在本 Runtime 内自动编写 Spike。

最终由独立的 PRD Consistency Verifier 与 Build Readiness Verifier 输出：

`READY_FOR_BUILD | READY_WITH_ACCEPTED_RISKS | NOT_READY`

---

# 12. 功能需求

## FR-01 Idea Intake

系统必须支持将自然语言 Idea 转成：

- Original Idea
- Problem Statement
- Target Users
- Proposed Solution
- Assumptions
- Unknowns
- Initial Non-goals
- Confidence

### 验收

- 不得自动假设所有 Idea 都值得做；
- Assumption 初始状态默认为 unvalidated；
- 无法判断的信息必须保留 unknown。

## FR-02 Research Contract

系统必须为每个 Idea 生成 Research Contract。

至少包含：

- Research Questions
- Required Evidence
- Required Source Types
- Required Competitor Count
- Required Visualizations
- Stop Conditions
- Loop Limit

### 验收

Research Contract 未批准前，禁止进入大规模 Research。

## FR-03 Human Gate

系统必须支持三类标准用户决策：

`APPROVE | MODIFY | CANCEL`

Direction Gate 额外支持：

`SELECT_OTHER | REQUEST_MORE_RESEARCH`

Evidence Waiver Gate 支持：

`PARTIAL_ACCEPTED | REQUEST_MORE_RESEARCH | CANCEL`

`PARTIAL_ACCEPTED` 只能用于经 Verifier 标记为 non-critical 的证据缺口。安全、合规、数据完整性、核心技术可行性和失败的 required Proof 不得豁免。

### 验收

- Gate 前 Workflow 状态必须保存；
- 用户的自然语言 `MODIFY` 必须先转换成 schema-valid diff，并在用户确认 diff 后生成新的 Artifact 版本；
- 用户修改后仅使受影响后继节点失效；
- 不得无条件重跑已验证且未受影响节点。

## FR-04 Parallel Research

系统必须支持无依赖 Research 节点并行。

默认候选支路：

- competitor
- user
- market
- oss-tech

### 验收

- Effective Workflow 由 Core Workflow、Product Profile 与 Project Research Contract 共同生成；
- Profile 可将研究支路设为 required、optional 或 disabled，但不得删除 Core Workflow 骨架；
- disabled 节点必须记录 `SKIPPED`、`PROFILE_DISABLED` 和 Profile 版本；
- Synthesis 只有在所有 effective required Research 节点通过验证，或 non-critical `PARTIAL` 已由 Evidence Waiver Gate 接受后才可运行。

## FR-05 Competitor Discovery

竞品至少分为：

- Direct
- Indirect
- Substitute
- Adjacent
- Platform Risk

### 验收

每个入选竞品必须至少有一个外部 Source。

## FR-06 Competitor Deep Dive

每个竞品必须支持独立 Deep Dive，并可并行执行。

需覆盖：

- Positioning
- Target User
- Core Workflow
- Features
- Integrations
- UX Model
- Pricing / License
- Traction
- User Feedback
- Strengths
- Weaknesses
- Strategic Threat
- Sources

## FR-07 Competitor Dataset

所有竞品信息必须标准化进入 Dataset。

不得让最终图表直接依赖非结构化文章文本。

Dataset 中：

- 缺失数值使用 null；
- 估算必须标记 estimated；
- Score 必须有 methodology；
- Source 必须可追溯。

## FR-08 Competitor Visualization

每份正式竞品报告必须先形成统一 Dataset。可视化 Artifact 的种类和数量由生效的 Product Profile 决定：

### Profile Defaults

| Profile | 默认必选图表 |
|---|---|
| Developer Tool | Feature Coverage Matrix、Positioning Map、Momentum Comparison、OSS Activity |
| AI / Agent Product | Capability Matrix、Positioning Map、Cost / Performance、Ecosystem / Momentum |
| Consumer App | Feature / UX Matrix、Positioning Map、Pricing 或 Sentiment；第三张必须在 Research Contract 中预先选择 |
| B2B SaaS | Feature Matrix、Positioning Map、Pricing、Integration / Security Coverage |

Research Contract 可以在 Research Scope Gate 中说明理由后调整图表要求。运行中因数据不足而无法满足要求时，不得静默减少图表，必须进入 Research Gap 或 Evidence Waiver。

### 图表输出

每张图至少保存：

```text
data.json
chart-spec.json
chart.svg/png
insight.md
```

### Insight 结构

每张图必须提供：

- Observation
- Interpretation
- Product Implication
- Confidence
- Evidence IDs

## FR-09 Score Transparency

任何综合评分必须公开：

- Metrics
- Weights
- Normalization
- Missing Value Handling

禁止 LLM 无依据直接产生 “92/100”。

## FR-10 User Evidence

系统必须区分：

- Pain
- Frequency
- Severity
- Workaround
- Switching Signal
- Willingness Signal

用户 Evidence 优先来源：

- GitHub Issues
- Reddit
- Hacker News
- Product reviews
- Community discussions
- Interviews

## FR-11 Market Landscape

系统必须回答：

- Why now?
- Why not now?
- Category maturity
- Market drivers
- Barriers
- Platform risk
- Business model patterns

不强制要求 TAM/SAM/SOM，除非有可靠数据。

## FR-12 OSS / Technical Landscape

必须分析：

- Relevant repositories
- Architecture
- Stars / Growth
- Maintenance
- License
- Reusable Components
- Technical Constraints
- Should-not-rebuild
- Should-not-copy
- Product Implications

## FR-13 Research Verification

Verifier 必须检查：

1. Coverage
2. Evidence provenance
3. Freshness
4. Source quality
5. Contradictions
6. Missing required data
7. Visualization requirements

输出：

`PASS | PARTIAL | FAIL`

- `PASS`：所有 effective required checks 通过；
- `PARTIAL`：仅存在可明确列举的 non-critical 缺口；
- `FAIL`：任一 critical check 失败，或 required Artifact / Source provenance 缺失。

`PARTIAL` 是 Verification Result，不是 Node Status，也不等于已获批准。

## FR-14 Research Gap

FAIL 后必须输出：

- Missing Claim / Data
- Required Action
- Target Skill
- Existing Data Reuse
- Retry Count

不得直接整套 Research 全部重跑。

## FR-15 Loop Policy

默认：

- max_retries_per_node = 2
- max_global_research_cycles = 2

超过限制后：

- non-critical 缺口 → 打开 Evidence Waiver Gate；
- critical 缺口 → `NOT_READY`，不得通过人工 Gate 绕过。

找不到证据时：

`INSUFFICIENT_EVIDENCE`

禁止编造。

## FR-16 Research Synthesis

必须输出：

- Validated
- Partially Validated
- Invalidated
- Unknown
- Contradictions
- Risks
- Opportunities

Research Synthesis 不得直接生成最终 PRD。

## FR-17 Opportunity Mapping

至少生成 2 个产品方向，最多默认 4 个。

评分维度可包含：

- Pain Strength
- Differentiation
- Feasibility
- Timing
- Defensibility
- MVP Cost

系统可以给 Recommendation，但最终方向由用户 Gate 决定。

## FR-18 Product Definition

必须形成：

- Problem
- Target User
- JTBD
- Value Proposition
- Core Object
- Core Workflow
- Differentiation
- Product Boundary
- Non-goals
- Success Definition

## FR-19 Feasibility Review

必须从 Engineering 视角检查：

- Data Availability
- API Availability
- Platform Constraints
- Architecture
- Security
- Performance
- Operational Complexity
- Implementation Cost
- Critical Assumptions

结果：

`FEASIBLE | CONDITIONALLY_FEASIBLE | BLOCKED | NOT_FEASIBLE`

## FR-20 Proof Planner

Critical Blocker 需要实际验证时，系统生成 Proof / Spike Plan。

至少包含：

- Question
- Hypothesis
- Experiment
- Inputs
- Pass Criteria
- Fail Criteria
- Expected Artifact

系统不执行 Proof 或编写 Spike。生成计划后进入 `WAITING_FOR_EXTERNAL_PROOF`；外部人员或 Coding Agent 执行后提交符合契约的 Proof Result，系统验证其结构和 Evidence，再重新运行 Feasibility Review。required Proof 失败或缺失时不得进入 MVP Scope。

## FR-21 MVP Scope

输出：

- Phase Goal
- Must Have
- Should Have
- Later
- Non-goals
- Success Metrics
- Exit Criteria

系统必须主动区分愿景与 Phase 1。

## FR-22 PRD Generation

PRD 只能基于已批准 Artifact 生成。

如果生成新的 P0 Requirement：

- 必须引用已批准 Decision；
- 否则 Verification Fail。

PRD 生成后必须由独立的 `prd_consistency_verifier` 检查，再由独立的 `build_readiness_verifier` 输出最终 Readiness；Generator 不得自证一致性或可开发性。

## FR-23 Decision Log

每个重大决策必须保存：

- Question
- Decision
- Rationale
- Evidence
- Alternatives
- Reversible / Irreversible

## FR-24 Workflow State

系统必须支持：

- Pause
- Resume
- Retry
- Skip（仅非 required）
- Invalidate downstream
- Resume from last verified node
- Wait for External Proof
- Cancel

Node Status、Verification Result、Gate Decision、Feasibility Result、Workflow Status 与 Readiness Status 必须是相互独立的类型，不得复用同一个字符串表示不同语义。

---

# 13. Product Profiles

四种 Profile 都属于 v0.1 的规范范围，并复用同一 Core Workflow。Profile 只能调整研究支路、优先级、Source 类型、门槛、图表和研究重点；不得删除 Core Workflow 的 Intake、Contract、Verify、Synthesis、Gate、Opportunity、Feasibility、MVP、PRD 与最终 Verifier。

通用研究默认值为：5 个竞品、8 个主要来源、15 条用户 Evidence、5 个 OSS / Technical 项。Profile 可以提供更具体的默认值；Project Research Contract 可以在 Research Scope Gate 中说明理由后收紧或放宽。

## 13.1 Developer Tool (`developer_tool`)

Required Research：

- Competitor
- User Evidence
- Market
- OSS / Technical

Required Visualizations：

- Feature Coverage Matrix
- Positioning Map
- Momentum Comparison
- OSS Activity

Research Focus：Integrations、Platform Risk、Technical Architecture、Reusable Components。

## 13.2 AI / Agent Product (`ai_agent_product`)

Required Research：Competitor、User Evidence、Market、OSS / Technical。

Required Visualizations：Capability Matrix、Positioning Map、Cost / Performance、Ecosystem / Momentum。

Research Focus：

- Models / APIs
- Papers
- Agent Frameworks
- OSS
- Platform-native capability risk

## 13.3 Consumer App (`consumer_app`)

Required Research：Competitor、User Evidence、Market。

Optional Research：OSS / Technical；禁用时必须记录 `PROFILE_DISABLED`。

Required Visualizations：Feature / UX Matrix、Positioning Map，以及在 Research Contract 中预先选择的 Pricing 或 Sentiment。

Research Focus：

- App Store
- Social
- Reviews
- Pricing
- UX

## 13.4 B2B SaaS (`b2b_saas`)

Required Research：Competitor、User Evidence、Market、OSS / Technical。

Required Visualizations：Feature Matrix、Positioning Map、Pricing、Integration / Security Coverage。

Research Focus：

- Buyer / User Split
- Workflow
- Pricing
- Security
- Integrations
- Procurement Constraints

## 13.5 Profile Extension 约束

- 仅在某类产品存在独立必经步骤时使用；
- 必须声明 `insert_after`、`before`、`required` 与配置；
- 合成后的 Effective Workflow 必须仍为 DAG；
- 不得删除核心节点、绕过 Human Gate、Evidence、Source、安全或 Build Readiness 规则；
- 新增 Human Gate 必须在 Profile 中显式说明必要性，不能由 Skill 临时创建。

---

# 14. Artifact 体系

```text
artifacts/
├── 00-intake/
├── 01-contract/
├── 02-research/
│   ├── competitors/
│   ├── users/
│   ├── market/
│   ├── technology/
│   └── source-index.json
├── 03-analysis/
│   ├── dataset/
│   ├── charts/
│   └── synthesis/
├── 04-decisions/
├── 05-product/
├── 06-feasibility/
└── 07-prd/
```

原则：

- Artifact 是状态载体；
- Conversation 不是唯一状态；
- 下游 Skill 默认读取 Artifact；
- 每个 Artifact 带 version / created_at / produced_by；
- Artifact、Attempt、Event 与 Decision append-only；
- 当前有效版本由 `current_manifest` 指向；
- Source 由每个 Run 独立的 Source Index 管理，Evidence 仅引用 `source_id`。

---

# 15. Build Readiness 质量门槛

只有同时满足：

- Problem defined
- Target user defined
- Research contract approved
- Effective Workflow 中所有 required Research 已通过验证，或只存在经 Evidence Waiver 接受的 non-critical 缺口
- 所有 disabled Research 节点具有 `PROFILE_DISABLED` 原因
- Critical assumptions recorded
- Product opportunity selected
- Product boundary defined
- Feasibility reviewed
- Critical blockers resolved；critical blocker 不得通过风险接受绕过
- 所有 required Proof 已提交并通过复审
- MVP scope frozen
- Non-goals defined
- PRD generated from approved artifacts
- PRD consistency verifier passed

Build Readiness Verifier 按以下规则输出：

- `READY_FOR_BUILD`：以上条件全部通过，且不存在被接受的证据缺口；
- `READY_WITH_ACCEPTED_RISKS`：以上条件全部通过，但存在 Evidence Waiver 明确接受的 non-critical 缺口；
- `NOT_READY`：存在未解决或不可豁免的 critical 缺口、required Proof 失败、PRD 不一致或其他 required 条件未通过。

`READY_WITH_ACCEPTED_RISKS` 不得用于安全、合规、数据完整性或核心可行性风险。

---

# 16. 关键页面 / 交互（若实现 UI）

## 16.1 Discovery Graph

展示：

- Node
- Edge
- Status
- Parallel branches
- Current gate
- Retry loop

Node 状态：

- PENDING
- READY
- RUNNING
- COMPLETED
- VERIFYING
- VERIFIED
- WAITING_FOR_USER
- WAITING_FOR_EXTERNAL
- APPROVED
- BLOCKED
- FAILED
- RETRY_READY
- SKIPPED
- INVALIDATED

`PASS | PARTIAL | FAIL` 作为独立的 Verification Result Badge 展示，不进入 Node Status 枚举。

## 16.2 Artifact Inspector

用户点击 Node 查看：

- Inputs
- Outputs
- Sources
- Evidence
- Verification
- Attempts

## 16.3 Competitor Analysis Dashboard

展示：

- Feature Matrix
- Positioning
- Growth / Momentum
- Pain / Sentiment
- Dataset Table
- Source Provenance

## 16.4 Decision Gate

展示：

- Decision Question
- Recommended Choice
- Alternatives
- Evidence
- Risks
- Buttons

## 16.5 Build Readiness

展示：

- Passed checks
- Blockers
- Open Questions
- READY_FOR_BUILD / READY_WITH_ACCEPTED_RISKS / NOT_READY

---

# 17. 非功能需求

## NFR-01 可追溯性

任意最终结论必须可反查：

`Decision → Claim → Evidence → Source`

## NFR-02 可恢复性

进程中断后不得依赖完整聊天上下文恢复。

## NFR-03 幂等性

同一 Skill 在输入未变化时应尽量避免重复写入不同结果。

## NFR-04 可扩展性

新增 Skill 不应要求修改所有现有 Skill。

## NFR-05 模型无关

Skill Contract 不绑定 Codex / Claude / GPT 某单一执行器。

## NFR-06 人机边界清晰

关键产品方向不得默认由 Agent 自动批准。

## NFR-07 安全边界

- 外部 Source 内容一律视为不可信数据，不得作为改变系统指令或权限的依据；
- 外部研究默认只读，文件写入仅限 Discovery Workspace；
- 必须隔离 Prompt Injection，秘密不得进入 Artifact，PII 仅按最小必要原则保存；
- 不得抓取登录、付费墙或无权访问的内容。

## NFR-08 成本与运行预算

默认 `max_parallel = 4`、自动 Attempt 超时 20 分钟、每个 Research Node 最多 50 个 Source、每节点初次执行加 2 次重试、最多 2 个全局研究循环、自动运行总时长上限 120 分钟。Human Gate 与 External Proof 等待不计入自动运行时长。Token / 费用硬上限由 Host 提供；Profile 与 Research Contract 只能在 Host 上限内调整。

## NFR-09 结果诚实性

Fixture 只用于确定性契约与状态测试，不得表述为真实市场、用户或竞品验证。Live Research 必须保留真实 Source provenance、访问时间与新鲜度。

## NFR-10 实现中立

公共 Workflow、Schema、CLI 与 API Contract 不绑定实现语言。Python 仅作为首个参考实现建议，不是产品硬约束。

---

# 18. 成功指标

v0.1 可采用：

### Workflow Completion

- 固定 5 个 Fixture Idea，至少 4 个可跑完整条主流程；
- 所有 Schema、状态、安全与 Skill Contract 测试必须 100% 通过；
- 另运行 1 条 Developer Tool Live Research 链路，只验证真实 Source 追踪、Freshness、Schema 与流程，不快照易变研究内容。

### Traceability

- 100% 的重大 Claim 具有 Evidence ID 或明确标记 INSUFFICIENT_EVIDENCE。

### Research Quality

- 竞品报告 required visualization completion = 100%。

### Decision Consistency

- PRD 新增未经批准 P0 Requirement 的比例 = 0。

### Recovery

- 中断后可从最近 VERIFIED Node 恢复。

### Efficiency

- Verification Fail 后能够定向重跑，而不是全量重跑。

---

# 19. 风险

## R1 — Research “看起来很完整”但事实错误

缓解：

- Source provenance；
- Tier hierarchy；
- Freshness；
- Verifier。

## R2 — Agent 为了完成流程编造数据

缓解：

- null / unknown 是合法值；
- 禁止强制补齐；
- Evidence requirement。

## R3 — Score 主观化

缓解：

- methodology 强制；
- 原始指标与综合分同时展示。

## R4 — Workflow 太重

缓解：

- Profile；
- Required / Optional 节点；
- 3 个标准 Human Gate；Evidence Waiver 仅条件触发。

## R5 — 无限 Research

缓解：

- Retry policy；
- Global cycle cap；
- Escalate to user。

## R6 — PRD 与前序决策漂移

缓解：

- Artifact-only generation；
- Decision Log；
- 独立 PRD consistency verifier 与 build readiness verifier。

## R7 — Fixture 被误当作真实研究

缓解：

- Fixture Artifact 明确标记 `fixture` Executor；
- Fixture 结果不得进入真实产品结论；
- Live Acceptance 与 Fixture Acceptance 分开报告。

## R8 — 外部来源中的恶意指令或敏感信息

缓解：

- 所有外部内容作为不可信数据处理；
- Source Index 只保留元数据、内容哈希与必要短摘录 / 摘要，不默认镜像全文；
- Prompt Injection 隔离、秘密过滤、PII 最小化和 Host 权限约束。

---

# 20. 版本范围

## v0.1 — Implementation-Ready Design Baseline

必须完成：

- Workflow YAML
- Skill Contract
- Artifact Schema
- State / Result / Decision / Readiness Contract
- 3 个标准 Human Gate + 条件式 Evidence Waiver Gate
- Research Loop
- Competitor Research Subgraph
- Dataset Normalization
- 四种 Product Profile 规范与 Fixture
- Profile-specific Visualization Contract
- Source Index、Executor、Storage、CLI / API、安全与预算 Contract
- PRD Generator、PRD Consistency Verifier 与 Build Readiness Verifier

本版本交付的是可实施规范，不表示以上 Runtime 已经实现。

## v0.2

可考虑：

- UI Graph
- Artifact Inspector
- Better Chart Renderer
- Incremental Research
- Vendor-specific Executor Adapters

## v1.0

可考虑：

- Team collaboration
- Organization templates
- Workflow library
- Distributed / cloud executor adapters
- Versioned decisions
- Discovery benchmark / evaluation suite

---

# 21. P0 验收场景

## 21.1 固定 Fixture Idea

| ID | Profile | Idea |
|---|---|---|
| `codex_progress_observability` | Developer Tool | 读取项目目录并展示 Coding Agent 执行进度 |
| `api_dependency_change_monitor` | Developer Tool | 识别 API / 依赖变化并提示代码影响范围 |
| `support_ticket_agent` | AI / Agent Product | 基于证据分流与总结支持工单 |
| `shared_household_planner` | Consumer App | 面向共同生活成员的共享计划与提醒产品 |
| `vendor_security_questionnaire_saas` | B2B SaaS | 协助供应商安全问卷收集、证据关联与复核 |

Fixture 由 `fixture` Executor 生成确定性 Artifact，用于验证 Contract、状态机、Profile、回环、Gate、恢复和 Readiness，不得作为真实研究结论。5 个 Idea 中至少 4 个必须完成有效端到端流程；所有 Schema、状态与安全 Contract 测试必须通过。

## 21.2 Live Developer Tool Acceptance

保留以下 Idea 作为唯一 v0.1 Live Research 验收链路：

> “我想做一个读取项目目录并自动展示 Codex / Claude Code 当前执行进度的工具。”

这是 Product Discovery SkillGraph 要分析的输入 Idea，不表示本系统自身接管 Codex / Claude Code Runtime。

系统必须：

1. 生成 Idea Definition 与带 Profile 默认值的 Research Contract；
2. 等待 Research Scope Gate，并展示研究范围、图表要求、预算与任何门槛调整；
3. 根据 Developer Tool Profile 并行执行四类真实研究；
4. 竞品 Subgraph 形成 Dataset 与 4 个 Profile-required 图表；
5. Verify Research；若技术 Evidence 不足，只定向重跑 Technical Research；
6. `PARTIAL` 时只允许对 non-critical 缺口打开 Evidence Waiver；
7. 形成 Synthesis 与 2–4 个机会方向，等待 Product Direction Gate；
8. 完成 Product Definition 与 Feasibility Review；
9. 必要时生成 Proof Plan、等待外部 Proof Result，并重新进行 Feasibility Review；
10. 生成 MVP Scope，等待 MVP Scope Gate；
11. 生成 PRD，依次通过 PRD Consistency Verifier 与 Build Readiness Verifier；
12. 输出 `READY_FOR_BUILD`、`READY_WITH_ACCEPTED_RISKS` 或 `NOT_READY`，并能够追溯判定依据。

Live Acceptance 只固定 Schema、Source provenance、Freshness、必需 Artifact 和状态迁移，不对会随时间变化的研究正文、指标数值或排名做 Golden Snapshot。

---

# 22. 最终产品原则

系统不追求：

> “让 Agent 更聪明地帮我想产品。”

系统追求：

> “把一个 Idea 在进入开发前必须经历的研究、证据、验证和决策过程编码成可重复执行的 Graph。”

这是 Product Discovery SkillGraph 的核心产品边界。
