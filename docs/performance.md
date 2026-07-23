# 性能优化指南

本文档提供 aquant 框架的性能优化建议和最佳实践。

## 性能基准

### 典型性能指标

在标准硬件上（4 核 CPU，16GB 内存），aquant 的典型性能：

| 场景 | 性能指标 |
|------|---------|
| 10 只股票，252 交易日 | 6000+ 天/秒 |
| 20 只股票，252 交易日 | 5000+ 天/秒 |
| 30 只股票，252 交易日 | 4000+ 天/秒 |
| 50 只股票，252 交易日 | 2600+ 天/秒 |

### 运行基准测试

```bash
# 基准测试：10 只股票，252 个交易日
uv run python tools/benchmark.py baseline 10 252

# 性能分析：10 只股票，252 个交易日
uv run python tools/benchmark.py profile 10 252

# 规模测试：测试不同股票数量的性能
uv run python tools/benchmark.py scale 50
```

## 性能分析工具

### 1. 函数性能分析装饰器

使用 `@profile_function` 装饰器分析函数性能：

```python
from aquant.tools.profiler import profile_function

@profile_function
def my_strategy_logic():
    # 你的代码
    pass
```

### 2. 代码块性能分析

使用 `PerformanceProfiler` 分析代码块：

```python
from aquant.tools.profiler import PerformanceProfiler

profiler = PerformanceProfiler()

with profiler:
    result = engine.run()

# 打印最耗时的 20 个函数
profiler.print_top(20)

# 保存详细报告
profiler.save_report("performance_report.txt")
```

### 3. 计时器

使用 `Timer` 测量多个阶段的耗时：

```python
from aquant.tools.profiler import Timer

timer = Timer()

timer.start("data_loading")
# 加载数据
timer.stop("data_loading")

timer.start("computation")
# 计算
timer.stop("computation")

timer.print_summary()
```

### 4. cProfile 性能分析

识别回测引擎的热点路径：

```bash
uv run python benchmarks/profile_engine.py
```

使用 snakeviz 可视化分析结果：

```bash
uv run snakeviz performance_profile.stats
```

### 5. 并行回测

对比多个策略时使用并行回测：

```bash
uv run python benchmarks/parallel_backtest.py
```


#### 使用数据缓存

```python
from aquant.data.alds import ALDSDataSource

class CachedDataSource:
    def __init__(self, underlying: ALDSDataSource):
        self.underlying = underlying
        self._cache = {}

    def load_bars(self, dt: date, symbols: set[str]):
        key = (dt, frozenset(symbols))
        if key not in self._cache:
            self._cache[key] = self.underlying.load_bars(dt, symbols)
        return self._cache[key]
```

#### 预加载数据

对于多次回测同一时间段的场景，预加载数据可以显著提升性能：

```python
data_source = ALDSDataSource()

# 预加载数据
calendar = data_source.load_calendar(start, end)
symbols = {"000001.SZ", "000002.SZ"}

bars_cache = {}
for dt in calendar:
    bars_cache[dt] = data_source.load_bars(dt, symbols)
```

### 2. 策略优化

#### 避免重复计算

**不好的做法：**

```python
def on_bar(self, context: Context) -> list[Signal]:
    for symbol in self.universe:
        bars = context.query.get_bars(symbol, count=20)
        # 每次都重新计算均线
        ma = sum(b.close for b in bars) / len(bars)
```

**好的做法：**

```python
def __init__(self):
    self.ma_cache = {}  # 缓存计算结果

def on_bar(self, context: Context) -> list[Signal]:
    for symbol in self.universe:
        bars = context.query.get_bars(symbol, count=20)
        # 增量更新均线
        if symbol in self.ma_cache:
            old_ma = self.ma_cache[symbol]
            new_ma = old_ma + (bars[-1].close - bars[0].close) / len(bars)
        else:
            new_ma = sum(b.close for b in bars) / len(bars)
        self.ma_cache[symbol] = new_ma
```

#### 减少数据查询次数

**不好的做法：**

```python
def on_bar(self, context: Context) -> list[Signal]:
    for symbol in self.universe:
        bars = context.query.get_bars(symbol, count=20)  # 重复查询
        position = context.query.get_position(symbol)    # 重复查询
```

**好的做法：**

```python
def on_bar(self, context: Context) -> list[Signal]:
    # 批量查询一次
    all_bars = {s: context.query.get_bars(s, count=20) for s in self.universe}
    all_positions = {s: context.query.get_position(s) for s in self.universe}

    for symbol in self.universe:
        bars = all_bars[symbol]
        position = all_positions[symbol]
```

#### 控制股票池大小

股票池越大，回测越慢。建议：

- 日内策略：10-20 只股票
- 日频策略：20-50 只股票
- 周频策略：50-100 只股票

### 3. 调仓频率优化

#### 降低调仓频率

