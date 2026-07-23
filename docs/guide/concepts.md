# 核心概念

本文介绍 aquant 框架的核心概念和设计理念。

## 设计哲学

### 信号权重模式

aquant 采用**信号权重模式**，策略只需返回目标持仓权重，框架自动处理以下细节：

- 订单生成：计算需要买卖的股票和数量
- 订单执行：模拟撮合或调用实盘接口
- 持仓管理：跟踪当前持仓和可用资金
- 成本计算：自动扣除佣金、印花税、滑点

这种模式让策略代码更简洁，专注于投资逻辑而非交易细节。

### 事件驱动架构

回测引擎采用事件驱动架构：

```text
数据源 → 事件流 → 策略 → 信号 → 风控 → 订单 → 撮合 → 持仓更新
```

每个交易日触发一个 `BarEvent`，驱动整个回测流程：

1. 加载当日行情数据
2. 调用策略的 `on_bar` 方法
3. 策略返回目标权重信号
4. 风控模块检查信号
5. 生成订单并撮合
6. 更新持仓和资金

## 核心组件

### Strategy（策略）

策略是回测的核心，定义投资逻辑。

```python
from aquant import Strategy, Signal, Context

class MyStrategy(Strategy):
    warmup_period = 20  # 预热期：需要多少天历史数据
    rebalance_mode = "replace"  # 调仓模式：replace 或 incremental

    def on_bar(self, context: Context) -> list[Signal]:
        """每个交易日调用一次

        Args:
            context: 上下文对象，提供查询接口

        Returns:
            信号列表，每个信号包含 symbol 和 weight
        """
        # 实现选股逻辑
        return [
            Signal(symbol="000001.SZ", weight=0.5),
            Signal(symbol="600000.SH", weight=0.5),
        ]
```

**关键属性：**

- `warmup_period`：预热期天数，框架会预加载这些数据
- `rebalance_mode`：
  - `replace`：完全替换持仓（未出现在信号中的股票会被清仓）
  - `incremental`：增量调整（只调整信号中的股票）

### Signal（信号）

信号表示目标持仓权重：

```python
Signal(symbol="000001.SZ", weight=0.3)
```

- `symbol`：股票代码
- `weight`：目标权重（0-1 之间，总和应为 1.0）
- `weight=0` 表示清仓

### Context（上下文）

上下文提供策略运行时的查询接口：

```python
def on_bar(self, context: Context) -> list[Signal]:
    # 当前日期
    today = context.current_date

    # 查询历史行情
    bars = context.query.get_bars(symbol="000001.SZ", count=20)

    # 查询当前持仓
    position = context.query.get_position("000001.SZ")

    # 查询可用资金
    cash = context.query.get_cash()

    # 查询总资产
    total_value = context.query.get_total_value()
```

**主要查询方法：**

- `get_bars(symbol, count)`：获取最近 N 根 K 线
- `get_position(symbol)`：获取持仓数量
- `get_cash()`：获取可用资金
- `get_total_value()`：获取总资产（持仓市值 + 现金）

### DataSource（数据源）

数据源提供历史行情数据：

```python
from aquant.data.source import DataSource
from aquant.market.bar import DayBar
from datetime import date

class MyDataSource(DataSource):
    def load_calendar(self, start: date, end: date) -> list[date]:
        """加载交易日历"""
        return [date(2023, 1, 3), date(2023, 1, 4), ...]

    def load_bars(self, dt: date, symbols: set[str]) -> dict[str, DayBar]:
        """加载指定日期的行情数据"""
        return {
            "000001.SZ": DayBar(
                symbol="000001.SZ",
                date=dt,
                open=10.0,
                high=10.5,
                low=9.8,
                close=10.2,
                volume=1000000,
            )
        }

    def load_adjustments(self, start: date, end: date):
        """加载企业行动（分红、送转）"""
        return []

    def load_delisted(self, start: date, end: date):
        """加载退市信息"""
        return {}
```

框架内置两个数据源：

- `ALDSDataSource`：从 ALDS 数据服务加载
- `CSVDataSource`：从 CSV 文件加载

### RiskControl（风控）

风控模块在信号转订单前进行检查：

