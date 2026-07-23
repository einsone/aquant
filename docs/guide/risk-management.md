# 风控管理

本文介绍如何在策略中添加风控规则，保护资金安全。

## 风控概述

风控（Risk Control）是量化交易的重要组成部分，用于：

- 限制单只股票的最大仓位
- 控制总体风险暴露
- 设置止损止盈条件
- 防止极端情况下的巨额亏损

aquant 提供两种风控方式：

1. **RiskGuard**：在信号转订单前检查，拒绝不符合条件的信号
2. **策略内风控**：在策略逻辑中实现风控规则

## RiskGuard 风控

### 内置风控规则

#### MaxPositionGuard

限制单只股票的最大仓位：

```python
from aquant import Engine, BacktestConfig
from aquant.risk.guard import MaxPositionGuard

# 限制单只股票最大仓位 30%
guard = MaxPositionGuard(max_weight=0.3)

engine = Engine(strategy, data_source, config, risk_guards=[guard])
result = engine.run()
```

#### MaxDrawdownGuard

当回撤超过阈值时停止交易：

```python
from aquant.risk.guard import MaxDrawdownGuard

# 回撤超过 20% 时停止交易
guard = MaxDrawdownGuard(max_drawdown=0.2)

engine = Engine(strategy, data_source, config, risk_guards=[guard])
result = engine.run()
```

#### VolatilityGuard

根据股票波动率限制仓位：

```python
from aquant.risk.guard import VolatilityGuard

# 高波动股票（日波动率 > 3%）最大仓位 10%
guard = VolatilityGuard(
    max_volatility=0.03,
    max_weight_if_high_vol=0.1
)

engine = Engine(strategy, data_source, config, risk_guards=[guard])
result = engine.run()
```

### 自定义风控规则

实现 `RiskGuard` 接口：

```python
from aquant.risk.guard import RiskGuard
from aquant.strategy.signal import Signal
from aquant.core.context import Context

class CustomRiskGuard(RiskGuard):
    def check(self, signal: Signal, context: Context) -> bool:
        """检查信号是否符合风控规则
        
        Args:
            signal: 策略生成的信号
            context: 上下文对象
            
        Returns:
            True: 允许交易
            False: 拒绝交易
        """
        # 实现自定义风控逻辑
        return True
```

### 风控规则示例

#### 行业集中度限制

限制单个行业的总仓位：

```python
from aquant.risk.guard import RiskGuard
from aquant.strategy.signal import Signal
from aquant.core.context import Context

class SectorConcentrationGuard(RiskGuard):
    def __init__(self, sector_map: dict[str, str], max_sector_weight: float = 0.4):
        """
        Args:
            sector_map: 股票代码 -> 行业名称的映射
            max_sector_weight: 单个行业最大仓位
        """
        self.sector_map = sector_map
        self.max_sector_weight = max_sector_weight
    
    def check(self, signal: Signal, context: Context) -> bool:
        # 获取该股票的行业
        sector = self.sector_map.get(signal.symbol)
        if sector is None:
            return True
        
        # 计算该行业当前总仓位
        sector_weight = 0.0
        for symbol, position in context.query.get_all_positions().items():
            if self.sector_map.get(symbol) == sector:
                sector_weight += position / context.query.get_total_value()
        
        # 加上新信号的权重
        new_sector_weight = sector_weight + signal.weight
        
        # 检查是否超过限制
        if new_sector_weight > self.max_sector_weight:
            return False
        
        return True

# 使用
sector_map = {
    "600036.SH": "金融",
    "601398.SH": "金融",
    "000001.SZ": "金融",
    "600519.SH": "消费",
    "000002.SZ": "科技",
}

guard = SectorConcentrationGuard(sector_map, max_sector_weight=0.4)
```

#### 换手率限制

限制单日换手率，避免过度交易：

```python
from aquant.risk.guard import RiskGuard
from aquant.strategy.signal import Signal
from aquant.core.context import Context

class TurnoverGuard(RiskGuard):
    def __init__(self, max_turnover: float = 0.5):
        """
        Args:
            max_turnover: 最大单日换手率（0-1）
        """
        self.max_turnover = max_turnover
        self.daily_turnover = 0.0
        self.last_date = None
    
    def check(self, signal: Signal, context: Context) -> bool:
        # 新的一天，重置计数
        if self.last_date != context.current_date:
            self.daily_turnover = 0.0
            self.last_date = context.current_date
        
        # 计算本次交易的换手量
        current_position = context.query.get_position(signal.symbol)
        current_weight = current_position / context.query.get_total_value()
        turnover = abs(signal.weight - current_weight)
        
        # 检查累计换手是否超限
        if self.daily_turnover + turnover > self.max_turnover:
            return False
        
        # 更新累计换手
        self.daily_turnover += turnover
        return True
```

#### 交易时间限制

限制只在特定时间段交易：

