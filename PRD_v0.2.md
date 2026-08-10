# Product Discovery SkillGraph — PRD v0.2

> 文档类型：Product Requirements Document  
> 状态：FROZEN / Current Product Requirements  
> 版本：v0.2  
> 产品代号：Product Discovery SkillGraph  
> 目标：将“Idea → Idea Shaping → 研究 → 证据 → 决策 → 可行性 → MVP → PRD”标准化为可重复执行的 Skill Graph  
> 历史基线：PRD v0.1（不可变的 Baseline / diff 参照）  
> 权威规则：PRD v0.2 是 Amendment + Current Source of Truth；明确修改优先于 v0.1，v0.2 未涉及的需求继承 v0.1  
> 冻结边界：FROZEN 表示当前产品需求已确定，不表示 Runtime、Schema、Skill、Fixture 或真实 Research 已实现；只有最终 SPEC 冻结且 PRD ↔ SPEC Traceability 通过后才允许开始 P0 Implementation

---

## 1. 文档目的

本文档定义 Product Discovery SkillGraph 的产品目标、用户问题、核心价值、产品边界、用户流程、功能需求、质量门槛、验收标准和阶段规划。

本产品不是一个“自动写 PRD 的 Agent”，也不是一个“竞品分析 Prompt 集合”。它是一套面向产品前期 Discovery 阶段的标准化执行系统：先将 Raw Idea 澄清到足以被研究的 Product Hypothesis，再将其拆解为具有输入契约、输出 Artifact、证据要求、验证规则和依赖关系的 Skill 节点，并通过 Graph、Human Gate 和 Research Loop 驱动整个产品发现流程。

## 1.1 版本合并与继承规则

- PRD v0.1 作为原始产品基线保留，不得被删除、覆盖或改写；
- PRD v0.2 是当前唯一产品事实来源，它对 v0.1 的明确修改构成 Amendment；
- v0.2 未明确修改的 v0.1 需求继续有效，不得因为本文档没有重复某句文字就推断其已废弃；
- `PRD_CHANGELOG.md` 记录每个稳定需求单元的继承或覆盖决策，与本文档共同用于审计版本差异；
- 当前 P0 是“v0.1 未被覆盖的 Baseline + v0.2 Amendment”的一次性合并交付，禁止先实现 v0.1、再重新实现 v0.2。

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

v0.1 还隐含假设用户虽然表达不完整，但基本知道自己要解决什么问题、服务谁以及产品如何产生价值。现实中的独立开发者、Vibe Coder、AI Developer、Hackathon 团队和非专业产品经理经常只提供一个领域、技术名词或模糊方向。Raw Idea 因此不一定天然达到 Research Input Quality：若系统直接结构化或自动补全，容易把 Agent 的猜测写成用户事实，再让后续 Research 验证 Agent 自己制造的结论。

## 2.2 核心机会

将产品 Discovery 从“依赖 Agent 临场思考”升级为：

> 先帮助用户把模糊 Idea 想清楚到足以研究，再进入可编排、可验证、可追溯、可中断恢复、可人工确认的 Product Discovery Graph。

系统的核心价值不在某个单独 Skill，而在以下组合：

**Skills + Graph + Artifact + Evidence + Verification + Human Gate + Loop**

---

# 3. 产品愿景

让任何一个软件 / AI / Developer Tool Idea 在进入开发之前，都可以先形成可研究的 Product Hypothesis，再通过一套标准化、可审计的 Discovery 流程完成研究与产品决策。

长期目标：

> 成为“一个 Idea 是否有资格进入开发”的标准化前置层。

---

# 4. 产品定位

## 4.1 一句话定义

**Product Discovery SkillGraph 是一套将 Idea → Idea Shaping → Research → Evidence → Decision → Feasibility → MVP → PRD 编码成可重复执行 Graph 的产品发现系统。**

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

### G1 — 标准化 Idea → Idea Shaping → PRD 流程

所有项目按照统一顶层 Graph 运行。Raw Idea 必须先经过 Clarity Evaluation；只有达到可研究条件后，才进入 Research Contract。

### G2 — 将 Research 拆为可复用 Skills

至少支持：

- Adaptive Idea Shaping / Idea Intake
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

