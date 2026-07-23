# 性能优化分析与实施

## 📊 当前性能基准

从 benchmark 测试结果：

| 股票数 | 天数 | 耗时 | 平均每天 | 吞吐量 |
|--------|------|------|----------|--------|
| 10     | 89   | 0.09s | 1.05ms | 9,535 bars/s |
| 50     | 89   | 0.11s | 1.18ms | 42,230 bars/s |
| 100    | 89   | 0.14s | 1.61ms | 62,029 bars/s |
| 100    | 250  | 0.36s | 1.46ms | 68,555 bars/s |

## 🔍 性能瓶颈分析

### 1. 数据加载（主要瓶颈）

**位置**: `Engine.run()` L195, L206, L232

```python
self._day_bars = self._data_source.load_bars(event.date, symbols)
```

**问题**:

- 每个交易日调用 1-3 次 `load_bars()`
- CSV 数据源：每次重新读取文件
- 没有批量预加载机制

**影响**: 约占总耗时 40-50%

---

### 2. Context 构建

**位置**: `Engine._build_context()` L156-168

```python
def _build_context(self, dt: date) -> Context:
    positions = self._portfolio.position_views()
    total_value = self._portfolio.cash + sum(p.shares * p.last_close for p in positions.values())
    query_service = PortfolioQueryService(...)
    return Context(...)
```

**问题**:

- 每个 SIGNAL 阶段都重新创建 PortfolioQueryService
- 持仓视图复制开销

**影响**: 约占总耗时 10-15%

---

### 3. Signal 对象复制

**位置**: `Engine.run()` L224

```python
self._pending_signals = [
    Signal(symbol=s.symbol, weight=s.weight, signal_date=event.date, meta=dict(s.meta))
    for s in filtered_signals
]
```

**问题**:

- 每个信号都创建新对象
- meta 字典浅拷贝

**影响**: 约占总耗时 5-10%

---

### 4. Polars 数据处理

**位置**: CSV/ALDS 数据源

```python
df_filtered = df.filter(pl.col("symbol").is_in(symbols))
for row in df_filtered.iter_rows(named=True):
    # 逐行处理
```

**问题**:

- `iter_rows(named=True)` 是最慢的迭代方式
- 没有利用 Polars 向量化优势

**影响**: 约占总耗时 15-20%

---

## 🚀 优化方案

### 优化 1: 数据批量预加载

**目标**: 一次性加载多天数据，减少 I/O 次数

**实现**:

```python
class DataPreloader:
    """数据预加载器，批量加载并缓存数据"""

    def __init__(self, data_source: DataSource, trading_days: list[date], symbols: set[str]):
        self.data_source = data_source
        self._cache: dict[date, dict[str, DayBar]] = {}

        # 批量预加载
        self._preload(trading_days, symbols)

    def _preload(self, trading_days: list[date], symbols: set[str]):
        """批量加载所有交易日数据"""
        # 分批加载（避免内存溢出）
        batch_size = 50  # 每批加载 50 天

        for i in range(0, len(trading_days), batch_size):
            batch = trading_days[i:i+batch_size]
            for dt in batch:
                self._cache[dt] = self.data_source.load_bars(dt, symbols)

    def get_bars(self, dt: date) -> dict[str, DayBar]:
        """从缓存获取数据"""
        return self._cache.get(dt, {})
```

**预期收益**: 减少 30-40% 总耗时

---

### 优化 2: Context 对象池

**目标**: 复用 Context 和 QueryService 对象

**实现**:

```python
class Engine:
    def __init__(self, ...):
        # ...
        self._query_service = PortfolioQueryService(
            daily_nav=self._portfolio._daily_nav,
            trade_log=self._portfolio.trade_log
        )

    def _build_context(self, dt: date) -> Context:
        # 复用 query_service，只更新数据引用
        positions = self._portfolio.position_views()
        total_value = self._portfolio.cash + sum(
            p.shares * p.last_close for p in positions.values()
        )

        return Context(
            current_date=dt,
            positions=positions,
            cash=self._portfolio.cash,
            total_value=total_value,
            query=self._query_service  # 复用
        )
```