```python
from aquant.risk.guard import RiskGuard
from aquant.strategy.signal import Signal
from aquant.core.context import Context

class TradingTimeGuard(RiskGuard):
    def __init__(self, allowed_hours: list[int] = None):
        """
        Args:
            allowed_hours: 允许交易的小时列表，None 表示不限制
        """
        self.allowed_hours = allowed_hours or list(range(24))
    
    def check(self, signal: Signal, context: Context) -> bool:
        # 注意：日线回测中没有具体时间，这个示例仅供参考
        # 实际使用时需要根据具体场景调整
        current_hour = context.current_date.hour if hasattr(context.current_date, 'hour') else 14
        return current_hour in self.allowed_hours
```

## 策略内风控

在策略逻辑中直接实现风控规则：

### 止损止盈

```python
from aquant import Strategy, Signal, Context

class StopLossStrategy(Strategy):
    warmup_period = 20
    rebalance_mode = "replace"
    
    def __init__(self, symbol: str):
        self.symbol = symbol
        self.entry_price = None
        self.stop_loss = 0.05  # 5% 止损
        self.take_profit = 0.10  # 10% 止盈
    
    def on_bar(self, context: Context) -> list[Signal]:
        bars = context.query.get_bars(symbol=self.symbol, count=self.warmup_period)
        
        if len(bars) < self.warmup_period:
            return []
        
        current_price = bars[-1].close
        position = context.query.get_position(self.symbol)
        
        # 有持仓：检查止损止盈
        if position > 0:
            if self.entry_price is None:
                # 回测重启后恢复入场价
                self.entry_price = current_price
            
            profit_rate = (current_price - self.entry_price) / self.entry_price
            
            # 触发止损
            if profit_rate < -self.stop_loss:
                self.entry_price = None
                return []  # 清仓
            
            # 触发止盈
            if profit_rate > self.take_profit:
                self.entry_price = None
                return []  # 清仓
        
        # 无持仓：寻找入场机会
        else:
            if self._should_enter(bars):
                self.entry_price = current_price
                return [Signal(symbol=self.symbol, weight=1.0)]
        
        return []
    
    def _should_enter(self, bars: list) -> bool:
        # 入场逻辑
        return True
```

### 最大回撤限制

```python
from aquant import Strategy, Signal, Context

class DrawdownControlStrategy(Strategy):
    warmup_period = 20
    rebalance_mode = "replace"
    
    def __init__(self):
        self.max_drawdown = 0.15  # 15% 最大回撤
        self.peak_value = 0.0
        self.stopped = False
    
    def on_bar(self, context: Context) -> list[Signal]:
        current_value = context.query.get_total_value()
        
        # 更新峰值
        if current_value > self.peak_value:
            self.peak_value = current_value
        
        # 计算当前回撤
        if self.peak_value > 0:
            drawdown = (self.peak_value - current_value) / self.peak_value
            
            # 回撤超过阈值，停止交易
            if drawdown > self.max_drawdown:
                self.stopped = True
                return []  # 清仓并停止交易
        
        # 已停止交易
        if self.stopped:
            return []
        
        # 正常交易逻辑
        return self._generate_signals(context)
    
    def _generate_signals(self, context: Context) -> list[Signal]:
        # 实现选股逻辑
        return []
```

### 仓位管理

#### 凯利公式仓位

根据胜率和赔率动态调整仓位：

```python
from aquant import Strategy, Signal, Context

class KellyPositionStrategy(Strategy):
    warmup_period = 20
    rebalance_mode = "replace"
    
    def __init__(self, symbol: str):
        self.symbol = symbol
        self.win_rate = 0.6  # 预估胜率
        self.avg_win = 0.15  # 平均盈利
        self.avg_loss = 0.08  # 平均亏损
    
    def on_bar(self, context: Context) -> list[Signal]:
        bars = context.query.get_bars(symbol=self.symbol, count=self.warmup_period)
        
        if len(bars) < self.warmup_period:
            return []
        
        # 凯利公式：f = (p * b - q) / b
        # p: 胜率, q: 败率, b: 赔率（盈亏比）
        p = self.win_rate
        q = 1 - p
        b = self.avg_win / self.avg_loss
        
        kelly_fraction = (p * b - q) / b
        
        # 限制仓位在 0-100% 之间
        kelly_fraction = max(0, min(1, kelly_fraction))
        
        # 保守起见，使用半凯利
        position_size = kelly_fraction * 0.5
        
        if position_size > 0:
            return [Signal(symbol=self.symbol, weight=position_size)]
        return []
```

#### 等波动率仓位

根据股票波动率调整仓位：

