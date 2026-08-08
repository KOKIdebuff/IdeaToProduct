# Product Discovery SkillGraph

Product Discovery SkillGraph 将 `Idea → Research → Evidence → Decision → Feasibility → MVP → PRD` 定义为可编排、可验证、可追溯的产品发现流程。

## 当前状态

- 设计基线：PRD / SPEC v0.1。
- 实施阶段：P0 Build Order Step 1（契约层）已于 2026-08-09 完成闭环；A1、A2、A3 均已确认。
- 当前交付：Workflow、四种 Product Profile、18 个 JSON Schema、静态验证器、16 个正例、7 个负例和 33 项契约测试。
- 尚未实现：Orchestrator、Runtime CLI/API、真实 Research、Human Gate 交互和端到端 P0。

## 环境

- Python 3.11+（当前验证环境为 Python 3.14）。
- 依赖见 `requirements-dev.txt`。

## 验证

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe scripts\validate_contracts.py
.\.venv\Scripts\python.exe -m pytest -q
```

如果系统 `python` 启动器指向错误或已删除的解释器，请先解析真实解释器路径，再用该绝对路径运行 `-m venv .venv`。项目验证命令始终使用 `.venv` 中的解释器，避免混用全局 Site Packages。

静态验证器成功返回 `0`，契约或 Schema 错误返回 `2`，未分类内部错误返回 `10`。

2026-08-08 本地验证证据：`[OK] checked=46 errors=0`，`33 passed`，`pip check` 无依赖冲突。

## 文档

- `PRD_v0.1.md`：产品需求基线。
- `SPEC_v0.1.md`：规范性系统与 Workflow 契约。
- `REQUIREMENTS.md`：当前阶段范围和验收标准。
- `IMPLEMENTATION_PLAN.md`：阶段一实施与回滚方案。
- `progress.md`：原子任务与验证证据。