v0.2 不做：

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
- 作为通用工作流引擎；
- 通用聊天 Agent 或通用 Brainstorming 平台；
- 固定顺序的 Brainstorming / Interview Workflow；Idea Shaping 可以按当前信息缺口动态调用受约束的 Brainstorming 或 Adaptive Product Discovery Interview，但它们不是独立产品流程；
- Idea Marketplace、自动创业 Idea 生成或创业评分系统；
- 自动判断 Idea 必然成功或失败；
- 用 Feature Brainstorming、UI 原型或 Coding 替代 Product Discovery；
- 自动替用户完成 Product Direction Decision；
- 为 Idea Shaping 重构后续 Research Pipeline 或增加顶层回边。

---

# 9. 核心产品模型

整个系统由以下概念组成：

| 概念 | 定义 |
|---|---|
| Node | Workflow 中的 Skill、Subgraph、Verifier、Human Gate、Router 或 External Input |
| Edge | Dependency / Condition |
| Skill | 具有输入输出契约的能力节点 |
| Interaction Method | `idea-intake` 内部用于解决特定信息缺口的交互方法，可由内部 method / skill 实现，但不是独立调度的 Workflow Node |
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
(single top-level Skill: clarity evaluation + adaptive idea shaping)
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

`idea-intake` 是 Idea Shaping 的唯一顶层节点。Clarification、Brainstorming、Adaptive Product Discovery Interview 和 Assumption Challenge 都是其内部 Interaction Method，由 Agent 根据当前信息缺口动态选择，可重复、跳过或提前结束。它们不新增顶层 Node、Subgraph、Gate 或业务 Artifact，也不改变后续 Research Pipeline。

---

# 11. 核心用户流程

## 11.1 Flow A — 新 Idea

1. 用户输入 Idea。
2. `idea-intake` 先评估 Problem、User、Scenario、Value 和 Mechanism 的清晰度，将 Idea 分类为 `CLEAR | PARTIAL | VAGUE`。
3. `CLEAR` 走 Fast Path：达到最低信息要求时直接形成 Idea Definition，不为了流程完整继续追问；只有阻止 Research Contract 的关键歧义才允许最多一次澄清。
4. `PARTIAL` 进入渐进式澄清：每轮只选择当前最高价值 Unknown，并动态选择 Clarification、Adaptive Interview 或 Assumption Challenge；用户回答后更新 Working Hypothesis 并重新评估 Completion Criteria。
5. `VAGUE` 进入探索式 Shaping：系统可调用受约束的 Brainstorming 或 Adaptive Product Discovery Interview，提供 2–4 个实质不同的 framing、自己的推荐和简短理由，同时保留修改、拒绝和自由输入。
6. Interaction Method 不是固定 Workflow Step；Agent 必须根据当前信息缺口动态选择，可重复、跳过或在 Completion Criteria 满足时立即停止。
7. 系统持续识别 Problem、Target User、Scenario、JTBD Hypothesis、Core Value、Mechanism、Alternatives、Assumptions、Unknowns 和 Research Seeds；不能确认的内容不得自动补全为事实。
8. 达到 Completion Criteria 时 Early Exit；交互最多 8 个主问题，不要求固定轮数。
9. 系统生成统一的 `idea_definition`。若信息不完整但仍能派生研究问题，标记 `PARTIAL_RESEARCHABLE`；若连研究问题都无法形成，则保存部分定义并以 `INSUFFICIENT_PRODUCT_CONTEXT` 暂停。
10. 系统从 Critical Assumptions、Researchable Unknowns 和 Research Seeds 派生 Research Contract。
11. 用户在现有 Research Scope Gate 确认研究范围后，系统进入并行 Research。

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

## FR-01 Adaptive Idea Shaping

系统必须首先判断自然语言 Idea 是否已经足以进入 Research，并根据缺失程度选择 `CLEAR | PARTIAL | VAGUE` 路径。`idea-intake` 的职责不是帮助用户生成更多 Feature，而是把模糊输入转化为可研究的 Product Hypothesis。它是唯一的顶层 Idea Shaping Skill，不得因为存在多种内部 Interaction Method 而拆成固定 Subgraph 或多个 Workflow Node。

Idea Shaping 至少覆盖：

