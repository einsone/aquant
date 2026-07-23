# 性能优化最佳实践

本文档总结框架的性能优化技巧和最佳实践。

## 目录

- [性能基线](#性能基线)
- [优化技巧](#优化技巧)
- [常见瓶颈](#常见瓶颈)
- [监控与分析](#监控与分析)

## 性能基线

### 标准测试环境

在标准配置下的性能表现：

| 股票数 | 天数 | 耗时 | 吞吐量 |
|--------|------|------|--------|
| 10 | 89 | 0.10s | 9,290 bars/s |
| 50 | 89 | 0.11s | 39,908 bars/s |
| 100 | 89 | 0.15s | 59,388 bars/s |
| 100 | 250 | 0.39s | 64,456 bars/s |

运行基准测试：

```bash
uv run aquant benchmark
```

### 性能目标

- **小规模**（10 股 × 100 天）：< 0.2 秒
- **中规模**（50 股 × 250 天）：< 0.5 秒
- **大规模**（100 股 × 250 天）：< 1 秒

## 优化技巧

### 1. 数据预加载 ⭐️

**问题**：每个交易日多次调用 `load_bars()` 造成重复 I/O

**解决方案**：使用 `DataManager` 预加载数据

```python
from aquant.data.manager import DataManager

# 创建数据管理器（带 LRU 缓存）
data_manager = DataManager(data_source, cache_size=100)

# 预加载整个回测区间的数据
data_manager.preload_range(start_date, end_date, symbols)

# 后续查询直接从内存读取
bars = data_manager.load_bars(date, symbols)
```

**性能提升**：40-50% ✅

**示例**：参考 `examples/preload_demo.py`

### 2. 减少数据加载次数

**问题**：策略中多次调用 `data_source.load_bars()`

**优化前**：

```python
class MyStrategy(Strategy):
    def on_bar(self, context: Context) -> list[Signal]:
        bars1 = self.data_source.load_bars(context.current_date, set1)
        bars2 = self.data_source.load_bars(context.current_date, set2)
        bars3 = self.data_source.load_bars(context.current_date, set3)
```

**优化后**：

```python
class MyStrategy(Strategy):
    def on_bar(self, context: Context) -> list[Signal]:
        # 一次性加载所有需要的股票
        all_symbols = set1 | set2 | set3
        bars = self.data_source.load_bars(context.current_date, all_symbols)
        
        # 按需筛选
        bars1 = {k: v for k, v in bars.items() if k in set1}
        bars2 = {k: v for k, v in bars.items() if k in set2}
```

**性能提升**：20-30% ✅

### 3. 缓存计算结果

**问题**：重复计算相同的指标

**优化前**：

```python
def on_bar(self, context: Context) -> list[Signal]:
    for symbol in symbols:
        ma = self._calculate_ma(symbol)  # 每次都重新计算
```

**优化后**：

```python
def __init__(self):
    self.ma_cache = {}  # 缓存均线结果

def on_bar(self, context: Context) -> list[Signal]:
    for symbol in symbols:
        if symbol not in self.ma_cache:
            self.ma_cache[symbol] = self._calculate_ma(symbol)
        ma = self.ma_cache[symbol]
```

**性能提升**：10-20% ✅

### 4. 使用向量化计算

**问题**：Python 循环计算慢

**优化前**：

```python
# 逐个计算
mean = sum(prices) / len(prices)
variance = sum((p - mean) ** 2 for p in prices) / len(prices)
```

**优化后**：

```python
import numpy as np

# 向量化计算
prices_arr = np.array(prices)
mean = prices_arr.mean()
variance = prices_arr.var()
```

**性能提升**：2-5x ✅

**注意**：需要权衡引入 NumPy 的依赖成本

### 5. 限制历史数据长度

**问题**：保留过多历史数据占用内存

**优化前**：

```python
self.price_history[symbol].append(price)  # 无限增长
```

**优化后**：

```python
self.price_history[symbol].append(price)

# 只保留需要的长度
if len(self.price_history[symbol]) > self.window:
    self.price_history[symbol] = self.price_history[symbol][-self.window:]
```

**内存节省**：50-80% ✅

### 6. 减少对象创建

**问题**：频繁创建短生命周期对象

**优化前**：

```python
def on_bar(self, context: Context) -> list[Signal]:
    signals = []
    for symbol in symbols:
        signal = Signal(symbol=symbol, weight=0.2)
        signals.append(signal)
    return signals
```

**优化后**：

```python
def on_bar(self, context: Context) -> list[Signal]:
    # 批量创建，减少调用次数
    return [
        Signal(symbol=symbol, weight=0.2)
        for symbol in symbols
    ]
```

### 7. 避免重复查询

**问题**：在循环中重复查询同一数据

**优化前**：

```python
for symbol in symbols:
    nav = context.query.get_nav_curve()  # 每次都查询
    if nav[-1] > threshold:
        ...
```

**优化后**：

```python
# 循环外查询一次
nav = context.query.get_nav_curve()

for symbol in symbols:
    if nav[-1] > threshold:
        ...
```

## 常见瓶颈

### 1. 数据加载（40-50%）

**位置**：`Engine.run()` 中的 `load_bars()` 调用

**解决方案**：

- 使用 `DataManager` + `preload_range()`
- 减少 `load_bars()` 调用次数

**详见**：[数据预加载](#1-数据预加载-️)

### 2. Context 构建（15-20%）

**位置**：`Engine._build_context()`

**问题**：

- 每个 SIGNAL 阶段都重新创建 `PortfolioQueryService`
- 持仓视图复制开销

**解决方案**（高级）：

使用 Context 对象池复用对象（需要修改引擎代码）

### 3. 指标计算（10-15%）

**位置**：策略的 `on_bar()` 方法

**解决方案**：

- 使用缓存避免重复计算
- 使用向量化计算
- 使用增量更新而非全量计算

### 4. 撮合引擎（5-10%）

**位置**：`Matcher.match()`

**优化空间有限**，已经是 O(1) 复杂度

### 5. 日志输出（0-5%）

**问题**：频繁的日志输出影响性能

**解决方案**：

```python
import structlog

# 减少日志级别
structlog.configure(
    wrapper_class=structlog.make_filtering_bound_logger(logging.WARNING)
)
```

## 监控与分析

### 使用 Python Profiler

```python
import cProfile
import pstats

# 性能分析
profiler = cProfile.Profile()
profiler.enable()

engine = Engine(strategy, data_source, config)
result = engine.run()

profiler.disable()

# 输出报告
stats = pstats.Stats(profiler)
stats.sort_stats('cumulative')
stats.print_stats(20)  # 打印前 20 个热点
```

### 关键指标

监控以下指标判断性能：

- **总耗时**：完整回测时间
- **平均每天耗时**：总耗时 / 交易日数
- **吞吐量**：bars/秒
- **内存占用**：峰值内存使用

### 性能对比

优化前后对比：

```python
import time

# 优化前
start = time.time()
result1 = engine1.run()
time1 = time.time() - start

# 优化后
start = time.time()
result2 = engine2.run()
time2 = time.time() - start

print(f"性能提升: {(time1 - time2) / time1 * 100:.1f}%")
```

## 优化检查清单

在优化策略性能时，按以下顺序检查：

- [ ] 使用 `DataManager` + `preload_range()`
- [ ] 减少 `load_bars()` 调用次数
- [ ] 缓存计算结果（均线、指标等）
- [ ] 限制历史数据长度
- [ ] 避免循环中重复查询
- [ ] 使用列表推导式代替循环
- [ ] 考虑向量化计算（NumPy）
- [ ] 减少日志输出级别

## 性能 vs 可读性

优化时要权衡性能和代码可读性：

✅ **优先优化**：

- 数据预加载（收益大，改动小）
- 减少重复加载（收益大，改动小）
- 缓存计算结果（收益中，改动小）

⚠️ **谨慎优化**：

- 复杂的对象池（收益小，复杂度高）
- 过度的微优化（收益小，可读性差）
- 引入新依赖（NumPy）（需要权衡）

## 实战案例

### 案例 1：优化动量策略

**原始代码**（0.8 秒）：

```python
def on_bar(self, context: Context) -> list[Signal]:
    signals = []
    for symbol in self.symbols:
        bars = self.data_source.load_bars(context.current_date, {symbol})
        prices = [bars[symbol].close for _ in range(20)]
        momentum = self._calculate_momentum(prices)
        if momentum > 0:
            signals.append(Signal(symbol=symbol, weight=1.0/len(self.symbols)))
    return signals
```

**优化后**（0.3 秒）：

```python
def on_bar(self, context: Context) -> list[Signal]:
    # 一次性加载所有数据
    bars = self.data_source.load_bars(context.current_date, set(self.symbols))
    
    # 批量计算动量
    signals = [
        Signal(symbol=symbol, weight=1.0/len(self.symbols))
        for symbol in self.symbols
        if symbol in bars and self._calculate_momentum_cached(symbol, bars[symbol].close) > 0
    ]
    return signals
```

**性能提升**：62.5% ✅

### 案例 2：优化布林带策略

使用 `DataManager` 预加载数据：

```python
# 优化前：0.5 秒
data_source = CSVDataSource("data/")

# 优化后：0.2 秒
data_manager = DataManager(data_source, cache_size=100)
data_manager.preload_range(start_date, end_date, symbols)
```

**性能提升**：60% ✅

## 总结

性能优化的黄金法则：

1. **先测量，后优化** - 使用 profiler 找出瓶颈
2. **优先低垂的果实** - 先优化收益大、改动小的部分
3. **保持简单** - 不要过度优化牺牲可读性
4. **持续监控** - 定期运行 benchmark 检查性能

参考完整优化分析：[PERFORMANCE_OPTIMIZATION.md](../PERFORMANCE_OPTIMIZATION.md)
