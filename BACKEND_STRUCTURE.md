# Backend Structure

## Module Boundaries

- 根目录 `workflow.yaml`、`profiles/`、`schemas/`、`skills/`、`subgraphs/`、`templates/`、`fixtures/contracts/`：不可变 `0.1.0` 审计 Bundle。
- `contracts/registry.schema.json` / `contracts/registry.yaml`：版本登记、操作能力、Bundle Root、默认拒绝 Legacy Compatibility Matrix 与完整性保护声明。
- `contracts/0.1.0-baseline.sha256.json`：根目录 v0.1 Contract Tree 的精确路径/内容哈希清单。
- `contracts/0.2.0/`：完整并行的当前 Bundle，内部拥有自己的 Workflow、四 Profile、23 Schema、23 Skill、1 Subgraph、5 Template 和 Fixture Manifest。
- `scripts/contract_bundles.py`：Fail Closed Registry Loader、Bundle Resolver、Context Loader、Bundle-local Ref Resolver、Legacy Ref Evaluator 与公开 Bundle Validation Adapter。
- `scripts/validate_contracts.py`：参数化静态结构/语义验证入口；保留 v0.1 helper 默认参数。
- `tests/`：Schema 和语义测试。

本阶段不包含 Orchestrator、Runtime、Skill Executor、Template Renderer 或业务 Artifact 生成模块。

## Data Flow

```text
Registry + requested operation/version
                    ↓
      one repository-root-relative Bundle Context
                    ↓
 safe YAML/JSON loader + Bundle-local Schema Registry
                    ↓
 JSON Schema + reference closure + semantic/legacy lint
                    ↓
 deterministic version-scoped diagnostics / exit code
```

## Error Handling

- 收集全部可定位错误，不在第一个失败处退出。
- 诊断包含文件、实例路径、规则和消息。
- 跨文件检查区分缺失实体、ID/版本漂移、悬空/混版引用、路径越界、DAG 环、Interaction 条件、Origin 映射、Legacy 决策和唯一 Writer 冲突。
- 可预期验证错误返回 `2`，内部异常返回 `10`。

## Security Notes

- YAML 使用 SafeLoader 并拒绝重复键；YAML/JSON 文档受大小限制。
- Bundle Root、Skill、Subgraph、Template、Executor、Fixture 与 `$ref` 路径拒绝绝对路径、URI、盘符、反斜杠、`..`、符号链接和越界解析。
- Schema Registry 只加载所选 Bundle 的 `schemas/`，不远程获取 `$ref`，也不从根目录或另一 Bundle 补齐缺失文件。
- Skill 的输出路径必须同时出现在其 `writes` 与 `output_contracts` 中，Schema / Template 引用只能解析到当前 Bundle。
- Legacy Ref 先核对来源 Bundle containment、精确 SHA-256 与来源 Schema，再匹配 default-deny Compatibility Rule；Current Manifest 明确拒绝 Legacy/Interaction 字段。

## Observability

验证器输出版本作用域、已检查项数和确定性错误列表。P0-01 仓库检查数为 246：Registry/Integrity 3、v0.1 111、v0.2 132。本阶段没有 Runtime Log、事件流或指标系统。