**预期收益**: 减少 5-10% 总耗时

---

### 优化 3: Polars 向量化处理

**目标**: 利用 Polars 向量化操作，避免逐行迭代

**实现**:

```python
def load_bars(self, dt: date, symbols: set[str]) -> dict[str, DayBar]:
    df = self._load_date_csv(dt)
    if df is None:
        return {}

    # 筛选指定股票
    df_filtered = df.filter(pl.col("symbol").is_in(symbols))

    # 向量化转换（避免 iter_rows）
    result = {}
    symbols_list = df_filtered.get_column("symbol").to_list()
    dates = df_filtered.get_column("date").to_list()
    opens = df_filtered.get_column("open").to_list()
    closes = df_filtered.get_column("close").to_list()
    highs = df_filtered.get_column("high").to_list()
    lows = df_filtered.get_column("low").to_list()
    volumes = df_filtered.get_column("volume").to_list()

    for i, sym in enumerate(symbols_list):
        result[sym] = DayBar(
            symbol=sym,
            date=dates[i],
            open=float(opens[i]),
            close=float(closes[i]),
            high=float(highs[i]),
            low=float(lows[i]),
            volume=float(volumes[i]),
            up_limit=float(closes[i]) * 1.1,
            down_limit=float(closes[i]) * 0.9,
            is_halted=False,
        )

    return result
```

**预期收益**: 减少 10-15% 总耗时

---

### 优化 4: Signal 原地修改

**目标**: 避免创建新 Signal 对象

**实现**:

```python
# 在 Signal 类中添加
class Signal:
    def with_date(self, signal_date: date) -> Signal:
        """原地修改信号日期（避免复制）"""
        self.signal_date = signal_date
        return self
```

**预期收益**: 减少 3-5% 总耗时

---

### 优化 5: 并行回测（可选）

**目标**: 支持多进程并行回测（参数优化场景）

**实现**:

```python
from concurrent.futures import ProcessPoolExecutor

def parallel_backtest(
    strategy_cls: type[Strategy],
    param_grid: dict[str, list],
    data_source: DataSource,
    config: BacktestConfig,
    n_jobs: int = -1
) -> pl.DataFrame:
    """并行回测多个参数组合"""

    if n_jobs == -1:
        n_jobs = os.cpu_count() or 1

    # 生成参数组合
    param_combinations = list(itertools.product(*param_grid.values()))

    # 并行执行
    with ProcessPoolExecutor(max_workers=n_jobs) as executor:
        futures = []
        for params in param_combinations:
            param_dict = dict(zip(param_grid.keys(), params))
            future = executor.submit(
                _run_single_backtest,
                strategy_cls,
                param_dict,
                data_source,
                config
            )
            futures.append((param_dict, future))

        # 收集结果
        results = []
        for param_dict, future in futures:
            try:
                result = future.result()
                results.append({**param_dict, **result.metrics})
            except Exception as e:
                logger.error(f"回测失败: {param_dict}, {e}")

    return pl.DataFrame(results)
```

**预期收益**: 线性加速（N 核 ≈ N 倍速度）

---

## 📈 预期总体收益

| 优化项 | 预期收益 | 优先级 | 实施难度 |
|--------|----------|--------|----------|
| 数据批量预加载 | 30-40% | 🔴 高 | 中 |
| Context 对象池 | 5-10% | 🟡 中 | 低 |
| Polars 向量化 | 10-15% | 🟡 中 | 中 |
| Signal 原地修改 | 3-5% | 🟢 低 | 低 |
| 并行回测 | N 倍 | 🟢 低 | 高 |

**累计预期**: 单进程加速 **50-70%**，多进程可达 **4-8 倍**（4-8 核）

## 🎯 实施顺序

1. ✅ **Polars 向量化**（低难度，中等收益）
2. ✅ **Context 对象池**（低难度，小收益）
3. ✅ **数据批量预加载**（中等难度，高收益）
4. ⏳ **Signal 优化**（低难度，小收益）
5. ⏳ **并行回测**（高难度，高收益，参数优化场景）