```python
class LowFrequencyStrategy(Strategy):
    def __init__(self):
        self.rebalance_period = 20  # 每 20 天调仓一次
        self.days_since_rebalance = 0

    def on_bar(self, context: Context) -> list[Signal]:
        self.days_since_rebalance += 1

        # 不到调仓日，返回空信号
        if self.days_since_rebalance < self.rebalance_period:
            return []

        self.days_since_rebalance = 0
        # 执行调仓逻辑
        return self._generate_signals(context)
```

#### 设置调仓阈值

只在权重变化超过阈值时才调仓：

```python
config = BacktestConfig(
    start=date(2023, 1, 1),
    end=date(2023, 12, 31),
    initial_capital=1_000_000.0,
    rebalance_threshold=0.05,  # 权重变化超过 5% 才调仓
)
```

### 4. 并行化

#### 多策略并行回测

使用并行回测工具同时运行多个策略：

```python
from benchmarks.parallel_backtest import run_parallel_backtest

results = run_parallel_backtest(
    strategy_configs,
    backtest_config,
    max_workers=4,  # 使用 4 个进程
)
```

#### 参数优化并行化

```python
import concurrent.futures

def optimize_parameter(param_value):
    strategy = MyStrategy(param=param_value)
    engine = Engine(strategy, data_source, config)
    result = engine.run()
    result.compute_metrics()
    return param_value, result.metrics['sharpe']

# 并行测试多个参数
param_values = [5, 10, 15, 20, 25]
with concurrent.futures.ProcessPoolExecutor(max_workers=4) as executor:
    results = list(executor.map(optimize_parameter, param_values))

best_param = max(results, key=lambda x: x[1])[0]
print(f"最优参数: {best_param}")
```

### 5. 内存优化

#### 限制历史数据长度

只保留必要的历史数据：

```python
class MemoryEfficientStrategy(Strategy):
    warmup_period = 20  # 只需要 20 天数据

    def on_bar(self, context: Context) -> list[Signal]:
        # 只查询需要的数据量
        bars = context.query.get_bars(symbol, count=self.warmup_period)
```

#### 清理不需要的缓存

```python
def on_bar(self, context: Context) -> list[Signal]:
    # 处理完后清理缓存
    signals = self._generate_signals(context)

    # 清理旧的缓存数据
    if len(self.cache) > 1000:
        self.cache.clear()

    return signals
```

## 性能监控

### 添加性能日志

```python
import time
import structlog

logger = structlog.get_logger()

class MonitoredStrategy(Strategy):
    def on_bar(self, context: Context) -> list[Signal]:
        start_time = time.time()

        signals = self._generate_signals(context)

        duration = time.time() - start_time
        logger.debug(
            "策略执行时间",
            date=context.current_date,
            duration_ms=duration * 1000,
        )

        return signals
```

### 性能指标收集

```python
class PerformanceMetrics:
    def __init__(self):
        self.call_count = 0
        self.total_time = 0.0
        self.max_time = 0.0

    def record(self, duration: float):
        self.call_count += 1
        self.total_time += duration
        self.max_time = max(self.max_time, duration)

    def summary(self):
        avg_time = self.total_time / self.call_count if self.call_count > 0 else 0
        print(f"调用次数: {self.call_count}")
        print(f"总耗时: {self.total_time:.2f}s")
        print(f"平均耗时: {avg_time * 1000:.2f}ms")
        print(f"最大耗时: {self.max_time * 1000:.2f}ms")
```

## 常见性能问题

### 1. 数据加载慢

**症状：** 回测启动时间长，大部分时间在加载数据

**解决方案：**

- 使用数据缓存
- 预加载常用数据
- 使用更快的数据源（本地文件 vs 远程 API）

### 2. 策略计算慢

**症状：** 每个交易日处理时间长

**解决方案：**

- 缓存中间计算结果
- 使用向量化计算（NumPy）
- 减少循环和重复计算

### 3. 内存占用高

**症状：** 回测过程中内存持续增长

**解决方案：**

- 限制缓存大小
- 只保留必要的历史数据
- 定期清理不需要的对象

### 4. 并行效率低

**症状：** 并行回测速度提升不明显

**解决方案：**

- 确保每个任务足够重（避免进程创建开销）
- 避免共享状态（使用独立的数据源实例）
- 合理设置 worker 数量（通常等于 CPU 核心数）

## 性能优化检查清单

- [ ] 使用数据缓存
- [ ] 避免重复计算
- [ ] 减少数据查询次数
- [ ] 控制股票池大小
- [ ] 降低调仓频率
- [ ] 设置调仓阈值
- [ ] 限制历史数据长度
- [ ] 使用并行回测（多策略对比）
- [ ] 使用性能分析工具识别瓶颈
- [ ] 添加性能监控日志

## 下一步

- 运行基准测试建立基线：`uv run python benchmarks/performance_benchmark.py`
- 使用性能分析识别热点：`uv run python benchmarks/profile_engine.py`
- 应用优化建议并对比前后性能
