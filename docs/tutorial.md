# 端到端回测教程

本教程从零开始，演示如何使用 Aquant 进行完整的策略回测。

## 步骤 1：准备数据

### 方式 1：使用 CSV 数据

创建测试数据：

```python
from datetime import date
from aquant.data.csv import create_sample_csv

# 生成示例数据
create_sample_csv(
    data_dir="./data/daily",
    start=date(2023, 1, 1),
    end=date(2023, 12, 31),
    symbols=["000001.SZ", "000002.SZ", "600000.SH", "600519.SH"],
)
```

### 方式 2：使用 ALDS

```python
from aquant.data.alds import ALDSDataSource

data_source = ALDSDataSource()
```

## 步骤 2：编写策略

创建一个简单的动量策略：

```python
from aquant.strategy.base import Strategy
from aquant.core.context import Context
from aquant.strategy.signal import Signal

class MyMomentumStrategy(Strategy):
    def __init__(self, lookback=20, top_n=3):
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
            top = sorted(momentum.items(), key=lambda x: x[1], reverse=True)[:self.top_n]
            weight = 1.0 / len(top)
            return [Signal(symbol=s, weight=weight) for s, _ in top]

        return []
```

## 步骤 3：配置回测

```python
from datetime import date
from aquant.core.engine import BacktestConfig

config = BacktestConfig(
    start=date(2023, 1, 1),
    end=date(2023, 12, 31),
    initial_capital=1_000_000.0,
    universe=["000001.SZ", "000002.SZ", "600000.SH", "600519.SH"],
)
```

## 步骤 4：运行回测

```python
from aquant.core.engine import Engine
from aquant.data.csv import CSVDataSource

# 创建引擎
engine = Engine(
    strategy=MyMomentumStrategy(lookback=20, top_n=3),
    data_source=CSVDataSource(data_dir="./data/daily"),
    config=config,
)

# 运行回测
result = engine.run()
```

## 步骤 5：查看结果

```python
# 打印关键指标
print(f"总收益率: {result.metrics['total_return']:.2%}")
print(f"年化收益率: {result.metrics['annualized_return']:.2%}")
print(f"夏普比率: {result.metrics['sharpe']:.2f}")
print(f"最大回撤: {result.metrics['max_drawdown']:.2%}")
print(f"胜率: {result.metrics['win_rate']:.2%}")

# 查看所有指标
for key, value in result.metrics.items():
    print(f"{key}: {value}")
```

## 步骤 6：生成报告

```python
from aquant.analytics.report import render_html

# 生成 HTML 报告
render_html(result, path="my_strategy_report.html")

# 或者直接在浏览器打开
render_html(result, open_browser=True)
```

## 步骤 7：添加风控（可选）

```python
from aquant.risk import RiskManager, MaxPositionSizeRule, MaxDrawdownRule

risk_manager = RiskManager(rules=[
    MaxPositionSizeRule(max_ratio=0.3),  # 单标的不超过 30%
    MaxDrawdownRule(max_dd=0.15),         # 回撤超 15% 停止买入
])

engine = Engine(
    strategy=MyMomentumStrategy(),
    data_source=data_source,
    config=config,
    risk_manager=risk_manager,  # 添加风控
)

result = engine.run()
```

## 步骤 8：参数优化

尝试不同的参数组合：

```python
results = []

for lookback in [10, 20, 30]:
    for top_n in [3, 5, 8]:
        strategy = MyMomentumStrategy(lookback=lookback, top_n=top_n)
        engine = Engine(strategy, data_source, config)
        result = engine.run()

        results.append({
            'lookback': lookback,
            'top_n': top_n,
            'return': result.metrics['total_return'],
            'sharpe': result.metrics['sharpe'],
            'max_dd': result.metrics['max_drawdown'],
        })

# 找到最佳参数
best = max(results, key=lambda x: x['sharpe'])
print(f"最佳参数: lookback={best['lookback']}, top_n={best['top_n']}")
print(f"夏普比率: {best['sharpe']:.2f}")
```

## 步骤 9：使用查询服务

策略内部可以查询历史数据：