- Original Idea 与 Normalized Summary；
- Problem、Trigger、Current Alternative 与 Pain Hypothesis；
- Primary / Secondary User；
- Primary Scenario、Trigger 与 Desired Outcome；
- Functional / Emotional / Social JTBD Hypothesis；
- Core Value 与 Why-better Hypothesis；
- Product Direction Hypothesis、Alternatives Considered 与 Core Mechanism；
- Initial Boundary 与 Non-goals；
- User / Problem / Behavior / Solution / Market / Technical Assumptions；
- Major Unknowns 与 Research Seeds；
- Problem / User / Scenario / Value / Mechanism Clarity。

### Dynamic Interaction Methods

`idea-intake` 可以在同一 Idea Shaping 阶段与同一统一状态中动态调用：

- **Clarification**：消除一个会阻断 Completion 或 Research Contract 的关键歧义；
- **Controlled Brainstorming**：在输入过于模糊时生成 2–4 个可比较 framing，不生成完整 Feature List；
- **Adaptive Product Discovery Interview**：围绕当前最高价值信息缺口提出一个主问题；
- **Assumption Challenge**：挑战过早锁定的 Problem、User、Value 或 Solution Hypothesis。

Agent 必须根据当前 Clarity、Unknown 的阻断性和预期信息价值选择方法。方法没有固定顺序，可以重复或跳过；一旦 Completion Criteria 满足必须 Early Exit。内部方法不得独立创建 Node、Subgraph、Gate、Attempt 或业务 Artifact；它们只能更新 Idea Shaping Working State，最终仍只产生统一 `idea_definition`。

### Interaction Policy

1. **One Question at a Time**：每轮只能提出一个主问题，解决一个最高价值不确定性；不得发送长问卷。
2. **Recommendation Before Question**：存在合理候选时，先给出 2–4 个实质不同的方向、推荐项和简短理由，再让用户选择。
3. **Prefer Choices Over Blank Questions**：选择题必须保留 `Other / 自定义`，用户可以选择、修改、拒绝或自由输入。
4. **Progressive Disclosure**：只展示当前需要解决的内容，不提前展开商业模式、技术架构、Feature List、MVP 或 PRD。
5. **Do Not Prematurely Feature-ize**：Problem、User、Scenario 和 Value 尚未清楚前，不得用 Feature List 代替产品定义。
6. **Preserve Unknowns**：不能确认的信息必须保存为 Assumption、Unknown 或 Research Question，不得写成事实。
7. **Assumption Challenge**：检查 Problem 是否真实、Workaround 是否足够、Solution 是否过早锁定、Idea 是否只是 Feature、技术能力是否被误当作用户价值、Platform-native Risk 以及 User / Buyer 混淆；无 Evidence 时只能输出 Critical Assumption 或 Research Question，不能宣布 Idea 无效。

### Clarity 与完成条件

各核心维度使用 `UNKNOWN | LOW | MEDIUM | HIGH`，整体路径使用 `CLEAR | PARTIAL | VAGUE`。禁止输出没有明确方法论的百分制 Clarity。

满足以下最低条件即可结束 Idea Shaping：

- Problem：defined 或 explicitly unknown；
- Primary User：defined 或 explicitly unknown；
- Primary Scenario：defined 或 explicitly unknown；
- Core Value：至少存在 hypothesis；
- Product Mechanism：至少存在 hypothesis；
- Critical Assumptions 已记录；
- Major Unknowns 已记录；
- Research Questions 可以派生。

默认 `max_rounds = 8`，它是保护上限而不是目标轮数。系统必须在初始评估和每次用户回答后重新检查 Completion Criteria，并在满足时立即 Early Exit。

达到上限仍不完整时：

- 若能够派生有意义的 Research Questions，输出 `PARTIAL_RESEARCHABLE` Idea Definition 并继续生成 Research Contract；
- 若连可研究的 Problem / User / Scenario 方向都无法界定，保存部分 Idea Definition，返回 `INSUFFICIENT_PRODUCT_CONTEXT` 并暂停，不得继续提问或自动补全。

### 验收

