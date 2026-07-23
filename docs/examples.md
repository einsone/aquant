# 示例说明

本文档详细介绍各个示例的功能、用法和学习要点。

## 目录

- [基础示例](#基础示例)
- [策略示例](#策略示例)
- [高级示例](#高级示例)

## 基础示例

### demo.py - 框架演示

**功能**：展示框架的基本用法和网格搜索优化

**运行**：

```bash
uv run python examples/demo.py
```

**学习要点**：

- 如何定义简单的动量策略
- 如何配置回测参数
- 如何使用网格搜索优化参数
- 如何解读回测结果

**关键代码**：

```python
# 定义策略
class MomentumStrategy(Strategy):
    def on_bar(self, context: Context) -> list[Signal]:
        # 策略逻辑
        pass

# 运行回测
engine = Engine(strategy, data_source, config)
result = engine.run()

# 参数优化
results = grid_search(
    strategy_class=MomentumStrategy,
    param_grid={"lookback": [10, 20], "top_n": [3, 5]},
    ...
)
```

### benchmark.py - 性能基准测试

**功能**：测试框架在不同数据规模下的性能

**运行**：

```bash
uv run aquant benchmark
# 或
uv run python examples/benchmark.py
```

**测试场景**：

- 10 只股票 × 100 天
- 50 只股票 × 100 天
- 100 只股票 × 100 天
- 100 只股票 × 250 天

**输出指标**：

- 总耗时
- 平均每天耗时
- 吞吐量（bars/秒）

### preload_demo.py - 数据预加载演示

**功能**：展示如何使用 DataManager 预加载数据提升性能

**运行**：

```bash
uv run python examples/preload_demo.py
```

**学习要点**：

- 使用 `DataManager` 统一管理数据
- 使用 `preload_range()` 预加载数据
- 对比预加载前后的性能差异

**关键代码**：

```python
from aquant.data.manager import DataManager

# 创建数据管理器
data_manager = DataManager(data_source, cache_size=100)

# 预加载数据
data_manager.preload_range(start_date, end_date, symbols)

# 使用预加载的数据
bars = data_manager.load_bars(date, symbols)
```

## 策略示例

### dual_moving_average.py - 双均线策略

**功能**：经典的双均线交叉策略

**策略逻辑**：

- 短期均线上穿长期均线时买入
- 短期均线下穿长期均线时卖出

**运行**：

```bash
uv run python examples/dual_moving_average.py
```

**学习要点**：

- 趋势跟踪策略的实现
- 均线计算
- 金叉/死叉判断
- 等权重持仓配置

**参数说明**：

- `short_window`: 短期均线窗口（默认 5）
- `long_window`: 长期均线窗口（默认 20）

**适用场景**：入门学习、趋势市场

### bollinger_bands.py - 布林带策略

**功能**：基于布林带的均值回归策略

**策略逻辑**：

- 价格触及下轨时买入（超卖）
- 价格触及上轨时卖出（超买）

**运行**：

```bash
uv run python examples/bollinger_bands.py
```

**学习要点**：

- 均值回归策略的实现
- 统计指标计算（均值、标准差）
- 超买超卖判断
- 多标的筛选逻辑

**参数说明**：

- `window`: 均线窗口（默认 20）
- `num_std`: 标准差倍数（默认 2.0）

**适用场景**：震荡市场、均值回归

### risk_controlled_momentum.py - 带风控的动量策略

**功能**：展示完整的风控体系和策略组合

**策略逻辑**：

- 计算动量并选取前 N 名
- 回撤超过阈值时清仓
- 多重风控规则保护

**运行**：

```bash
uv run python examples/risk_controlled_momentum.py
```

**学习要点**：

- 动量策略实现
- 风控规则配置
- QueryService 查询历史数据
- 多重风控组合使用

**风控规则**：

- `MaxPositionSizeRule`: 单仓位不超过 25%
- `MaxDrawdownRule`: 最大回撤不超过 15%
- `ConcentrationRule`: 前 3 大持仓不超过 60%

**参数说明**：

- `lookback`: 动量回看期（默认 20）
- `top_n`: 选取前 N 名（默认 5）
- `max_drawdown_threshold`: 清仓阈值（默认 0.10）

**适用场景**：实战策略、风控学习

## 运行所有示例

```bash
# 依次运行所有示例
for script in examples/*.py; do
    echo "运行 $script..."
    uv run python "$script"
done
```

## 自定义示例

基于现有示例创建自己的策略：

### 1. 复制模板

```bash
cp examples/dual_moving_average.py my_strategy.py
```

### 2. 修改策略逻辑

```python
class MyStrategy(Strategy):
    def on_bar(self, context: Context) -> list[Signal]:
        # 你的策略逻辑
        signals = []
        # ...
        return signals
```

### 3. 运行测试

```bash
# 验证代码
uv run aquant validate my_strategy.py

# 运行回测
uv run aquant run my_strategy.py
```

## 示例对比

| 示例 | 难度 | 类型 | 特点 |
|------|------|------|------|
| demo.py | 入门 | 动量 | 参数优化 |
| dual_moving_average.py | 入门 | 趋势跟踪 | 经典策略 |
| bollinger_bands.py | 中级 | 均值回归 | 统计指标 |
| risk_controlled_momentum.py | 高级 | 动量+风控 | 完整体系 |
| benchmark.py | - | 工具 | 性能测试 |
| preload_demo.py | 中级 | 工具 | 性能优化 |

## 常见问题

### 示例运行失败怎么办？

1. 确保已安装依赖：`uv sync`
2. 检查 Python 版本：需要 >= 3.12
3. 查看错误信息并根据提示修复

### 如何修改股票池？

修改示例中的 `symbols` 列表：

```python
symbols = ["AAPL", "GOOGL", "MSFT"]  # 自定义股票列表
```

### 如何修改回测时间？

修改 `BacktestConfig` 中的日期：

```python
config = BacktestConfig(
    start=date(2022, 1, 1),
    end=date(2023, 12, 31),
    initial_capital=1_000_000.0
)
```

### 如何使用真实数据？

替换 CSVDataSource 为 ALDSDataSource：

```python
from aquant.data.alds import ALDSDataSource

# 需要先安装: pip install alds
data_source = ALDSDataSource()
```

或实现自定义数据源继承 `DataSource` 基类。

## 下一步

- 阅读 [快速入门](quickstart.md) 了解框架基础
- 阅读 [架构设计](architecture.md) 深入理解框架
- 阅读 [API 参考](api_reference.md) 查看完整 API
