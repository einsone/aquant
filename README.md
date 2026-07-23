# Aquant

一个轻量级、类型安全的 Python 量化回测框架，专注于信号权重模式的策略回测。

[![Python](https://img.shields.io/badge/python-3.12+-blue.svg)](https://www.python.org/downloads/)
[![Code style: ruff](https://img.shields.io/badge/code%20style-ruff-000000.svg)](https://github.com/astral-sh/ruff)

## ✨ 特性

- 🎯 **信号权重模式** - 策略只需返回目标权重，框架自动处理订单
- 🔒 **类型安全** - 完整的类型注解，编译期类型检查
- 🚀 **简洁易用** - 核心代码 ~3000 行，学习曲线平缓
- 🛡️ **可插拔风控** - 内置多种风控规则，支持自定义
- 📊 **完整分析** - 提供 20+ 绩效指标和可视化报告
- 🔧 **高度可扩展** - 插件式架构，支持自定义数据源、交易规则等
- 📚 **中文文档** - 完整的中文文档和示例

## 🚀 快速开始

### 安装

```bash
git clone <repo-url>
cd aquant
uv sync
```

### 第一个策略

```python
from datetime import date
from aquant.strategy.base import Strategy
from aquant.core.context import Context
from aquant.strategy.signal import Signal

class MomentumStrategy(Strategy):
    """动量策略：买入过去 20 日涨幅最大的 5 只股票"""

    def __init__(self, lookback: int = 20, top_n: int = 5):
        self.lookback = lookback
        self.top_n = top_n
        self.price_history = {}

    def on_bar(self, context: Context) -> list[Signal]:
        # 更新价格历史
        for symbol, bar in context.bars.items():
            if symbol not in self.price_history:
                self.price_history[symbol] = []
            self.price_history[symbol].append(bar.close)
            self.price_history[symbol] = self.price_history[symbol][-self.lookback:]

        # 计算动量并选股
        momentum = {}
        for symbol, prices in self.price_history.items():
            if len(prices) >= self.lookback:
                momentum[symbol] = (prices[-1] - prices[0]) / prices[0]

        if momentum:
            top_symbols = sorted(momentum.items(), key=lambda x: x[1], reverse=True)[:self.top_n]
            weight = 1.0 / len(top_symbols)
            return [Signal(symbol=s, weight=weight) for s, _ in top_symbols]

        return []
```

### 运行回测

```python
from aquant.core.engine import Engine, BacktestConfig
from aquant.data.bigquant import BigQuantDAISource

# 配置回测
config = BacktestConfig(
    start=date(2023, 1, 1),
    end=date(2023, 12, 31),
    initial_capital=1_000_000.0,
    universe=["000001.SZ", "000002.SZ", "600000.SH", "600519.SH"],
)

# 运行回测
engine = Engine(
    strategy=MomentumStrategy(lookback=20, top_n=5),
    data_source=BigQuantDAISource(),
    config=config,
)
result = engine.run()

# 查看结果
print(f"总收益率: {result.metrics['total_return']:.2%}")
print(f"夏普比率: {result.metrics['sharpe']:.2f}")
print(f"最大回撤: {result.metrics['max_drawdown']:.2%}")
```

## 📖 文档

- [快速入门](docs/quickstart.md) - 5 分钟上手
- [架构设计](docs/architecture.md) - 深入理解框架设计
- [API 参考](docs/api_reference.md) - 完整的 API 文档

## 🎨 核心概念

### 信号权重模式

策略只需返回目标持仓权重，框架自动计算买卖操作：

```python
def on_bar(self, context: Context) -> list[Signal]:
    return [
        Signal(symbol="000001.SZ", weight=0.3),  # 目标持仓 30%
        Signal(symbol="600000.SH", weight=0.2),  # 目标持仓 20%
        # 其他持仓自动平仓
    ]
```

### 查询服务（CQRS）

策略可以查询历史数据：

```python
def on_bar(self, context: Context) -> list[Signal]:
    # 查询当前回撤
    current_dd = context.query.get_current_drawdown()

    # 回撤过大时减仓
    if current_dd > 0.15:
        return []

    return signals
```

### 风控管理

可插拔的风控规则：

```python
from aquant.risk import RiskManager, MaxPositionSizeRule, MaxDrawdownRule

risk_manager = RiskManager(rules=[
    MaxPositionSizeRule(max_ratio=0.2),   # 单标的不超过 20%
    MaxDrawdownRule(max_dd=0.15),         # 回撤超 15% 停止买入
])

engine = Engine(strategy, data_source, config, risk_manager=risk_manager)
```

## 📊 绩效分析

框架提供完整的绩效指标：

**收益指标**
- 累计收益率、年化收益率

**风险指标**
- 年化波动率、最大回撤

**风险调整收益**
- 夏普比率、卡玛比率

**交易统计**
- 胜率、盈亏比、换手率

**相对指标**（需提供基准）
- Alpha、Beta、信息比率

## 🔧 高级特性

### 多品种支持

支持不同品种的交易规则：

```python
from aquant.matching.rules import FuturesRules

# 期货回测（T+0）
futures_rules = FuturesRules()
```

### 事件驱动

基于消息总线的事件系统：

```python
from aquant.events.bus import MessageBus

bus = MessageBus()

# 订阅订单成交事件
def on_fill(event):
    print(f"成交: {event.symbol} {event.shares}股")

bus.subscribe("order.filled", on_fill)
```

### 数据缓存

内置 LRU 缓存提升性能：

```python
from aquant.data.manager import DataManager

manager = DataManager(data_source, cache_size=256)
manager.preload_range(start, end, symbols)  # 预加载数据
```

## 🧪 测试

项目包含完整的单元测试：

```bash
# 运行所有测试
uv run pytest

# 运行特定测试
uv run pytest tests/test_risk.py -v
```

**测试覆盖**：
- ✅ 61 个单元测试
- ✅ 100% 核心模块覆盖
- ✅ 所有新功能都有测试

## 🛠️ 开发

### 代码质量检查

```bash
# 运行所有检查
prek run --all-files

# 包括：
# - ruff (代码规范)
# - ruff format (代码格式)
# - ty (类型检查)
# - markdownlint (文档检查)
```

### 项目结构

```
aquant/
├── core/           # 核心引擎
├── strategy/       # 策略基类
├── portfolio/      # 组合管理
├── matching/       # 订单撮合
├── risk/           # 风控模块
├── analytics/      # 绩效分析
├── data/           # 数据源
├── events/         # 事件系统
└── market/         # 市场数据
```

## 📈 示例

查看 `examples/` 目录获取更多示例：

- `demo.py` - 基础回测示例
- `momentum_acceleration.py` - 动量加速策略

## 🙏 致谢

框架设计参考了以下优秀项目：

- [VnPy](https://github.com/vnpy/vnpy) - 仓位管理和数据管理设计
- [NautilusTrader](https://github.com/nautechsystems/nautilus_trader) - 消息总线和 CQRS 模式
- [Backtrader](https://github.com/mementum/backtrader) - 策略抽象
