# 项目约定

## 代码原则

- 编写代码遵循 YAGNI（You Aren’t Gonna Need It）原则，只实现当前明确需要的功能。
- 不为假设中的未来需求引入额外抽象、依赖、配置或扩展机制，优先采用简单直接的实现。

## Python 环境

- 使用名为 `gdut` 的 Conda 环境运行 Python、安装依赖和执行测试。
- 执行相关操作前先运行 `conda activate gdut`；无法激活时，使用 `conda run -n gdut <命令>`。
