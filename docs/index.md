# Aquant

轻量级 Python 量化回测框架

## 特性

- **简洁优雅**：核心代码约 3000 行，易于理解和扩展
- **类型安全**：完整的类型注解 + ty 类型检查
- **信号权重模式**：策略只需返回目标权重，框架自动处理订单生成
- **事件驱动**：松耦合的事件架构，易于扩展
- **可插拔风控**：灵活的风控规则系统
- **多资产支持**：支持股票、期货、期权等多种资产
- **实盘接口**：提供券商适配器抽象层

## 快速开始

### 安装

```bash
pip install aquant
```

或使用 uv（推荐）：

```bash
uv pip install aquant
```

### 简单示例

```python
from datetime import date
from aquant import Strategy, Signal, Engine, BacktestConfig
from aquant.data.bigquant import BigQuantDataSource

class MyStrategy(Strategy):
    """简单双均线策略"""

    warmup_period = 20
    rebalance_mode = "replace"

    def on_bar(self, context):
        # 策略逻辑
        signals = []
        # ... 计算信号
        return signals

# 配置回测
config = BacktestConfig(
    start=date(2023, 1, 1),
    end=date(2023, 12, 31),
    initial_capital=1_000_000.0,
)

# 运行回测
data_source = BigQuantDataSource()
engine = Engine(MyStrategy(), data_source, config)
result = engine.run()

# 查看结果
print(result.metrics)
result.render_html(open_browser=True)
```

## 核心概念

### 信号权重模式

策略只需返回目标权重，框架自动计算买卖操作：

```python
def on_bar(self, context):
    return [
        Signal(symbol="000001.SZ", weight=0.3),  # 目标 30%
        Signal(symbol="600000.SH", weight=0.2),  # 目标 20%
    ]
```

### 事件驱动

框架使用事件驱动架构，各模块通过事件通信：

- 松耦合：模块之间通过事件接口交互
- 可扩展：新增功能通过订阅事件实现
- 可观测：所有关键操作都发布事件

### 风控管理

可插拔的风控规则系统：

```python
from aquant.risk import RiskManager, MaxPositionSizeRule, MaxDrawdownRule

risk_manager = RiskManager(rules=[
    MaxPositionSizeRule(max_ratio=0.2),
    MaxDrawdownRule(max_dd=0.15),
])

engine = Engine(strategy, data_source, config, risk_manager=risk_manager)
```

## 文档导航

- [快速开始](getting-started/installation.md) - 安装和基础示例
- [用户指南](guide/concepts.md) - 核心概念和策略开发
- [API 参考](api/engine.md) - 完整 API 文档
- [架构设计](architecture.md) - 框架设计思想

## 示例

查看 [examples](examples.md) 目录获取更多示例：

- 双均线策略
- 布林带策略
- 动量策略
- 实盘交易示例

## 测试覆盖

框架包含 82 个单元测试，覆盖所有核心模块：

```bash
uv run pytest tests/ -v
```

## 许可证

MIT License