- 清晰 Idea 默认 0 次追问；仅存在阻止 Research Contract 的关键歧义时最多 1 次；
- Partial Idea 能通过 2–5 轮渐进式交互形成可研究 Idea Definition；
- Vague Idea 能获得候选 framing、推荐和自由输入，而不是被要求从空白开始回答；
- 每轮最多一个主问题；
- 用户始终拥有修改和拒绝权；
- Assumption 初始状态只能是 `unvalidated`；
- 无法确认的信息必须保留 Unknown；
- 不得提前生成完整 Feature List、最终 Product Definition、Validated Differentiation 或 Confirmed Product Direction；
- 必须能够从最终 Idea Definition 派生 Research Questions；
- 达到最低信息要求后必须 Early Exit；
- 不得超过 `max_rounds` 或通过自动 Retry 形成无限交互。
- Brainstorming / Adaptive Product Discovery Interview 可被动态重复或跳过，不得被硬编码为固定步骤序列；
- 任何内部 Interaction Method 都不得新增独立 Node、Gate 或 Artifact。

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

Research Questions 必须优先从以下内容派生：

- `idea_definition.assumptions` 中的 Critical Assumptions；
- `idea_definition.unknowns` 中 `researchable: true` 的 Major Unknowns；
- `idea_definition.research_seeds`。

每个派生问题必须保留 `origin_refs`。合并重复问题时保留所有来源引用；不可研究的 Unknown 作为 Limitation 保留，不能通过自动补全消失。

### 验收

Research Contract 未批准前，禁止进入大规模 Research。每个 Critical Assumption 必须映射至少一个 Research Question，或记录明确的不可研究理由；每个 Researchable Major Unknown 必须映射至少一个 Research Question。

## FR-03 Human Gate

系统必须支持三类标准用户决策：

`APPROVE | MODIFY | CANCEL`

Direction Gate 额外支持：

`SELECT_OTHER | REQUEST_MORE_RESEARCH`

Evidence Waiver Gate 支持：

`PARTIAL_ACCEPTED | REQUEST_MORE_RESEARCH | CANCEL`

`PARTIAL_ACCEPTED` 只能用于经 Verifier 标记为 non-critical 的证据缺口。安全、合规、数据完整性、核心技术可行性和失败的 required Proof 不得豁免。

Idea Shaping 中的选项、推荐和用户回复属于 `Interactive Input`，用于帮助系统理解用户，不属于 Governance Gate：

- 不新增 `HUMAN GATE #0`；
- 不生成 Gate Decision；
- 不占用 `current_gate`；
- 不得把用户在 Idea Shaping 中选择的方向写成正式 Product Direction Decision；
- 只有既有 Research Scope、Product Direction、MVP Scope 和条件式 Evidence Waiver 才具有阻止 Workflow 跨越关键决策的治理语义。

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

Interactive Skill 还必须支持：

- 同一 Attempt 在 `RUNNING → WAITING_FOR_USER → RUNNING` 间多轮切换；
- 在每次提问、回答和 Working Hypothesis 更新后持久化版本化 Checkpoint；
- 用户回复后 Resume 同一 Attempt，不增加 Retry Count；
- 不依赖完整聊天上下文恢复当前问题、回答历史、Working Hypothesis 和 Completion Status；
- 使用独立 `current_interaction` 表达交互等待，不复用 `current_gate`；
- 用户等待时间不计入自动 Attempt / Run 超时。

Node Status、Verification Result、Gate Decision、Feasibility Result、Workflow Status 与 Readiness Status 必须是相互独立的类型，不得复用同一个字符串表示不同语义。

---

# 13. Product Profiles

四种 Profile 都属于 v0.2 的规范范围，并复用同一 Core Workflow。Profile 只能调整研究支路、优先级、Source 类型、门槛、图表和研究重点；不得删除 Core Workflow 的 Intake、Contract、Verify、Synthesis、Gate、Opportunity、Feasibility、MVP、PRD 与最终 Verifier，也不得放宽 Idea Shaping 的诚实性和最大轮次约束。

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

v0.2 边界：

