# Product Discovery SkillGraph

Product Discovery SkillGraph 将 `Idea → Research → Evidence → Decision → Feasibility → MVP → PRD` 定义为可编排、可验证、可追溯的产品发现流程。

## 当前状态

- 当前设计基线：冻结的 PRD / SPEC v0.2；四份 PRD/SPEC 冻结文件由 Registry 中的 SHA-256 精确保护。
- 不可变历史基线：根目录 `workflow.yaml`、`profiles/`、`schemas/`、`skills/`、`subgraphs/`、`templates/`、`fixtures/contracts/` 继续表示 `0.1.0`，只允许审计，不允许新建或恢复 Run。
- 当前静态 Bundle：`contracts/0.2.0/`，包含 23 个 JSON Schema、23 个 Skill Contract、4 个 Profile、1 个 Subgraph、5 个 Template、25 个正例、20 个 Schema/语义负例和 7 个 Legacy Compatibility 场景。
- Version Registry：`contracts/registry.yaml` 默认且只允许以 `0.2.0` 新建或恢复；Legacy Compatibility Matrix 默认拒绝，仅显式允许 Source/Evidence/Claim 作为只读 Research Seed，并要求来源 Schema、哈希及重新验证条件同时成立。
- 验证边界：`scripts/validate_contracts.py` 分别验证 Registry、根目录 v0.1 不可变审计和 v0.2 完整闭包，不在两个 Bundle 之间搜索缺失文件。
- 阶段状态：P0-01 已于 2026-08-11 完成自动验证并通过用户 A2 行为确认；下一阶段为尚未开始的 P0-02 Runtime Foundation。
- 尚未实现：可执行 Skill、Orchestrator、Runtime CLI/API、真实 Research、Template Renderer、Human Gate/Interaction Handler 和端到端 P0 Workflow。

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
```

如果系统 `python` 启动器指向错误或已删除的解释器，请先解析真实解释器路径，再用该绝对路径运行 `-m venv .venv`。项目验证命令始终使用 `.venv` 中的解释器，避免混用全局 Site Packages。

静态验证器成功返回 `0`，契约或 Schema 错误返回 `2`，未分类内部错误返回 `10`。

历史证据：P0 Step 1 为 `[OK] checked=46 errors=0`、`35 passed`；P0-00 为 `[OK] checked=111 errors=0`、`100 passed`。P0-01 的静态验证器检查数为 246（Registry/Integrity 3、v0.1 111、v0.2 132）；最终 pytest 与依赖证据记录在 `progress.md`。

## 文档

- `PRD_v0.2.md`：当前冻结产品需求基线；`PRD_v0.1.md` 保留历史基线。
- `SPEC_v0.2.md`：当前冻结系统与 Workflow 规范；`SPEC_v0.1.md` 保留历史基线。
- `REQUIREMENTS.md`：当前阶段范围和验收标准。
- `IMPLEMENTATION_PLAN.md`：阶段一实施与回滚方案。
- `progress.md`：原子任务与验证证据。
- 根目录契约树只声明 v0.1；`contracts/0.2.0/` 只声明 v0.2 静态契约。两者都不代表对应执行器或业务流程已经实现。
