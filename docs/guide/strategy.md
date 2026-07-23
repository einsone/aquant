# 策略开发指南

本文介绍如何开发量化交易策略，从简单到复杂。

## 策略基础

### 最简单的策略

买入并持有策略：

```python
from aquant import Strategy, Signal, Context

class BuyAndHoldStrategy(Strategy):
    warmup_period = 1
    rebalance_mode = "replace"

    def __init__(self, symbol: str):
        self.symbol = symbol
        self.initialized = False

    def on_bar(self, context: Context) -> list[Signal]:
        # 只在第一天建仓
        if not self.initialized:
            self.initialized = True
            return [Signal(symbol=self.symbol, weight=1.0)]
        return []
```

### 双均线策略

经典的技术分析策略：

```python
from aquant import Strategy, Signal, Context

class DualMAStrategy(Strategy):
    warmup_period = 60
    rebalance_mode = "replace"

    def __init__(self, symbol: str, fast: int = 5, slow: int = 20):
        self.symbol = symbol
        self.fast_period = fast
        self.slow_period = slow

    def on_bar(self, context: Context) -> list[Signal]:
        # 获取历史数据
        bars = context.query.get_bars(
            symbol=self.symbol,
            count=self.slow_period
        )

        if len(bars) < self.slow_period:
            return []

        # 计算均线
        closes = [b.close for b in bars]
        fast_ma = sum(closes[-self.fast_period:]) / self.fast_period
        slow_ma = sum(closes) / self.slow_period

        # 金叉买入，死叉卖出
        if fast_ma > slow_ma:
            return [Signal(symbol=self.symbol, weight=1.0)]
        else:
            return []
```

## 多股票策略

### 轮动策略

动态选择表现最好的股票：

```python
from aquant import Strategy, Signal, Context

class RotationStrategy(Strategy):
    warmup_period = 20
    rebalance_mode = "replace"

    def __init__(self, universe: list[str], top_n: int = 5):
        self.universe = universe
        self.top_n = top_n

    def on_bar(self, context: Context) -> list[Signal]:
        # 计算每只股票的动量
        momentum = {}
        for symbol in self.universe:
            bars = context.query.get_bars(symbol=symbol, count=self.warmup_period)
            if len(bars) == self.warmup_period:
                momentum[symbol] = (bars[-1].close - bars[0].close) / bars[0].close

        # 选出动量最大的 top_n 只股票
        sorted_stocks = sorted(momentum.items(), key=lambda x: x[1], reverse=True)
        top_stocks = sorted_stocks[:self.top_n]

        # 等权重配置
        if top_stocks:
            weight = 1.0 / len(top_stocks)
            return [Signal(symbol=s, weight=weight) for s, _ in top_stocks]
        return []
```

### 行业轮动策略

基于行业表现进行轮动：

```python
from aquant import Strategy, Signal, Context

class SectorRotationStrategy(Strategy):
    warmup_period = 60
    rebalance_mode = "replace"

    def __init__(self):
        # 定义行业股票池
        self.sectors = {
            "金融": ["600036.SH", "601398.SH"],
            "科技": ["000002.SZ", "600519.SH"],
            "消费": ["000001.SZ", "600000.SH"],
        }

    def on_bar(self, context: Context) -> list[Signal]:
        # 计算各行业动量
        sector_momentum = {}
        for sector_name, symbols in self.sectors.items():
            returns = []
            for symbol in symbols:
                bars = context.query.get_bars(symbol=symbol, count=self.warmup_period)
                if len(bars) == self.warmup_period:
                    ret = (bars[-1].close - bars[0].close) / bars[0].close
                    returns.append(ret)
            if returns:
                sector_momentum[sector_name] = sum(returns) / len(returns)

        # 选择动量最强的行业
        if sector_momentum:
            best_sector = max(sector_momentum.items(), key=lambda x: x[1])[0]
            symbols = self.sectors[best_sector]
            weight = 1.0 / len(symbols)
            return [Signal(symbol=s, weight=weight) for s in symbols]
        return []
```

## 因子策略

### 单因子策略

基于单个因子选股：

```python
from aquant import Strategy, Signal, Context

class ValueStrategy(Strategy):
    """市盈率因子策略"""
    warmup_period = 1
    rebalance_mode = "replace"

    def __init__(self, universe: list[str], top_n: int = 10):
        self.universe = universe
        self.top_n = top_n

    def on_bar(self, context: Context) -> list[Signal]:
        # 获取当日行情和基本面数据
        pe_ratios = {}
        for symbol in self.universe:
            bars = context.query.get_bars(symbol=symbol, count=1)
            if bars:
                # 这里简化处理，实际需要从基本面数据源获取 PE
                # pe = get_pe_from_fundamental_data(symbol, context.current_date)
                pe = 15.0  # 示例值
                pe_ratios[symbol] = pe

        # 选出 PE 最低的股票
        sorted_stocks = sorted(pe_ratios.items(), key=lambda x: x[1])
        top_stocks = sorted_stocks[:self.top_n]

        if top_stocks:
            weight = 1.0 / len(top_stocks)
            return [Signal(symbol=s, weight=weight) for s, _ in top_stocks]
        return []
```