- Idea Shaping 最终仍只生成统一的 `idea_definition`，不得创建 `idea_brief`、`product_concept`、`brainstorm_result`、`interview_result` 或 `idea_shaping_result`；
- `idea_definition` 是 Research 前的 Hypothesis Model，可以包含 JTBD、Value、Direction 和 Mechanism Hypothesis，但不能包含 Validated Differentiation、Evidence-backed Positioning、Final Product Boundary 或 Confirmed Product Direction；
- `product_definition` 继续由 Research Synthesis、Opportunity Mapping 和 Product Direction Gate 之后的 Skill 生成，是 Research 后的 Evidence-backed Product Decision；
- Interactive Attempt Checkpoint 是 Runtime 私有工作状态，不是业务 Artifact，不进入 `current_manifest`，也不能被 Research Skill 当作正式输入；
- 达到最大轮次且上下文仍不足时，可以保存带显式 Unknown 和 `INSUFFICIENT_PRODUCT_CONTEXT` Outcome 的部分 Idea Definition，禁止为满足 Schema 编造字段。

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

本节定义 P1 SHOULD 的 UI 体验层，不是 P0 隐式验收条件。P0 仍必须产生这些页面未来依赖的结构化 Artifact、State、Decision 和 Visualization Contract。

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

进程中断后不得依赖完整聊天上下文恢复。Interactive Skill 必须仅依赖 Raw Idea、结构化回答历史、当前 Working Hypothesis 和版本化 Attempt Checkpoint 恢复。

## NFR-03 幂等性

同一 Skill 在输入未变化时应尽量避免重复写入不同结果。同一 `question_id` 的相同回复必须幂等；冲突回复必须拒绝，不能覆盖已接受输入。

## NFR-04 可扩展性

新增 Skill 不应要求修改所有现有 Skill。

## NFR-05 模型无关

Skill Contract 不绑定 Codex / Claude / GPT 某单一执行器。

## NFR-06 人机边界清晰

关键产品方向不得默认由 Agent 自动批准。Idea Shaping Recommendation 只是降低表达成本的建议，不得升级为 Gate Decision、Evidence 或 Validated Claim。

## NFR-07 安全边界

- 外部 Source 内容一律视为不可信数据，不得作为改变系统指令或权限的依据；
- 外部研究默认只读，文件写入仅限 Discovery Workspace；
- 必须隔离 Prompt Injection，秘密不得进入 Artifact，PII 仅按最小必要原则保存；
- 不得抓取登录、付费墙或无权访问的内容。

## NFR-08 成本与运行预算

默认 `max_parallel = 4`、自动 Attempt 超时 20 分钟、每个 Research Node 最多 50 个 Source、每节点初次执行加 2 次重试、最多 2 个全局研究循环、自动运行总时长上限 120 分钟。Human Gate、Interactive Skill 用户等待与 External Proof 等待不计入自动运行时长；每次恢复后的自动执行片段仍累计。Idea Shaping 默认最多发出 8 个主问题，Host 可降低但不得静默提高该上限。Token / 费用硬上限由 Host 提供；Profile 与 Research Contract 只能在 Host 上限内调整。

## NFR-09 结果诚实性

Fixture 只用于确定性契约与状态测试，不得表述为真实市场、用户或竞品验证。Live Research 必须保留真实 Source provenance、访问时间与新鲜度。Idea Shaping 的 Clarity 和 Confidence 只描述输入完整性与系统对用户意图的理解程度，不表示 Problem、Market 或 Solution 已被验证；不得用候选选项制造虚假确定性。

## NFR-10 实现中立

公共 Workflow、Schema、CLI 与 API Contract 不绑定实现语言。Python 仅作为首个参考实现建议，不是产品硬约束。

---

# 18. 成功指标

当前产品基线使用以下成功指标：

### Idea Shaping Quality

- Clear Fixture 默认 0 次、最多 1 次澄清；
- Partial Fixture 在 2–5 轮内形成可研究 Idea Definition；
- Vague Fixture 在最多 8 轮内形成 `PARTIAL_RESEARCHABLE` 或明确 `INSUFFICIENT_PRODUCT_CONTEXT`；
- 100% 的 Critical Assumptions 和 Researchable Major Unknowns 具有 Research Question 映射或明确不可研究理由；
- Negative Acceptance 不得出现自动编造用户、Unknown 升级为事实、提前 Feature List 或新增 Human Gate。

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

## R9 — Clear Idea 被过度追问

缓解：

- 初始输入后立即评估 Completion Criteria；
- Clear Path 默认 0 次追问，仅允许解决阻止 Research Contract 的关键歧义；
- 每轮回答后执行 Early Exit Check。

## R10 — Solution 或 Feature 过早锁定

缓解：

