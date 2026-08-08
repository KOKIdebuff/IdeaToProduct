# Implementation Plan

## Milestones

1. 建立 SSoT 与任务追踪。
2. 同步 SPEC 勘误，落地 Workflow、Profile 和 Schema。
3. 实现静态验证器与 Fixture。
4. 完成 pytest 验证并同步交付文档。

## Task Breakdown

| task_id | expected_result | validation | acceptance |
|---|---|---|---|
| T1 | SSoT 文档和任务状态建立 | 文档存在性检查 | 范围、非目标、命令和 A1 决策一致 |
| T2 | SPEC 勘误、Workflow、四 Profile 落地 | YAML 安全解析 | 配置可解析且与 v0.1 口径一致 |
| T3 | 核心 Schema 与依赖闭包落地 | Meta-Schema + `$ref` 检查 | 无悬空引用，公共枚举分型 |
| T4 | 验证器和正反例 Fixture 落地 | 验证器自检 | 结构与语义错误可确定性定位 |
| T5 | 自动测试闭环 | `python -m pytest -q` | 正例通过、负例按预期失败 |
| T6 | 状态、经验与交付口径同步 | 文档一致性检查 | 不夸大 Runtime 完成状态 |

## Validation Plan

```powershell
.\.venv\Scripts\python.exe scripts\validate_contracts.py
.\.venv\Scripts\python.exe -m pytest -q
```

## Rollback Plan

- 本阶段主要为新增文件，可按目录和文件清单删除。
- SPEC 只做少量已记录的局部勘误，可逐项反向恢复。
- 不执行数据迁移、Git 操作、部署或不可逆外部写入。
