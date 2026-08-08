# Lessons

## 2026-08-08 - YAML 时间戳保持 JSON Wire Shape

- issue: 未加引号的 ISO 时间戳被 PyYAML 解析为 `datetime`，无法通过要求字符串的 JSON Schema。
- root_cause: YAML 隐式类型解析与 JSON 数据模型不完全一致。
- fix: Fixture 中的时间戳统一显式引用为字符串，不放宽 Schema 接受 Python 专有对象。
- prevention: 新增 YAML 契约示例时，所有 `date` / `date-time` 值必须加引号，并经过 YAML 解析后的 Schema 测试。

## 2026-08-08 - Python 启动器与虚拟环境必须同源

- issue: 系统 `python -c` 指向 3.14，但 `python -m venv` 一度解析到已删除的 Python 3.12，生成不可执行环境。
- root_cause: 本机 Python 启动器存在跨版本残留映射，全局 pip 结果不能证明当前解释器可导入依赖。
- fix: 使用已解析的 Python 3.14 绝对路径创建 `.venv`，所有验证命令直接调用虚拟环境解释器。
- prevention: 安装前同时核对 `sys.executable`、`python -m pip --version` 和 `pyvenv.cfg`，不复用未经验证的全局环境。

## 2026-08-08 - 声明式 Schema 与安全语义分层

- issue: JSON Schema 可以约束路径字符串格式，但无法完整证明 Fixture 路径、Schema 引用和 Profile 合成图不会越界或产生第二个 Readiness 写入者。
- root_cause: 这些规则依赖仓库根目录、跨节点图和多个文档的联合上下文。
- fix: 增加根目录 containment、禁止 traversal `$ref`、DAG、结果类型和唯一写入者的确定性 Python Lint。
- prevention: 新增跨文档能力时先判断是否需要语义检查，并同时添加正向实例与恶意/错误负例。
