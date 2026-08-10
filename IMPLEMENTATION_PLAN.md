# Implementation Plan

## Milestones

1. 建立 SSoT 与任务追踪。
2. 同步 SPEC 勘误，落地 Workflow、Profile 和 Schema。
3. 实现静态验证器与 Fixture。
4. 完成 pytest 验证并同步交付文档。

以上里程碑已作为 P0 Step 1 于 2026-08-09 关闭。P0-00 随后补齐 v0.1 静态业务契约；P0-01 在不启动 Runtime 的前提下新增 Version Registry、不可变 v0.1 审计与完整并行 v0.2 Bundle。

## Task Breakdown

| task_id | expected_result | validation | acceptance |
|---|---|---|---|
| T1 | SSoT 文档和任务状态建立 | 文档存在性检查 | 范围、非目标、命令和 A1 决策一致 |
| T2 | SPEC 勘误、Workflow、四 Profile 落地 | YAML 安全解析 | 配置可解析且与 v0.1 口径一致 |
| T3 | 核心 Schema 与依赖闭包落地 | Meta-Schema + `$ref` 检查 | 无悬空引用，公共枚举分型 |
| T4 | 验证器和正反例 Fixture 落地 | 验证器自检 | 结构与语义错误可确定性定位 |
| T5 | 自动测试闭环 | `python -m pytest -q` | 正例通过、负例按预期失败 |
| T6 | 状态、经验与交付口径同步 | 文档一致性检查 | 不夸大 Runtime 完成状态 |

### P0-00 Task Breakdown

| task_id | expected_result | validation | acceptance |
|---|---|---|---|
| P0-00-T1 | v0.1 契约闭包范围与 SSoT 锁定 | 文档、Git 状态与受保护文件哈希审计 | 历史 T1–T6 保留；Runtime 与 v0.2 明确排除 |
| P0-00-T2 | 业务 Artifact Schema 与最小 `$ref` 闭包落地 | Draft 2020-12 Meta-Schema + 本地引用解析 | 无悬空、远程或越界 `$ref`，Artifact Header 未被放宽 |
| P0-00-T3 | Competitor Subgraph 与五个 Markdown Template 落地 | Subgraph Schema、DAG 和 Template front matter 检查 | 内部 `competitor-verifier` 与输出类型可解析，Verification 输出契约锁定 Retry/Return，模板身份合法 |
| P0-00-T4 | 23 个 Standard Skill Contract 目录落地 | Skill Schema、Markdown section 和双向引用检查 | 每目录有 `SKILL.md`/`skill.yaml`，ID=目录名，版本为 `0.1.0` |
| P0-00-T5 | 验证器和新增正反例闭环 | 定向 pytest + 原有 Fixture 回归 | Core Node、Subgraph、Skill、Schema、Template、路径与唯一 Writer 规则确定性通过/失败 |
| P0-00-T6 | 全量复验与交付口径同步 | validator、pytest、pip check、Git/hash 边界审计 | 全部命令返回 `0`，三个 v0.2 文档未变，不夸大实现状态 |

### P0-01 Task Breakdown

| task_id | expected_result | validation | acceptance |
|---|---|---|---|
| P0-01-T1 | Version Registry 与内嵌 Compatibility Matrix | Registry Schema/instance tests | 新建默认且只允许 `0.2.0`；Legacy 默认拒绝 |
| P0-01-T2 | 静态 Bundle Resolver/Context | 路径与操作分型 tests | Repository-root-relative、无远程/越界/回退/混版 |
| P0-01-T3 | 完整 v0.2 Bundle 与 v0.1 哈希清单 | Inventory + SHA-256 audit | 23/23/4/1/5 精确库存；112 个 v0.1 文件不变 |
| P0-01-T4 | 基础 Artifact/Source/Evidence/Claim/Decision Schema | Meta-Schema + local `$ref` tests | 严格 v0.2 Artifact Header 与内容哈希 |
| P0-01-T5 | State/Executor/Manifest/Verification/Gate/Readiness | Wire 正反契约 tests | Interaction/Gate 互斥、同 Attempt Resume、条件结果分型 |
| P0-01-T6 | Idea/Research/Competitor/Chart/Proof Schema | 业务 Schema 与 Origin tests | 0..8 轮、假设未验证边界、Question Origin 可解析 |
| P0-01-T7 | Core Workflow 与四 Profile | DAG/Extension/Writer tests | 22 Core Node、Profile 扩展不替换核心或放宽 Idea |
| P0-01-T8 | 23 Skill 与 idea-intake Interaction Model | YAML/Markdown 同步 tests | writes/output 精确；四 Method、Freeform、Early Exit、8 轮 |
| P0-01-T9 | Competitor Subgraph 与五 Template | Producer/Verifier/front matter tests | 唯一终点 Verifier、输出闭包、Template 仅表达层 |
| P0-01-T10 | Bundle-local 完整 Fixture Manifest | 参数化 fixture validation | 25 个正例覆盖全部实例型静态契约 |
| P0-01-T11 | Fail Closed 与 Legacy 正反例 | 精确失败规则和无变异 tests | 20 个 Schema/语义负例、7 个 Legacy 场景 deterministic |
| P0-01-T12 | 双 Bundle 仓库验证与 SSoT 闭环 | validator + full pytest + pip/hash/security gates | v0.1/v0.2 独立验证且冻结资产不变 |

## Validation Plan

```powershell
.\.venv\Scripts\python.exe scripts\validate_contracts.py
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m pip check
```

## Rollback Plan

- P0-00 主要为新增文件，可按明确文件清单逐项移除；不得使用会清理既有未跟踪 v0.2 文档的批量命令。
- SPEC 只做 `output_contracts`、Subgraph、`competitor-verifier` 和 Template front matter 的局部勘误，可逐项反向恢复。
- 进入 P0-00 前已有的 `progress.md`、验证器和工作流语义测试改动必须保留，不得整体回滚。
- P0-01 以 `contracts/0.2.0/`、Registry、Resolver 和增量验证器改动为边界，可按任务文件清单逆序回滚；根目录 v0.1 Contract Tree 和四份冻结 PRD/SPEC 不参与回滚写入。
- 回滚 Registry 或当前 Bundle 时必须同步恢复验证入口，不能留下默认版本指向不存在 Bundle 的半状态。
- 不执行数据迁移、Git 操作、部署或不可逆外部写入。
