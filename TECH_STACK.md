# Tech Stack

## Runtime and Language

- Python 3.11+；当前本地解释器为 Python 3.14.5。
- JSON Schema Draft 2020-12。
- YAML 作为 Registry、Workflow、Profile 和契约实例格式；JSON 用于 Schema、Manifest 与部分 Fixture。

## Core Libraries

- `jsonschema[format]==4.26.0`：Meta-Schema、实例和格式校验。
- `PyYAML==6.0.3`：使用 `yaml.safe_load` 解析 YAML。
- `pytest==9.1.1`：契约与语义测试。

## Data and Storage

- 本阶段仅包含仓库内 YAML / JSON / Markdown 和静态 SHA-256 完整性清单。
- 不实现 Runtime State 持久化写入、数据库或事件日志写入器。

## Infra and Tooling

- `scripts/contract_bundles.py` 提供 Registry、Bundle Context、路径解析、版本闭包和 Legacy Ref 静态决策。
- `scripts/validate_contracts.py` 提供 v0.1/v0.2 参数化、确定性本地验证。
- `requirements-dev.txt` 固定直接依赖版本。
- `.venv/` 提供隔离运行环境；验证命令不依赖全局 Site Packages。

## Tradeoffs

- JSON Schema 负责结构、格式和局部条件；DAG、跨节点类型与路径等语义由 Python Lint 负责。
- 使用所选 Bundle 内的本地相对 `$ref`，避免远程 Schema 服务与跨版本回退。
- 采用并行完整 Bundle 而不是在单 Schema Tree 中混合 0.1/0.2 条件；文件较多，但版本边界更可审计、回滚更直接。
- 未新增运行时依赖；Legacy 内容哈希使用 Python 标准库 `hashlib`。
- 本机默认 Python 启动器存在 3.14/失效 3.12 映射不一致，因此实际验证使用由 Python 3.14 绝对路径创建的 `.venv`；该环境目录不进入版本控制。
