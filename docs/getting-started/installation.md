# 安装

## 系统要求

- Python 3.10+
- 支持 Linux / macOS / Windows

## 使用 pip 安装

```bash
pip install aquant
```

## 使用 uv 安装（推荐）

[uv](https://github.com/astral-sh/uv) 是更快的 Python 包管理器：

```bash
# 安装 uv
curl -LsSf https://astral.sh/uv/install.sh | sh

# 安装 aquant
uv pip install aquant
```

## 从源码安装

```bash
git clone https://github.com/yourusername/aquant.git
cd aquant
uv pip install -e .
```

## 验证安装

```python
import aquant
print(aquant.__version__)
```

## 依赖项

核心依赖：

- `polars`: 高性能数据处理
- `pydantic`: 数据验证
- `structlog`: 结构化日志
- `tqdm`: 进度条

可选依赖：

- `mkdocs`: 文档生成
- `pytest`: 测试框架

## 下一步

查看 [基础示例](basic-example.md) 开始使用。
