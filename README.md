# Product Discovery SkillGraph

Product Discovery SkillGraph 将 `Idea → Research → Evidence → Decision → Feasibility → MVP → PRD` 定义为可编排、可验证、可追溯的产品发现流程。

## 当前状态

- 当前设计基线：冻结的 PRD / SPEC v0.2；四份 PRD/SPEC 冻结文件由 Registry 中的 SHA-256 精确保护。
- 不可变历史基线：根目录 `workflow.yaml`、`profiles/`、`schemas/`、`skills/`、`subgraphs/`、`templates/`、`fixtures/contracts/` 继续表示 `0.1.0`，只允许审计，不允许新建或恢复 Run。
- 当前静态 Bundle：`contracts/0.2.0/`，包含 23 个 JSON Schema、23 个 Skill Contract、4 个 Profile、1 个 Subgraph、5 个 Template、25 个正例、20 个 Schema/语义负例和 7 个 Legacy Compatibility 场景。
- Version Registry：`contracts/registry.yaml` 默认且只允许以 `0.2.0` 新建或恢复；Legacy Compatibility Matrix 默认拒绝，仅显式允许 Source/Evidence/Claim 作为只读 Research Seed，并要求来源 Schema、哈希及重新验证条件同时成立。
- 验证边界：`scripts/validate_contracts.py` 分别验证 Registry、根目录 v0.1 不可变审计和 v0.2 完整闭包，不在两个 Bundle 之间搜索缺失文件。
- 阶段状态：P0-05-T1/T2 的私有 Provenance 基础，以及 P0-04-T1～T9 已完成；P0-04-T10～T13 需单独批准的契约演进，当前明确延期。
- Runtime Core：`src/skillgraph_runtime/` 提供不可变 Run Snapshot、Registry-backed Run Creation、确定性 DAG/Condition/Subgraph/fan-out/fan-in 调度、全局并发配额、Attempt Planning/Input Fingerprint、Executor Wire 提案校验，以及可选显式 `storage_root` 下的单 Writer 持久化 Runtime。
- T7～T12：持久化入口创建/加载/调度 Run，Interaction 同 Attempt Resume，Gate/External 分型等待，完整 Error Taxonomy 的本地动作、累计 Usage/Budget、append-only Artifact/Checkpoint/Snapshot、原子 Current Manifest 和故障恢复报告均已实现。Recovery 只报告 Current Manifest 未选中的文件，不删除它们，也不将其视为 GC 资格；Retention/GC 将作为独立后续能力。未提供 `storage_root` 时原有 API 维持纯内存、持久化请求明确失败为 `storage_root_required`。
- T13～T21：Runtime Storage 现在追加 Event/Decision/Idempotency Log，并以 Manifest `last_event_offset` 绑定已提交状态；进程内 `RuntimeOperations` 与 JSON CLI 使用统一 Envelope、幂等与状态版本控制；支持精确下游失效、Fixture/Manual/Host Agent Adapter。`submit_artifact_patch`、`get_source`、`export_prd` 仍属于后续业务阶段，明确拒绝而不伪造成功。
- P0-03：`AdaptiveIdeaShapingService` 在同一 Idea Attempt 内执行确定性的 Clarity、Completion-first、Gap/Method 与八轮收束策略；受限 Host LLM Provider 只提出语义候选。Runtime 写入版本化 Checkpoint、唯一 `idea_definition`、带 `origin_refs` 的 `research_contract`，并在 Research Scope Gate 批准前阻断 Research。它不执行自治 Agent、自动 Research 或网络工具调用。
- P0-05-T1/T2 + P0-04-T1～T9：Kernel 使用 URL/fallback identity 的 Source Index 和私有 Source→Evidence→Claim Provenance sidecar；`CompetitorResearchService` 完成 Candidate、Ranking、Deep Dive、Dataset 和四类确定性 Analysis。所有外部事实仍只来自受限 Callback/Fixture Provider，Dataset/Analysis 不访问网络，Deep Dive/Analysis 调度继续受全局配额、路径与 Producer 校验约束。
- 尚未实现：P0-04-T10～T13（透明评分、Visualization、Verifier、Retry/Return 与完整集成）、Template Renderer、Product Diff/PRD 导出与端到端 P0 Workflow；不提供 HTTP、数据库、队列、多 Writer 或 Vendor-specific Adapter。

## 环境

- Python 3.11+（当前验证环境为 Python 3.14）。
- 依赖见 `requirements-dev.txt`。

## 验证

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe scripts\validate_contracts.py
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m pip check
.\.venv\Scripts\python.exe -m pip wheel . --no-deps --wheel-dir .pytest_cache\wheels
```

如果系统 `python` 启动器指向错误或已删除的解释器，请先解析真实解释器路径，再用该绝对路径运行 `-m venv .venv`。项目验证命令始终使用 `.venv` 中的解释器，避免混用全局 Site Packages。

静态验证器成功返回 `0`，契约或 Schema 错误返回 `2`，未分类内部错误返回 `10`。

历史证据：P0 Step 1 为 `[OK] checked=46 errors=0`、`35 passed`；P0-00 为 `[OK] checked=111 errors=0`、`100 passed`。P0-01 的静态验证器检查数为 246（Registry/Integrity 3、v0.1 111、v0.2 132）。P0-02-T1～T21 完成时再次通过 `[OK] checked=246 errors=0`、分文件执行的 pytest `200 passed`（Runtime 60、其余 140）、`pip check` clean 与无依赖 wheel 构建；P0-03 追加定向 `19 passed`（13 项负例与 Idea→Contract→Gate E2E），全量回归 `220 passed`。详细范围记录在 `progress.md`。

## 文档

- `PRD_v0.2.md`：当前冻结产品需求基线；`PRD_v0.1.md` 保留历史基线。
- `SPEC_v0.2.md`：当前冻结系统与 Workflow 规范；`SPEC_v0.1.md` 保留历史基线。
- `REQUIREMENTS.md`：当前阶段范围和验收标准。
- `IMPLEMENTATION_PLAN.md`：阶段一实施与回滚方案。
- `progress.md`：原子任务与验证证据。
- 根目录契约树只声明 v0.1；`contracts/0.2.0/` 只声明 v0.2 静态契约。两者都不代表对应执行器或业务流程已经实现。
