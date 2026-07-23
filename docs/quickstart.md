# Aquant 快速入门

Aquant 是一个轻量级的 Python 回测框架，专注于信号权重模式的策略回测。

## 安装

```bash
# 克隆仓库
git clone <repo-url>
cd aquant

# 安装依赖（使用 uv）
uv sync
```

## 5 分钟快速开始

### 1. 编写策略

创建一个简单的动量策略：

```python
from datetime import date
from aquant.strategy.base import Strategy
from aquant.core.context import Context
from aquant.strategy.signal import Signal

class MomentumStrategy(Strategy):
    """动量策略：买入过去 20 日涨幅最大的股票"""

    def __init__(self, lookback: int = 20, top_n: int = 5):
        self.lookback = lookback
        self.top_n = top_n
        self.price_history = {}

    def on_bar(self, context: Context) -> list[Signal]:
        """每日调用，生成目标持仓信号"""
        signals = []

        # 更新价格历史
        for symbol, bar in context.bars.items():
            if symbol not in self.price_history:
                self.price_history[symbol] = []
            self.price_history[symbol].append((context.current_date, bar.close))
            # 只保留 lookback 天
            self.price_history[symbol] = self.price_history[symbol][-self.lookback:]

        # 计算动量
        momentum = {}
        for symbol, prices in self.price_history.items():
            if len(prices) >= self.lookback:
                old_price = prices[0][1]
                new_price = prices[-1][1]
                momentum[symbol] = (new_price - old_price) / old_price

        # 选择动量最强的 top_n 只股票
        if momentum:
            sorted_symbols = sorted(momentum.items(), key=lambda x: x[1], reverse=True)
            top_symbols = [s for s, _ in sorted_symbols[:self.top_n]]

            # 生成等权重信号
            target_weight = 1.0 / len(top_symbols)
            for symbol in top_symbols:
                signals.append(Signal(symbol=symbol, weight=target_weight))

        return signals
```

### 2. 准备数据源

使用 ALDS 数据源（本地 A 股数据）或 CSV 数据源：

```python
from aquant.data.alds import ALDSDataSource
# 或者使用 CSV 数据源
# from aquant.data.csv import CSVDataSource

# 初始化数据源
data_source = ALDSDataSource()
# 或者
# data_source = CSVDataSource(data_dir="./data/daily")
```

### 3. 配置回测引擎

```python
from datetime import date
from aquant.core.engine import Engine, BacktestConfig

# 创建策略实例
strategy = MomentumStrategy(lookback=20, top_n=5)

# 配置回测参数
config = BacktestConfig(
    start=date(2023, 1, 1),
    end=date(2023, 12, 31),
    initial_capital=1_000_000.0,
    universe=["000001.SZ", "000002.SZ", "600000.SH", "600519.SH"],  # 股票池
)

# 创建引擎
engine = Engine(
    strategy=strategy,
    data_source=data_source,
    config=config,
)
```

### 4. 运行回测

```python
# 执行回测
result = engine.run()

# 查看结果
print(f"总收益率: {result.metrics['total_return']:.2%}")
print(f"年化收益率: {result.metrics['annualized_return']:.2%}")
print(f"最大回撤: {result.metrics['max_drawdown']:.2%}")
print(f"夏普比率: {result.metrics['sharpe']:.2f}")
```

### 5. 生成报告

```python
from aquant.analytics.report import render_html

# 生成 HTML 报告
render_html(result, path="backtest_report.html")
```

## 核心概念

### 信号权重模式

Aquant 采用**信号权重模式**，策略只需要返回目标持仓权重，框架自动处理订单生成和执行：

```python
def on_bar(self, context: Context) -> list[Signal]:
    # 返回目标持仓，框架自动计算需要的买卖操作
    return [
        Signal(symbol="000001.SZ", weight=0.3),  # 持仓 30%
        Signal(symbol="600000.SH", weight=0.2),  # 持仓 20%
        # 其他持仓自动平仓
    ]
```

优点：

- ✅ 简洁：策略代码更短，专注于信号逻辑
- ✅ 安全：框架自动处理现金管理和持仓调整
- ✅ 一致：所有策略使用统一接口

### 事件驱动架构

回测按照固定的事件顺序执行：

```text
DAY_START → SIGNAL → MATCH → DAY_END
```

- **DAY_START**: 解锁 T+1 持仓
- **SIGNAL**: 调用策略生成信号
- **MATCH**: 撮合订单，更新持仓
- **DAY_END**: 记录净值快照

### Context（上下文）

策略通过 `Context` 访问市场数据和组合状态：

```python
class Context:
    current_date: date           # 当前日期
    bars: dict[str, DayBar]      # 当日行情数据
    positions: dict[str, PositionView]  # 当前持仓
    cash: float                   # 可用现金
    total_value: float            # 组合总市值
    query: PortfolioQueryService  # 历史数据查询服务
```

## 下一步

- 查看 [架构设计文档](architecture.md) 了解框架设计
- 查看 [API 参考](api_reference.md) 了解详细接口
- 查看 `examples/` 目录获取更多策略示例
- 查看 [高级功能](advanced.md) 了解风控、多品种等功能

## 常见问题

### Q: 如何使用自定义数据源？

继承 `DataSource` 并实现接口：

```python
from aquant.data.source import DataSource

class MyDataSource(DataSource):
    def load_calendar(self, start: date, end: date) -> list[date]:
        # 返回交易日列表
        pass

    def load_bars(self, dt: date, symbols: set[str]) -> dict[str, DayBar]:
        # 返回指定日期的行情数据
        pass
```

### Q: 如何添加风控规则？

使用 `RiskManager`：

```python
from aquant.risk import RiskManager, MaxPositionSizeRule, MaxDrawdownRule

risk_manager = RiskManager(rules=[
    MaxPositionSizeRule(max_ratio=0.2),  # 单标的最多 20%
    MaxDrawdownRule(max_dd=0.15),        # 回撤超 15% 停止买入
])

engine = Engine(strategy, data_source, config, risk_manager=risk_manager)
```

### Q: 如何查询历史数据？

通过 `context.query`：

```python
def on_bar(self, context: Context) -> list[Signal]:
    # 查询当前回撤
    current_dd = context.query.get_current_drawdown()

    # 查询净值曲线
    nav_curve = context.query.get_nav_curve()

    # 查询胜率
    win_rate = context.query.get_win_rate(symbol="000001.SZ")

    return signals
```
