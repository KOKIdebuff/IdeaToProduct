# Tech Stack

## Runtime and Language

- Python 3.11+；当前本地解释器为 Python 3.14.5。
- JSON Schema Draft 2020-12。
- YAML 作为 Workflow、Profile 和契约实例格式。

## Core Libraries

- `jsonschema[format]==4.26.0`：Meta-Schema、实例和格式校验。
- `PyYAML==6.0.3`：使用 `yaml.safe_load` 解析 YAML。
- `pytest==9.1.1`：契约与语义测试。

## Data and Storage

- 本阶段仅包含仓库内 YAML / JSON / Markdown。
- 不实现 Runtime State 持久化写入、数据库或事件日志写入器。

## Infra and Tooling

- `scripts/validate_contracts.py` 提供确定性本地验证。
- `requirements-dev.txt` 固定直接依赖版本。
- `.venv/` 提供隔离运行环境；验证命令不依赖全局 Site Packages。

## Tradeoffs

- JSON Schema 负责结构、格式和局部条件；DAG、跨节点类型与路径等语义由 Python Lint 负责。
- 使用本地相对 `$ref`，避免依赖未部署的远程 Schema 服务。
- 本机默认 Python 启动器存在 3.14/失效 3.12 映射不一致，因此实际验证使用由 Python 3.14 绝对路径创建的 `.venv`；该环境目录不进入版本控制。