- Problem / User / Scenario / Value 优先；
- Direction 与 Mechanism 只保存为 Hypothesis；
- Problem 未定义前禁止完整 Feature List。

## R11 — Recommendation Bias / Confirmatory Bias

缓解：

- 候选必须实质不同并保留 Other / 自定义；
- Recommendation 必须给出理由，用户可以修改或拒绝；
- 用户无法确认的内容转成 Assumption / Unknown / Research Question；
- Research 负责验证，不负责证明 Agent 的预设方向。

## R12 — Interactive State 丢失或重复消费

缓解：

- Attempt Checkpoint 版本化并 append-only；
- Question ID、Idempotency Key 和 State Version 联合校验；
- Resume 不依赖完整聊天上下文。

## R13 — Idea Definition 与 Product Definition 越界

缓解：

- Idea Definition 字段显式使用 Hypothesis 语义；
- Validated Differentiation、Evidence-backed Positioning、Final Boundary 和 Confirmed Direction 只允许出现在 Research 后流程；
- 增加跨 Artifact 一致性负例。

## R14 — Idea Shaping 无限循环

缓解：

- `max_rounds = 8`；
- 达到上限后只允许 `PARTIAL_RESEARCHABLE` 或 `INSUFFICIENT_PRODUCT_CONTEXT` 收束；
- 不自动通过 Retry 延长同一交互循环。

---

# 20. 当前统一交付范围

本节代替“先实现 v0.1、再实现 v0.2”的阶段解读。当前开发只有一个产品基线：PRD v0.1 中未被覆盖的需求与 PRD v0.2 Amendment 合并后的当前 P0。

## 20.1 P0 MUST — Consolidated Product Baseline

P0 必须一次性交付：

- 从 Raw Idea、`idea-intake`、Research Contract 到 PRD 和 Build Readiness 的唯一 Core Workflow；
- Adaptive Idea Shaping：Clarity Evaluation、`CLEAR | PARTIAL | VAGUE`、动态 Interaction Method、One Question at a Time、Recommendation / Choice / Freeform、Assumption Challenge、Early Exit 与 `max_rounds = 8`；
- Brainstorming / Adaptive Product Discovery Interview 作为 `idea-intake` 内部可重复、可跳过的动态方法，不新增 Node、Subgraph、Gate 或 Artifact；
- 统一 `idea_definition`、`PARTIAL_RESEARCHABLE`、`INSUFFICIENT_PRODUCT_CONTEXT`、Interactive Waiting / Resume / Checkpoint 语义，以及 Assumption / Unknown / Research Seed 到 Research Question 的溯源；
- Workflow、Skill、Artifact、State / Result / Decision / Readiness Contract，以及事件、决策、Attempt 和 Current Manifest 管理；
- 三个标准 Human Gate 与条件式 Evidence Waiver Gate；Interaction Input 不得冒充 Governance Gate；
- 四种 Product Profile、Project Research Contract 和受约束的 Effective Workflow 合成；
- Competitor、User Evidence、Market、OSS / Technical 研究支路，Competitor Research Subgraph、Dataset Normalization、Profile-specific Visualization 和 Score Transparency；
- Source、Evidence、Claim、Verification、Research Gap、定向 Retry、最多两次全局 Research Loop、Synthesis 和 Opportunity Mapping；
- Product Definition、Feasibility Review、外部 Proof Plan / Result、MVP Scope、PRD Generation、PRD Consistency Verifier 和三态 Build Readiness；
- Source Index、Executor、Storage、CLI / API、安全、恢复、幂等、预算和结果诚实性边界；
- 确定性 Fixture、Clear / Partial / Vague / Negative Acceptance 和一条 Live Developer Tool Acceptance 设计。

P0 不允许把上述内容拆成“v0.1 实现”与“v0.2 重新实现”两条开发链。

## 20.2 P1 SHOULD

- 完整 UI 体验层：Discovery Graph、Artifact Inspector、Competitor Analysis Dashboard、Decision Gate 和 Build Readiness 页面；
- Better Chart Renderer；
- Incremental Research。

P1 项不得成为 P0 的隐式验收条件，也不得在 P0 期间通过“顺手实现”扩大范围。

## 20.3 Future / Not Implemented