```python
from aquant import Strategy, Signal, Context

class VolatilityParityStrategy(Strategy):
    warmup_period = 60
    rebalance_mode = "replace"
    
    def __init__(self, universe: list[str]):
        self.universe = universe
        self.target_volatility = 0.15  # 目标组合波动率
    
    def on_bar(self, context: Context) -> list[Signal]:
        volatilities = {}
        
        # 计算各股票波动率
        for symbol in self.universe:
            bars = context.query.get_bars(symbol=symbol, count=self.warmup_period)
            if len(bars) == self.warmup_period:
                vol = self._calc_volatility(bars)
                volatilities[symbol] = vol
        
        if not volatilities:
            return []
        
        # 计算等波动率权重
        signals = []
        total_inv_vol = sum(1 / v for v in volatilities.values())
        
        for symbol, vol in volatilities.items():
            # 权重与波动率成反比
            weight = (1 / vol) / total_inv_vol
            signals.append(Signal(symbol=symbol, weight=weight))
        
        return signals
    
    def _calc_volatility(self, bars: list) -> float:
        """计算年化波动率"""
        returns = []
        for i in range(1, len(bars)):
            ret = (bars[i].close - bars[i-1].close) / bars[i-1].close
            returns.append(ret)
        
        avg_return = sum(returns) / len(returns)
        variance = sum((r - avg_return) ** 2 for r in returns) / len(returns)
        daily_vol = variance ** 0.5
        annual_vol = daily_vol * (252 ** 0.5)  # 年化
        
        return annual_vol
```

## 组合多个风控规则

```python
from aquant import Engine, BacktestConfig
from aquant.risk.guard import MaxPositionGuard, MaxDrawdownGuard

# 组合多个风控规则
guards = [
    MaxPositionGuard(max_weight=0.3),      # 单只股票最大 30%
    MaxDrawdownGuard(max_drawdown=0.2),    # 最大回撤 20%
    SectorConcentrationGuard(sector_map, max_sector_weight=0.4),  # 行业集中度 40%
    TurnoverGuard(max_turnover=0.5),       # 日换手率 50%
]

engine = Engine(strategy, data_source, config, risk_guards=guards)
result = engine.run()
```

## 风控监控

### 实时监控指标

```python
from aquant import Strategy, Signal, Context
import structlog

logger = structlog.get_logger()

class MonitoredStrategy(Strategy):
    warmup_period = 20
    rebalance_mode = "replace"
    
    def __init__(self):
        self.initial_capital = 0.0
        self.peak_value = 0.0
    
    def on_bar(self, context: Context) -> list[Signal]:
        current_value = context.query.get_total_value()
        
        # 首次初始化
        if self.initial_capital == 0:
            self.initial_capital = current_value
            self.peak_value = current_value
        
        # 更新峰值
        if current_value > self.peak_value:
            self.peak_value = current_value
        
        # 计算关键指标
        total_return = (current_value - self.initial_capital) / self.initial_capital
        drawdown = (self.peak_value - current_value) / self.peak_value if self.peak_value > 0 else 0
        
        # 记录监控信息
        logger.info(
            "风控监控",
            date=context.current_date,
            total_value=f"{current_value:,.0f}",
            total_return=f"{total_return * 100:.2f}%",
            drawdown=f"{drawdown * 100:.2f}%",
            cash=f"{context.query.get_cash():,.0f}",
        )
        
        # 生成信号
        return self._generate_signals(context)
    
    def _generate_signals(self, context: Context) -> list[Signal]:
        return []
```

## 最佳实践

### 1. 分层风控

```python
# 第一层：策略内风控（选股阶段）
class Strategy:
    def on_bar(self, context):
        # 过滤低质量股票
        # 控制换手率
        pass

# 第二层：RiskGuard（信号检查）
guards = [
    MaxPositionGuard(),
    SectorConcentrationGuard(),
]

# 第三层：全局风控（引擎层）
config = BacktestConfig(
    max_drawdown=0.2,  # 最大回撤限制
)
```

### 2. 渐进式风控

```python
class GradualStopLoss(Strategy):
    """渐进式止损：持仓时间越长，止损线越高"""
    
    def __init__(self):
        self.entry_date = None
        self.entry_price = None
    
    def on_bar(self, context):
        if self.entry_date:
            days_held = (context.current_date - self.entry_date).days
            
            # 止损线随时间提升
            if days_held < 5:
                stop_loss = 0.05  # 5%
            elif days_held < 10:
                stop_loss = 0.03  # 3%
            else:
                stop_loss = 0.01  # 1%（移动到盈亏平衡点附近）
```

### 3. 压力测试

在极端行情下测试策略：

```python
# 测试策略在 2015 年股灾期间的表现
config = BacktestConfig(
    start=date(2015, 6, 1),
    end=date(2015, 9, 1),
    initial_capital=1_000_000.0,
)

result = engine.run()
print(f"股灾期间最大回撤: {result.metrics['max_drawdown'] * 100:.2f}%")
```

## 下一步

- [策略开发](strategy.md) - 在策略中集成风控
- [实盘交易](live-trading.md) - 实盘风控注意事项
- [性能优化](../best_practices.md) - 优化风控性能
