# Backend Structure

## Module Boundaries

- `workflow.yaml`：Core Workflow 配置。
- `profiles/`：四种规范 Product Profile。
- `schemas/`：Draft 2020-12 数据契约。
- `scripts/validate_contracts.py`：静态结构与语义验证入口。
- `fixtures/contracts/`：正反例契约数据。
- `tests/`：Schema 和语义测试。

本阶段不包含 Orchestrator 或 Runtime 模块。

## Data Flow

```text
schema files + workflow/profile/fixture instances
                    ↓
          safe YAML / JSON loader
                    ↓
       JSON Schema + semantic lint
                    ↓
       deterministic diagnostics / exit code
```

## Error Handling

- 收集全部可定位错误，不在第一个失败处退出。
- 诊断包含文件、实例路径、规则和消息。
- 可预期验证错误返回 `2`，内部异常返回 `10`。

## Security Notes

- YAML 只使用 `safe_load`。
- Skill / Executor 写路径拒绝绝对路径、盘符路径和 `..`。
- Schema Registry 只加载仓库内 `schemas/`，不远程获取 `$ref`。

## Observability

验证器输出已检查文件数和错误列表；本阶段没有 Runtime Log 或指标系统。