- Vendor-specific 或 Distributed / Cloud Executor Adapters；
- Team Collaboration 与 Multi-user Approval；
- Organization Templates；
- Workflow Library；
- Versioned Decisions；
- Discovery Benchmark / Evaluation Suite；
- Managed Hosting、SaaS 多租户、企业级权限和通用 Marketplace。

## 20.4 Delivery Truth

本 PRD 已冻结产品需求，但不声称 Schema、Skill、Fixture、Test 或 Runtime 已实现。在最终 SPEC 冻结且 PRD ↔ SPEC Traceability Gate 通过前，必须停止代码实现。

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

## 21.2 Adaptive Idea Shaping Acceptance

必须增加三类 Idea Shaping Fixture：

| Path | Example | Expected |
|---|---|---|
| Clear | 明确 Problem、User、Scenario、Value 与 Mechanism 的 Coding Agent Observability Tool | 默认 0 次，阻塞性歧义时最多 1 次澄清 |
| Partial | “我想做一个帮助大学生找工作的 AI” | 2–5 轮后形成可研究 Idea Definition |
| Vague | “我想做一个 Agent 产品” | 提供 framing、推荐与自由输入；最多 8 轮后收敛或安全停止 |

正向验收还必须覆盖：

- Resume 只依赖持久化 Attempt Checkpoint，不依赖完整聊天上下文；
- Early Exit 在达到 Completion Criteria 后立即生效；
- Critical Assumptions 和 Researchable Unknowns 可以追溯到 Research Questions；
- Interaction 等待时 `current_gate` 为空，且不生成 Gate Decision；
- Brainstorming / Adaptive Product Discovery Interview 可以根据信息缺口被重复、跳过或提前停止，不依赖固定方法序列；
- 所有内部 Interaction Method 共用同一 Idea Shaping 阶段状态，最终只生成统一 `idea_definition`。

Negative Acceptance：

1. Clear Idea 被连续追问 8 次，应 Fail；
2. 用户不知道 Target User，系统自动编造，应 Fail；
3. Problem 未定义便生成完整 Feature List，应 Fail；
4. Unknown 被写成 Validated Fact，应 Fail；
5. 超过 `max_rounds` 继续提问，应 Fail；
6. Interactive Skill 被实现为新增 Human Gate，应 Fail；
7. Resume 必须依赖完整聊天上下文，应 Fail；
8. 相同 `question_id` 接受两个冲突回复，应 Fail；
9. `PARTIAL_RESEARCHABLE` 无法派生 Research Question，应 Fail；
10. Idea Definition 提前写入 Validated Differentiation 或 Confirmed Product Direction，应 Fail；
11. Brainstorming / Adaptive Product Discovery Interview 被实现为固定顶层 Workflow Step，应 Fail；
12. 内部 Interaction Method 创建 `brainstorm_result` 或 `interview_result` 业务 Artifact，应 Fail；
13. Completion Criteria 已满足仍为了执行完预设 Interview 步骤继续提问，应 Fail。

## 21.3 Live Developer Tool Acceptance

保留以下 Idea 作为 v0.2 Live Research 验收链路：

> “我想做一个读取项目目录并自动展示 Codex / Claude Code 当前执行进度的工具。”

这是 Product Discovery SkillGraph 要分析的输入 Idea，不表示本系统自身接管 Codex / Claude Code Runtime。

系统必须：

1. 先评估 Idea Clarity；若达到最低信息要求则走 Fast Path，生成 Idea Definition 与带 Profile 默认值的 Research Contract；
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

> “让 Agent 替用户脑补一个完整产品，或把模糊 Idea 直接变成 Feature List。”

系统追求：

> “先帮助开发者把模糊 Idea 澄清到足以被研究，再把进入开发前必须经历的研究、证据、验证和决策过程编码成可重复执行的 Graph。”

核心逻辑是：

```text
Think clearly
→ Research objectively
→ Collect Evidence
→ Make Decisions
→ Validate Feasibility
→ Freeze MVP
→ Generate PRD
```

Idea Shaping 不替代 Research，Research 不替代 Product Direction Gate，Idea Definition 不替代 Product Definition。Brainstorming 与 Adaptive Product Discovery Interview 只是 Idea Shaping 内部的动态交互方法，不改变这些边界。这是 Product Discovery SkillGraph v0.2 的核心产品边界。
