# API Contract

## Endpoints

N/A — P0-01 不实现可执行 Runtime API、CLI 或 Handler。未来规范性操作以冻结的 `SPEC_v0.2.md` 为准；本文件只记录后续 Runtime 可复用的静态解析接口。

静态 Python 接口：

- `resolve_contract_bundle(version=None, operation="new_run")`：新建默认解析为 `0.2.0`；v0.1 新建/恢复与未知版本返回 `SCHEMA_VERSION_UNSUPPORTED`。
- `load_bundle_context(bundle)`：一次性绑定 Workflow、Schema、Profile、Skill、Subgraph、Template 与 Fixture Manifest 路径。
- `validate_bundle(bundle, registry=...)`：只在所选 Bundle 内执行静态闭包验证。
- `evaluate_legacy_input_ref(ref, target_version)`：只有来源版本、来源 Schema、内容哈希和显式 Compatibility Rule 全部通过时才返回只读 Seed 决策。

## Request Schema

`contracts/0.2.0/schemas/executor-request.schema.json` 定义首次执行与同 Attempt `interaction_resume` 的静态 Wire Shape；不实现请求处理器。

## Response Schema

`contracts/0.2.0/schemas/executor-result.schema.json` 定义 `COMPLETED | WAITING_FOR_USER | FAILED` 条件分型；等待结果必须包含 Interaction Request/Checkpoint，且不得伪装最终 Artifact 或 Error。当前不实现响应服务。

## Error Cases

静态验证脚本退出码：`0` 成功，`2` 契约或 Schema 错误，`10` 未分类内部错误。

Resolver 的可预期版本/路径错误使用稳定 `code` 与 `rule`，包括 `SCHEMA_VERSION_UNSUPPORTED`、`INPUT_INVALID`、`mixed_bundle_version`、`missing_contract_asset` 和 `unsafe_path`。这些是静态库错误，不是已实现的 Runtime HTTP/CLI 错误响应。

## Backward Compatibility Notes

- 公共字段保持 `snake_case`。
- 根目录 `0.1.0` 只允许审计；新建和恢复只允许完整 `0.2.0` Bundle，不做隐式迁移或根目录回退。
- Legacy Compatibility 默认拒绝；登记的 v0.1 Source/Evidence/Claim 只能作为只读 Research Seed，不得进入 Current Manifest 或驱动 Workflow State。
- 后续 Runtime 必须兼容 SPEC v0.2 第 49–50 节，不得把静态验证脚本当作规范性 Runtime CLI。
