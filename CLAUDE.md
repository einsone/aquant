# CLAUDE.md

## 语言

- 始终使用**中文**回答与交流。
- 代码注释、文档字符串、提交信息、PR 描述也使用中文。

## 代码格式要求

每次修改文件后都须运行 prek 跑通全部钩子，保证项目符合规范（配置见 `prek.toml`）：

```bash
prek run --all-files
```

## 常用命令

```bash
uv run python examples/demo.py    # 运行合成数据端到端示例
prek run --all-files              # 每次改动后跑通全部检查
```