```python
from aquant.risk.guard import RiskGuard

class MyRiskGuard(RiskGuard):
    def check(self, signal: Signal, context: Context) -> bool:
        """检查信号是否符合风控规则

        Returns:
            True：允许交易
            False：拒绝交易
        """
        # 示例：限制单只股票最大仓位
        if signal.weight > 0.3:
            return False
        return True
```

内置风控规则：

- `MaxPositionGuard`：单只股票最大仓位限制
- `MaxDrawdownGuard`：最大回撤限制
- `VolatilityGuard`：波动率限制

### Portfolio（投资组合）

投资组合跟踪持仓、现金和净值：

```python
portfolio = engine._portfolio

# 查询持仓
positions = portfolio.positions  # dict[str, int]

# 查询现金
cash = portfolio.cash

# 查询总资产
total_value = portfolio.total_value

# 查询每日净值
daily_nav = portfolio._daily_nav  # polars DataFrame
```

### Engine（回测引擎）

回测引擎驱动整个回测流程：

```python
from aquant import Engine, BacktestConfig
from datetime import date

config = BacktestConfig(
    start=date(2023, 1, 1),
    end=date(2023, 12, 31),
    initial_capital=1_000_000.0,
    commission_rate=0.0003,  # 万三佣金
    stamp_duty_rate=0.001,   # 千一印花税
    min_commission=5.0,       # 最低佣金 5 元
    slippage_rate=0.0005,    # 万五滑点
)

engine = Engine(strategy, data_source, config)
result = engine.run()
```

## 数据流

### 1. 初始化阶段

```text
DataSource.load_calendar() → 获取交易日列表
DataSource.load_bars() → 预加载 warmup_period 天数据
Strategy.__init__() → 初始化策略状态
```

### 2. 回测循环

每个交易日重复以下流程：

```text
1. 加载当日行情 → DataSource.load_bars(today, symbols)
2. 调用策略 → Strategy.on_bar(context) → list[Signal]
3. 风控检查 → RiskGuard.check(signal) → bool
4. 生成订单 → Matcher.generate_orders(signals, positions)
5. 订单撮合 → Matcher.match(orders, bars)
6. 更新持仓 → Portfolio.update(trades)
7. 记录净值 → Portfolio.record_nav(date, value)
```

### 3. 结果分析

```text
Portfolio → BacktestResult → 计算指标 → 生成报告
```

## 交易成本

框架自动计算交易成本：

### 佣金

```python
commission = max(
    min_commission,
    shares * price * commission_rate
)
```

### 印花税（仅卖出）

```python
stamp_duty = shares * price * stamp_duty_rate  # 仅卖出时收取
```

### 滑点

```python
buy_price = close * (1 + slippage_rate)   # 买入时价格上浮
sell_price = close * (1 - slippage_rate)  # 卖出时价格下浮
```

### 总成本

```python
total_cost = commission + stamp_duty + slippage
```

## 调仓模式

### Replace 模式（完全替换）

每次调仓完全替换持仓：

```python
# 上次持仓：A=30%, B=30%, C=40%
# 新信号：A=50%, D=50%
# 结果：B 和 C 被清仓，A 增持到 50%，D 新建仓 50%
```

适合场景：定期全面调仓的策略（如月度调仓）

### Incremental 模式（增量调整）

只调整信号中的股票：

```python
# 上次持仓：A=30%, B=30%, C=40%
# 新信号：A=50%, D=50%
# 结果：A 增持到 50%，D 新建仓 50%，B 和 C 保持不变
```

适合场景：增量调整策略（如日内 T+0）

## 类型安全

aquant 使用 `ty` 进行类型检查，确保代码正确性：

```python
from aquant import Strategy, Signal, Context

class MyStrategy(Strategy):
    def on_bar(self, context: Context) -> list[Signal]:
        # 返回错误类型会在编译期报错
        return "wrong type"  # ❌ 类型错误

        return [Signal(symbol="000001.SZ", weight=0.5)]  # ✅ 正确
```

运行类型检查：

```bash
prek run --all-files  # 包含 ty 类型检查
```

## 下一步

- [策略开发指南](strategy.md) - 学习如何编写策略
- [数据源接入](data-source.md) - 接入自定义数据源
- [风控管理](risk-management.md) - 添加风控规则
- [实盘交易](live-trading.md) - 将策略部署到实盘
