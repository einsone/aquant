# 基础示例

完整的回测示例，从策略开发到结果分析。

## 完整示例

```python
from datetime import date
from aquant import Strategy, Signal, Engine, BacktestConfig
from aquant.data.bigquant import BigQuantDataSource

# 1. 定义策略
class DualMovingAverageStrategy(Strategy):
    """双均线策略"""
    
    warmup_period = 60  # 需要 60 天历史数据
    rebalance_mode = "replace"  # 完全替换持仓
    
    def __init__(self):
        self.fast_period = 20
        self.slow_period = 60
        self.universe = ["000001.SZ", "600000.SH", "000002.SZ"]
    
    def on_bar(self, context):
        signals = []
        
        for symbol in self.universe:
            # 获取历史数据
            bars = context.query.get_bars(
                symbol=symbol,
                count=self.slow_period
            )
            
            if len(bars) < self.slow_period:
                continue
            
            # 计算均线
            closes = [b.close for b in bars]
            fast_ma = sum(closes[-self.fast_period:]) / self.fast_period
            slow_ma = sum(closes) / self.slow_period
            
            # 金叉买入
            if fast_ma > slow_ma:
                signals.append(Signal(symbol=symbol, weight=1.0 / 3))
        
        return signals

# 2. 配置回测
config = BacktestConfig(
    start=date(2023, 1, 1),
    end=date(2023, 12, 31),
    initial_capital=1_000_000.0,
    commission_rate=0.0003,  # 万三佣金
    stamp_duty_rate=0.001,   # 千一印花税
    min_commission=5.0,       # 最低佣金 5 元
    slippage_rate=0.0005,    # 万五滑点
    show_progress=True,       # 显示进度条
)

# 3. 运行回测
data_source = BigQuantDataSource()
engine = Engine(DualMovingAverageStrategy(), data_source, config)
result = engine.run()

# 4. 查看结果
print("=" * 70)
print("回测结果")
print("=" * 70)
print(f"总收益率: {result.metrics['total_return'] * 100:.2f}%")
print(f"年化收益率: {result.metrics['annual_return'] * 100:.2f}%")
print(f"夏普比率: {result.metrics['sharpe']:.2f}")
print(f"最大回撤: {result.metrics['max_drawdown'] * 100:.2f}%")
print(f"胜率: {result.metrics['win_rate'] * 100:.2f}%")
print(f"交易次数: {len(result.trades)}")

# 5. 生成报告
result.render_html(path="backtest_report.html", open_browser=True)
```

## 输出示例

```
======================================================================
回测结果
======================================================================
总收益率: 15.32%
年化收益率: 15.32%
夏普比率: 1.23
最大回撤: -8.45%
胜率: 58.33%
交易次数: 24
```

## 关键步骤说明

### 1. 定义策略

- 继承 `Strategy` 基类
- 设置 `warmup_period`（预热期）
- 设置 `rebalance_mode`（调仓模式）
- 实现 `on_bar` 方法返回信号

### 2. 配置回测

- 设置时间范围
- 设置初始资金
- 配置交易成本（佣金、印花税、滑点）
- 可选：显示进度条

### 3. 运行回测

- 创建数据源
- 创建 Engine 实例
- 调用 `run()` 方法

### 4. 分析结果

- `result.metrics`: 绩效指标字典
- `result.trades`: 交易记录列表
- `result.daily_nav`: 每日净值数据
- `result.positions`: 最终持仓

### 5. 生成报告

- `render_html()`: 生成交互式 HTML 报告
- `report()`: 生成 Markdown 报告

## 下一步

- [核心概念](../guide/concepts.md) - 深入理解框架设计
- [策略开发](../guide/strategy.md) - 开发更复杂的策略
- [风控管理](../guide/risk-management.md) - 添加风控规则
