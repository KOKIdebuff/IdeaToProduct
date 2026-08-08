# API Contract

## Endpoints

N/A — P0 Step 1 不实现可执行 Runtime API 或 CLI。未来规范性操作见 `SPEC_v0.1.md` 第 49–50 节。

## Request Schema

本阶段只实现 `executor-request.schema.json` 等静态数据契约，不实现请求处理器。

## Response Schema

本阶段只实现 `executor-result.schema.json` 和相关静态数据契约，不实现响应服务。

## Error Cases

静态验证脚本退出码：`0` 成功，`2` 契约或 Schema 错误，`10` 未分类内部错误。

## Backward Compatibility Notes

- 公共字段保持 `snake_case`。
- 业务 Schema Version 固定为 `0.1.0`。
- 后续 Runtime 必须兼容 SPEC 第 49–50 节，不得把静态验证脚本当作规范性 CLI。

