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
- 🌐 **多资产支持** - 支持股票、期货、期权等多种资产类型
- 🔌 **实盘交易** - 提供券商适配器接口，支持实盘交易
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
from aquant.data.alds import ALDSDataSource

# 股票池定义
UNIVERSE = ["000001.SZ", "000002.SZ", "600000.SH", "600519.SH"]

class MomentumStrategy(Strategy):
    """动量策略：买入过去 20 日涨幅最大的 5 只股票"""

    warmup_period: int = 20
    rebalance_mode: str = "replace"

    def __init__(self, lookback: int = 20, top_n: int = 5, data_source: ALDSDataSource | None = None):
        self.lookback = lookback
        self.top_n = top_n
        self.data_source = data_source
        self.price_history = {}

    def on_bar(self, context: Context) -> list[Signal]:
        if self.data_source is None:
            return []

        # 从数据源加载当日行情
        bars = self.data_source.load_bars(context.current_date, set(UNIVERSE))

        # 更新价格历史
        for symbol, bar in bars.items():
            if symbol not in self.price_history:
                self.price_history[symbol] = []
            self.price_history[symbol].append(bar.close)
            self.price_history[symbol] = self.price_history[symbol][-self.lookback:]

        # 计算动量并选股
        momentum = {}
        for symbol in UNIVERSE:
            prices = self.price_history.get(symbol, [])
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
from aquant.data.alds import ALDSDataSource

# 配置回测
config = BacktestConfig(
    start=date(2023, 1, 1),
    end=date(2023, 12, 31),
    initial_capital=1_000_000.0,
)

# 创建数据源
data_source = ALDSDataSource()

# 运行回测
engine = Engine(
    strategy=MomentumStrategy(lookback=20, top_n=5, data_source=data_source),
    data_source=data_source,
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

### 收益指标

- 累计收益率、年化收益率

### 风险指标

- 年化波动率、最大回撤

### 风险调整收益

- 夏普比率、卡玛比率

### 交易统计

- 胜率、盈亏比、换手率

**相对指标**（需提供基准）

- Alpha、Beta、信息比率

## 🔧 高级特性

### 多资产支持

框架支持股票、期货、期权等多种资产类型：

```python
from aquant.market.bar import AssetType

# DayBar 自动识别资产类型
bar = DayBar(
    symbol="IF2312",
    date=date(2023, 12, 15),
    open=3800.0,
    close=3850.0,
    high=3900.0,
    low=3750.0,
    volume=100000.0,
    up_limit=4000.0,
    down_limit=3600.0,
    is_halted=False,
    asset_type=AssetType.FUTURE  # 期货
)
```

### 实盘交易

框架提供券商适配器接口，支持实盘交易：

```python
from aquant.broker.adapter import BrokerAdapter, OrderSide, OrderType
from aquant.broker.simulated import SimulatedBroker

# 使用模拟券商测试
broker = SimulatedBroker(initial_cash=100000.0)

# 提交订单
order = broker.submit_order(
    symbol="AAPL",
    side=OrderSide.BUY,
    quantity=100,
    price=150.0,
    order_type=OrderType.LIMIT
)

# 查询持仓
positions = broker.get_positions()

# 查询资金
cash = broker.get_cash()
total_value = broker.get_total_value()
```

**对接真实券商**：

1. 继承 `BrokerAdapter` 基类
2. 实现 `submit_order`、`cancel_order`、`get_positions` 等方法
3. 参考 `examples/live_trading.py` 了解完整流程

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

```text
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
- `dual_moving_average.py` - 双均线策略
- `bollinger_bands.py` - 布林带策略
- `risk_controlled_momentum.py` - 风控动量策略
- `live_trading.py` - 实盘交易示例
- `benchmark.py` - 性能基准测试

详细说明请参考 [示例文档](docs/examples.md)。

## ❓ 常见问题（FAQ）

### 如何开始使用？

最快的方式是运行内置示例：

```bash
# 运行双均线策略示例
uv run python examples/dual_moving_average.py

# 或使用 CLI 工具
uv run aquant run examples/dual_moving_average.py
```

### 支持哪些数据源？

框架内置两种数据源：

- **CSVDataSource** - 本地 CSV 文件（开箱即用，适合测试）
- **ALDSDataSource** - ALDS 数据平台（需安装 `alds` 库）

也可以继承 `DataSource` 基类实现自定义数据源。

### 如何验证策略代码？

使用 CLI 工具的 validate 命令：

```bash
uv run aquant validate my_strategy.py
```

会检查策略是否包含必需的组件（Strategy 类、main 函数）。

### 性能如何？

在标准测试环境下：

- **吞吐量**：9,000 - 64,000 bars/秒
- **100 只股票 × 250 天**：约 0.4 秒

运行性能基准测试：

```bash
uv run aquant benchmark
```

### 如何添加风控规则？

创建 `RiskManager` 并添加规则：

```python
from aquant.risk import RiskManager, MaxPositionSizeRule, MaxDrawdownRule

risk_manager = RiskManager(rules=[
    MaxPositionSizeRule(max_ratio=0.25),  # 单仓位不超过 25%
    MaxDrawdownRule(max_dd=0.15),         # 最大回撤不超过 15%
])

engine = Engine(strategy, data_source, config, risk_manager=risk_manager)
```

### 支持多品种回测吗？

支持。框架已添加多资产类型支持（股票、期货、期权）：

```python
from aquant.market.bar import AssetType

# 创建期货行情数据
bar = DayBar(
    symbol="IF2312",
    asset_type=AssetType.FUTURE,
    # ... 其他字段
)
```

配合不同的交易规则（`StockRules`、`FuturesRules`）可以回测不同品种。

### 如何进行实盘交易？

框架提供券商适配器接口：

1. 对于测试和演示，使用内置的 `SimulatedBroker`
2. 对于真实交易，继承 `BrokerAdapter` 实现具体券商接口

查看 `examples/live_trading.py` 了解完整示例：

```bash
uv run python examples/live_trading.py
```

### 如何获取帮助？

- 查看 [快速入门](docs/quickstart.md)
- 查看 [API 参考](docs/api_reference.md)
- 查看 [示例代码](examples/)
- 提交 Issue 到 GitHub

## 🙏 致谢

框架设计参考了以下优秀项目：

- [VnPy](https://github.com/vnpy/vnpy) - 仓位管理和数据管理设计
- [NautilusTrader](https://github.com/nautechsystems/nautilus_trader) - 消息总线和 CQRS 模式
- [Backtrader](https://github.com/mementum/backtrader) - 策略抽象