```python
class AdaptiveMomentumStrategy(Strategy):
    def on_bar(self, context: Context) -> list[Signal]:
        # 查询当前回撤
        current_dd = context.query.get_current_drawdown()

        # 根据回撤调整仓位
        if current_dd > 0.10:
            # 回撤大于 10%，减仓到 50%
            position_scale = 0.5
        else:
            position_scale = 1.0

        # ... 计算信号
        signals = calculate_signals()

        # 调整权重
        for signal in signals:
            signal.weight *= position_scale

        return signals
```

## 步骤 10：多策略对比

```python
from aquant.analytics.metrics import compute_all

strategies = {
    'Momentum(10,3)': MyMomentumStrategy(10, 3),
    'Momentum(20,5)': MyMomentumStrategy(20, 5),
    'Momentum(30,8)': MyMomentumStrategy(30, 8),
}

results = {}
for name, strategy in strategies.items():
    engine = Engine(strategy, data_source, config)
    result = engine.run()
    results[name] = result.metrics

# 对比指标
import polars as pl

df = pl.DataFrame(results).transpose()
print(df.select(['total_return', 'sharpe', 'max_drawdown']))
```

## 完整示例代码

```python
from datetime import date
from aquant.core.engine import Engine, BacktestConfig
from aquant.data.csv import CSVDataSource, create_sample_csv
from aquant.strategy.base import Strategy
from aquant.core.context import Context
from aquant.strategy.signal import Signal
from aquant.analytics.report import render_html

# 1. 准备数据
create_sample_csv(
    data_dir="./data/daily",
    start=date(2023, 1, 1),
    end=date(2023, 12, 31),
    symbols=["000001.SZ", "000002.SZ", "600000.SH", "600519.SH"],
)

# 2. 定义策略
class MyStrategy(Strategy):
    def __init__(self, lookback=20, top_n=3):
        self.lookback = lookback
        self.top_n = top_n
        self.price_history = {}

    def on_bar(self, context: Context) -> list[Signal]:
        for symbol, bar in context.bars.items():
            if symbol not in self.price_history:
                self.price_history[symbol] = []
            self.price_history[symbol].append(bar.close)
            self.price_history[symbol] = self.price_history[symbol][-self.lookback:]

        momentum = {}
        for symbol, prices in self.price_history.items():
            if len(prices) >= self.lookback:
                momentum[symbol] = (prices[-1] - prices[0]) / prices[0]

        if momentum:
            top = sorted(momentum.items(), key=lambda x: x[1], reverse=True)[:self.top_n]
            weight = 1.0 / len(top)
            return [Signal(symbol=s, weight=weight) for s, _ in top]
        return []

# 3. 配置回测
config = BacktestConfig(
    start=date(2023, 1, 1),
    end=date(2023, 12, 31),
    initial_capital=1_000_000.0,
    universe=["000001.SZ", "000002.SZ", "600000.SH", "600519.SH"],
)

# 4. 运行回测
engine = Engine(
    strategy=MyStrategy(lookback=20, top_n=3),
    data_source=CSVDataSource(data_dir="./data/daily"),
    config=config,
)
result = engine.run()

# 5. 查看结果
print(f"总收益率: {result.metrics['total_return']:.2%}")
print(f"夏普比率: {result.metrics['sharpe']:.2f}")
print(f"最大回撤: {result.metrics['max_drawdown']:.2%}")

# 6. 生成报告
render_html(result, path="report.html")
```

## 常见问题

### Q: 如何调试策略？

在策略中使用 print 输出：

```python
def on_bar(self, context: Context) -> list[Signal]:
    print(f"[{context.current_date}] 现金: {context.cash:.2f}")
    print(f"持仓: {list(context.positions.keys())}")
    # ...
```

### Q: 如何处理停牌股票？

框架自动处理，停牌股票不会出现在 context.bars 中。

### Q: 如何实现止损？

使用查询服务检查持仓盈亏：

```python
def on_bar(self, context: Context) -> list[Signal]:
    signals = []
    for symbol, pos in context.positions.items():
        pnl_pct = (pos.last_close - pos.cost_basis) / pos.cost_basis
        if pnl_pct < -0.05:  # 亏损超过 5%
            # 平仓（不返回该标的的信号）
            continue
        signals.append(Signal(symbol=symbol, weight=...))
    return signals
```

### Q: 如何使用基准对比？

在配置中指定基准：

```python
config = BacktestConfig(
    ...
    benchmark="000300.SH",  # 沪深 300
)
```

回测结果中会包含 Alpha、Beta、超额收益等指标。