### 多因子合成

结合多个因子的得分：

```python
from aquant import Strategy, Signal, Context

class MultiFactorStrategy(Strategy):
    warmup_period = 60
    rebalance_mode = "replace"

    def __init__(self, universe: list[str], top_n: int = 10):
        self.universe = universe
        self.top_n = top_n
        # 因子权重
        self.factor_weights = {
            "momentum": 0.3,
            "value": 0.3,
            "quality": 0.4,
        }

    def on_bar(self, context: Context) -> list[Signal]:
        scores = {}

        for symbol in self.universe:
            bars = context.query.get_bars(symbol=symbol, count=self.warmup_period)
            if len(bars) < self.warmup_period:
                continue

            # 计算各因子得分
            momentum = self._calc_momentum(bars)
            value = self._calc_value(bars)
            quality = self._calc_quality(bars)

            # 加权合成
            total_score = (
                self.factor_weights["momentum"] * momentum +
                self.factor_weights["value"] * value +
                self.factor_weights["quality"] * quality
            )
            scores[symbol] = total_score

        # 选出得分最高的股票
        sorted_stocks = sorted(scores.items(), key=lambda x: x[1], reverse=True)
        top_stocks = sorted_stocks[:self.top_n]

        if top_stocks:
            weight = 1.0 / len(top_stocks)
            return [Signal(symbol=s, weight=weight) for s, _ in top_stocks]
        return []

    def _calc_momentum(self, bars: list) -> float:
        """动量因子"""
        return (bars[-1].close - bars[-20].close) / bars[-20].close

    def _calc_value(self, bars: list) -> float:
        """价值因子（简化）"""
        avg_price = sum(b.close for b in bars) / len(bars)
        return -bars[-1].close / avg_price  # 负号表示价格越低越好

    def _calc_quality(self, bars: list) -> float:
        """质量因子：成交量稳定性"""
        volumes = [b.volume for b in bars]
        avg_vol = sum(volumes) / len(volumes)
        variance = sum((v - avg_vol) ** 2 for v in volumes) / len(volumes)
        return -variance / (avg_vol ** 2)  # 负号表示波动越小越好
```

## 状态管理

### 策略内部状态

维护策略运行状态：

```python
from aquant import Strategy, Signal, Context

class StatefulStrategy(Strategy):
    warmup_period = 20
    rebalance_mode = "replace"

    def __init__(self):
        self.position = None  # 当前持仓状态
        self.entry_price = 0.0  # 入场价格
        self.days_held = 0  # 持仓天数

    def on_bar(self, context: Context) -> list[Signal]:
        symbol = "000001.SZ"
        bars = context.query.get_bars(symbol=symbol, count=self.warmup_period)

        if len(bars) < self.warmup_period:
            return []

        current_price = bars[-1].close

        # 无持仓：寻找入场机会
        if self.position is None:
            if self._should_enter(bars):
                self.position = symbol
                self.entry_price = current_price
                self.days_held = 0
                return [Signal(symbol=symbol, weight=1.0)]

        # 有持仓：判断是否离场
        else:
            self.days_held += 1
            if self._should_exit(bars, current_price):
                self.position = None
                self.entry_price = 0.0
                self.days_held = 0
                return []

        return []

    def _should_enter(self, bars: list) -> bool:
        """入场条件"""
        # 示例：突破 20 日高点
        max_price = max(b.high for b in bars[:-1])
        return bars[-1].close > max_price

    def _should_exit(self, bars: list, current_price: float) -> bool:
        """离场条件"""
        # 止盈：涨幅超过 10%
        if current_price > self.entry_price * 1.1:
            return True
        # 止损：跌幅超过 5%
        if current_price < self.entry_price * 0.95:
            return True
        # 时间止损：持仓超过 10 天
        if self.days_held > 10:
            return True
        return False
```

## 高级技巧

### 动态调整仓位

根据市场条件调整仓位：

