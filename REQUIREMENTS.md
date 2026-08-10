# Requirements

## Goal

在不修改根目录 `0.1.0` 契约树和四份冻结 PRD/SPEC 的前提下，完成 P0-01 Version Registry 与完整静态 `0.2.0` Contract Bundle，使新 Run、恢复、审计、Bundle 内引用和只读 Legacy Seed 都有确定性、默认拒绝的版本边界。

## Scope In

- 新增 `contracts/registry.schema.json`、`contracts/registry.yaml` 与仓库根相对的静态 Bundle Resolver。
- 保留根目录 `0.1.0` 为不可变、仅审计 Bundle；新增完整、并行的 `contracts/0.2.0/` Bundle。
- v0.2 Bundle 固定包含 23 Schema、23 Skill、4 Profile、1 Subgraph、5 Template 与 Bundle-local Fixture Manifest。
- v0.2 Wire Contract 覆盖 Interaction/Gate 分离、同 Attempt 恢复、条件式 Executor Result、Current Manifest 纯当前版本和 Research Question Origin Traceability。
- Compatibility Matrix 默认拒绝；只允许登记的 v0.1 Source/Evidence/Claim 以只读 Research Seed 进入重新验证流程，禁止成为 Current Manifest 或 Workflow-driving Artifact。
- 静态验证器按 Bundle Context 分别验证 v0.1 和 v0.2，同时保留现有 v0.1 helper 的默认调用方式。
- 为路径逃逸、远程/混版引用、v0.1 Resume、Interaction 条件、Idea 边界、Origin 悬空和 Legacy 复用提供确定性负例。

## Scope Out

- Orchestrator、状态持久化、事件日志、调度、重试、恢复执行链和 Runtime Adapter。
- 规范性 Runtime CLI/API Handler、真实 Research、真实 Human Gate/Interaction 处理和 External Proof 执行。
- Template Renderer、业务 Artifact 生产、Legacy Import/转换、五业务完整 E2E Workflow。
- UI、数据库、队列、部署、提交、合并、推送、发布和数据迁移。

## Acceptance Criteria

- Registry 默认且只允许 `0.2.0` 新建/恢复；`0.1.0` 只能审计，未知版本与省略 Resume 版本均 Fail Closed。
- Bundle Root、`$ref`、Schema/Template/Fixture 路径和 `@version` 引用不得绝对、远程、反斜杠、越界、符号链接、父目录回退或跨 Bundle。
- v0.2 Inventory 精确为 23 Schema、23 Skill、4 Profile、1 Subgraph、5 Template；25 正例、20 Schema/语义负例和 7 Legacy 场景结果确定。
- Idea、Research、Interaction、Executor、Manifest、Workflow/Profile/Skill/Subgraph/Template 的结构与跨文件语义全部通过。
- v0.1 Contract Tree 112 个文件与四份冻结文档 SHA-256 精确不变。
- `scripts/validate_contracts.py`、全量 pytest 与 `pip check` 返回 `0`；安全扫描只允许经审计的刻意负例命中。
- 文档只声明静态契约和验证能力，不宣称 Runtime、真实 Research、Legacy 转换或 E2E P0 已实现。

## Constraints

- 公共字段使用 `snake_case`；同一 Bundle 内版本必须严格一致。
- Schema 只使用所选 Bundle 内的相对 `$ref`；YAML/JSON 拒绝重复键并限制文档大小。
- 核心对象默认拒绝未知字段，仅显式扩展区允许自由键。
- `skill.yaml` 的 `writes` 与 `output_contracts` 必须精确一致，Schema/Template 只解析到当前 Bundle。
- 保留进入 P0-01 前的脏工作树，不整理 Git，不覆盖用户基线，不新增依赖或联网。
- `PRD_v0.1.md`、`PRD_v0.2.md`、`SPEC_v0.1.md`、`SPEC_v0.2.md` 保持字节不变。

## Risks

- 单一 Schema Tree 同时兼容 0.1/0.2 会产生条件分支与静默混版风险，因此采用并行完整 Bundle。
- JSON Schema 无法表达 Method 一致性、Origin 实体存在、DAG、唯一 Writer 和 Legacy Matrix 等联合语义，必须由确定性 Python Lint 补充。
- Legacy Source Schema 合法并不表示可成为当前 Artifact；仍必须核对内容哈希、显式 Rule、只读属性和重新验证要求。
- Fixture 负例若同时违反多条规则会导致诊断不稳定，因此每个新增负例尽量只破坏一个目标约束。

## A1 Decision

- 状态：approved。
- 选择：Step 1 契约闭环 + Python 参考验证栈。
- 明确排除：Step 2–7 Runtime 与 Research 实现。

## A2 Decision

- 状态：approved。
- 确认时间：2026-08-08。
- 确认内容：自动验证已通过，阶段一行为与验收标准一致。
- 后续闸门：A3 已于 2026-08-09 完成最终交付确认。

## A3 Decision

- 状态：approved。
- 确认时间：2026-08-09。
- 确认内容：阶段一交付范围、验证证据、已知边界与后续风险已接受，允许正式关闭本轮迭代。
- 外部动作：无 Git 提交、合并、部署或发布；本次 A3 仅完成本地交付确认。

## P0-00 Decision

- 状态：approved / completed。
- 确认时间：2026-08-10。
- 选择：补齐 v0.1 静态契约目录和引用闭包，并在完整验证后关闭 P0-00。
- 明确排除：Runtime、可执行 Skill、真实 Research、业务 Artifact 生成和任何 v0.2 实施。
- 验证证据：`[OK] checked=111 errors=0`、`100 passed`、`pip check` 无破损依赖；三个 v0.2 文档哈希保持不变。

## P0-01 Decision

- 状态：approved / completed。
- 实现时间：2026-08-11。
- A2 确认时间：2026-08-11。
- 选择：并行完整 v0.2 Bundle + 参数化验证器；根目录 v0.1 保持不可变、仅审计；Legacy Matrix 内嵌 Registry 且 default deny。
- 明确排除：Orchestrator、Runtime CLI/API Handler、真实 Research、Legacy Import/转换、完整业务 E2E、提交、合并、推送与发布。
- 验证证据：`[OK] checked=246 errors=0`、`140 passed`、`pip check` 无破损依赖；112 个 v0.1 Contract 文件和四份冻结 PRD/SPEC 哈希精确不变。
- A2 确认内容：新建/恢复只允许完整 `0.2.0`、v0.1 仅审计、Legacy Default-Deny 且只读、P0-01 不包含 Runtime 的行为边界符合预期。
- 后续阶段：P0-02 Orchestrator and Runtime Foundation；开始前仍需独立 A1 范围/架构确认。本次授权不包含 A3、Git 或发布动作。
