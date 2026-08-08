# Requirements

## Goal

完成 SPEC v0.1 第 53 节 Step 1：交付机器可读、可静态验证且无悬空引用的 Workflow、Profile 与核心数据契约。

## Scope In

- 完整 `workflow.yaml` 和四种 Product Profile。
- JSON Schema Draft 2020-12 核心契约与直接依赖闭包。
- 安全 YAML 解析、Schema 验证和 Workflow/Profile 语义检查。
- 正反例 Fixture、pytest 测试、阶段状态和经验沉淀。
- 对 SPEC 中影响实现正确性的最小勘误。

## Scope Out

- Orchestrator、调度器、状态迁移执行器、重试和恢复实现。
- 规范性 Runtime CLI/API、真实 Research、Gate 交互、External Proof 执行。
- Idea、Competitor、Research、Chart 等后续业务 Artifact Schema。
- UI、数据库、队列、部署、Git 初始化和厂商专用 LLM Adapter。

## Acceptance Criteria

- 所有 Schema 通过 Draft 2020-12 Meta-Schema 检查且无悬空 `$ref`。
- Core Workflow 和四个 Profile 通过结构与语义验证。
- 正例全部通过，负例在预期规则上失败。
- 路径逃逸、非法 Gate Action、枚举混用、DAG 环和无效条件被拒绝。
- `python scripts/validate_contracts.py` 与 `python -m pytest -q` 均返回 `0`。
- 文档不得宣称 Runtime 或端到端 P0 已完成。

## Constraints

- 公共字段使用 `snake_case`，契约版本为 `0.1.0`。
- Schema 使用仓库内相对 `$ref`。
- YAML 只能使用安全加载器。
- 核心对象默认拒绝未知字段，仅显式扩展区允许自由键。
- 当前目录不是 Git 仓库，不执行提交、合并或发布。

## Risks

- SPEC 示例存在少量遗漏或口径不精确，需要最小勘误后才能形成可执行契约。
- JSON Schema 无法表达全部跨节点语义，需要确定性 Python Lint 补充。
- 依赖尚未安装，首次验证可能受网络或 Python 3.14 环境兼容性影响。

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