```python
from aquant import Strategy, Signal, Context

class DynamicPositionStrategy(Strategy):
    warmup_period = 20
    rebalance_mode = "replace"

    def __init__(self, symbol: str):
        self.symbol = symbol

    def on_bar(self, context: Context) -> list[Signal]:
        bars = context.query.get_bars(symbol=self.symbol, count=self.warmup_period)

        if len(bars) < self.warmup_period:
            return []

        # 计算市场波动率
        returns = []
        for i in range(1, len(bars)):
            ret = (bars[i].close - bars[i-1].close) / bars[i-1].close
            returns.append(ret)

        avg_return = sum(returns) / len(returns)
        variance = sum((r - avg_return) ** 2 for r in returns) / len(returns)
        volatility = variance ** 0.5

        # 根据波动率调整仓位
        if volatility < 0.01:  # 低波动
            weight = 1.0
        elif volatility < 0.02:  # 中波动
            weight = 0.5
        else:  # 高波动
            weight = 0.2

        return [Signal(symbol=self.symbol, weight=weight)]
```

### 多周期策略

结合不同时间周期的信号：

```python
from aquant import Strategy, Signal, Context

class MultiTimeframeStrategy(Strategy):
    warmup_period = 250  # 需要足够长的历史数据
    rebalance_mode = "replace"

    def __init__(self, symbol: str):
        self.symbol = symbol

    def on_bar(self, context: Context) -> list[Signal]:
        bars = context.query.get_bars(symbol=symbol, count=self.warmup_period)

        if len(bars) < self.warmup_period:
            return []

        # 长周期趋势（200 日）
        long_trend = self._calc_trend(bars, 200)

        # 中周期趋势（50 日）
        mid_trend = self._calc_trend(bars, 50)

        # 短周期趋势（10 日）
        short_trend = self._calc_trend(bars, 10)

        # 只有三个周期都看多才入场
        if long_trend > 0 and mid_trend > 0 and short_trend > 0:
            return [Signal(symbol=self.symbol, weight=1.0)]
        return []

    def _calc_trend(self, bars: list, period: int) -> float:
        """计算趋势强度"""
        closes = [b.close for b in bars[-period:]]
        ma = sum(closes) / len(closes)
        return (bars[-1].close - ma) / ma
```

## 调试技巧

### 打印调试信息

```python
from aquant import Strategy, Signal, Context
import structlog

logger = structlog.get_logger()

class DebugStrategy(Strategy):
    warmup_period = 20
    rebalance_mode = "replace"

    def on_bar(self, context: Context) -> list[Signal]:
        symbol = "000001.SZ"
        bars = context.query.get_bars(symbol=symbol, count=self.warmup_period)

        # 打印调试信息
        logger.info(
            "策略运行",
            date=context.current_date,
            bars_count=len(bars),
            cash=context.query.get_cash(),
            total_value=context.query.get_total_value(),
        )

        # ... 策略逻辑
        return []
```

### 记录自定义指标

```python
from aquant import Strategy, Signal, Context

class MetricsStrategy(Strategy):
    warmup_period = 20
    rebalance_mode = "replace"

    def __init__(self):
        self.metrics = []  # 记录自定义指标

    def on_bar(self, context: Context) -> list[Signal]:
        # 计算并记录指标
        self.metrics.append({
            "date": context.current_date,
            "cash": context.query.get_cash(),
            "total_value": context.query.get_total_value(),
        })

        # ... 策略逻辑
        return []
```

## 最佳实践

### 1. 避免未来函数

确保策略只使用当前及过去的数据：

```python
# ❌ 错误：使用了未来数据
bars = context.query.get_bars(symbol, count=20)
tomorrow_price = bars[0].close  # 这是明天的价格！

# ✅ 正确：只使用当前和历史数据
bars = context.query.get_bars(symbol, count=20)
today_price = bars[-1].close  # 今天的收盘价
yesterday_price = bars[-2].close  # 昨天的收盘价
```

### 2. 处理数据缺失

```python
def on_bar(self, context: Context) -> list[Signal]:
    bars = context.query.get_bars(symbol, count=20)

    # 数据不足时直接返回
    if len(bars) < 20:
        return []

    # ... 策略逻辑
```

### 3. 控制交易频率

```python
class LowFrequencyStrategy(Strategy):
    def __init__(self):
        self.rebalance_days = 0
        self.rebalance_period = 20  # 每 20 天调仓一次

    def on_bar(self, context: Context) -> list[Signal]:
        self.rebalance_days += 1

        # 不到调仓日不交易
        if self.rebalance_days < self.rebalance_period:
            return []

        self.rebalance_days = 0
        # ... 调仓逻辑
```

### 4. 参数化策略

```python
class ParameterizedStrategy(Strategy):
    def __init__(
        self,
        fast_period: int = 5,
        slow_period: int = 20,
        top_n: int = 10,
        rebalance_days: int = 20,
    ):
        self.fast_period = fast_period
        self.slow_period = slow_period
        self.top_n = top_n
        self.rebalance_days = rebalance_days
        self.warmup_period = slow_period
```

## 下一步

- [风控管理](risk-management.md) - 添加风控规则保护策略
- [数据源接入](data-source.md) - 接入自定义数据源
- [实盘交易](live-trading.md) - 将策略部署到实盘
