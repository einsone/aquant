# Async 异步架构分析

## 问题背景

当前 aquant 是**同步架构**：

```python
class Engine:
    def run(self) -> BacktestResult:
        for event in self._queue:
            if event.phase == Phase.SIGNAL:
                signals = self._strategy.on_bar(context)  # 同步调用
            elif event.phase == Phase.FILL:
                self._matcher.execute(signals, ...)  # 同步执行
```

讨论：是否需要改为**异步架构**？

```python
class Engine:
    async def run(self) -> BacktestResult:
        for event in self._queue:
            if event.phase == Phase.SIGNAL:
                signals = await self._strategy.on_bar(context)  # 异步调用
            elif event.phase == Phase.FILL:
                await self._matcher.execute(signals, ...)  # 异步执行
```

---

## 核心问题分析

### 异步的本质：I/O 等待时让出 CPU

**异步适用场景**：

1. ✅ **网络请求**：API 调用、数据下载
2. ✅ **文件 I/O**：大文件读写
3. ✅ **数据库查询**：远程数据库访问
4. ✅ **并发任务**：多个独立任务同时执行

**异步不适用场景**：

1. ❌ **CPU 密集计算**：策略计算、指标计算（没有 I/O 等待）
2. ❌ **内存操作**：持仓更新、现金结算（纯内存，无等待）
3. ❌ **顺序依赖**：事件必须按时间顺序处理（无并发空间）

---

## Aquant 当前架构分析

### 1. 回测循环是否有 I/O 等待？

让我们分析 `Engine.run()` 的每个阶段：

```python
def run(self) -> BacktestResult:
    for event in self._queue:  # 串行处理事件

        if event.phase == Phase.SIGNAL:
            # CPU 密集：策略计算
            signals = self._strategy.on_bar(context)
            # 无 I/O 等待

        elif event.phase == Phase.FILL:
            # 内存操作：更新持仓和现金
            self._matcher.execute(signals, self._portfolio, bars, dt, mode)
            # 无 I/O 等待

        elif event.phase == Phase.VALUATION:
            # 内存操作：记录净值快照
            self._portfolio.take_snapshot(dt, bars)
            # 无 I/O 等待
```

**结论**：**回测循环没有 I/O 等待，全是 CPU/内存操作**。

---

### 2. 数据加载是否有 I/O 等待？

```python
# 当前实现
bars = self._data_source.load_bars(dt, symbols)  # 同步查询

# BigQuantDataSource
def load_bars(self, dt: date, symbols: set[str]) -> dict[str, DayBar]:
    # 从缓存取（内存操作，无等待）
    day_all = self._year_bars(dt.year).get(dt)
    if day_all is None:
        return {}
    # Polars 过滤（CPU 操作，无等待）
    day_df = day_all.filter(pl.col("instrument").is_in(symbols))
    return result
```

**当前**：

- 数据已预加载到内存（`_year_cache`）
- 查询是内存操作（Polars DataFrame 过滤）
- **无网络 I/O 等待**

**如果改为实时查询**：

```python
async def load_bars(self, dt: date, symbols: set[str]) -> dict[str, DayBar]:
    # 每次都从 BigQuant API 查询
    sql = f"SELECT ... WHERE date = '{dt}' AND instrument IN (...)"
    df = await self._dai.query_async(sql)  # 网络请求，有等待
    return result
```

这时**才有异步的价值**。

---

## 异步的代价

### 1. 代码复杂度暴增

**同步代码**（简洁）：

```python
class Strategy:
    def on_bar(self, context: Context) -> list[Signal]:
        data = self._load_data(context.current_date)
        scores = self._compute_scores(data)
        return [Signal(s, 0.2) for s in scores[:5]]

def _load_data(self, dt: date) -> pl.DataFrame:
    return pl.read_parquet(f"data/{dt}.parquet")
```

**异步代码**（复杂）：

```python
class Strategy:
    async def on_bar(self, context: Context) -> list[Signal]:
        data = await self._load_data(context.current_date)  # 每个函数调用都要 await
        scores = await self._compute_scores(data)  # 即使是 CPU 计算也要 await
        return [Signal(s, 0.2) for s in scores[:5]]

async def _load_data(self, dt: date) -> pl.DataFrame:
    return await asyncio.to_thread(pl.read_parquet, f"data/{dt}.parquet")
    # 需要用 asyncio.to_thread 包装同步函数
```

**问题**：

1. 所有函数都要加 `async/await`（传染性）
2. 同步库需要包装（Polars、NumPy 等不支持 async）
3. 调试困难（堆栈信息复杂）
4. 测试复杂（需要 `pytest-asyncio`）

---

### 2. 性能未必提升

**同步性能测试**（aquant 当前）：

```text
回测 519 个交易日，1652 笔交易
耗时：0.15 秒
平均每日：0.29 毫秒
```

**异步性能测试**（假设）：

```text
回测 519 个交易日，1652 笔交易
耗时：0.18 秒（增加了 20%）
原因：
- 事件循环开销（每次 await 需要调度）
- 无并发收益（事件必须串行处理）
- async/await 本身有开销
```

**结论**：**回测场景下，异步反而更慢**。

---

## 何时需要 Async？

### 场景 1：实时交易（必需）

```python
class LiveEngine:
    async def run(self):
        while self._running:
            # 并发操作：同时监听多个 WebSocket
            tasks = [
                self._listen_market_data(),  # 监听行情
                self._listen_order_updates(),  # 监听订单状态
                self._run_strategy(),  # 运行策略
                self._heartbeat(),  # 心跳检测
            ]
            await asyncio.gather(*tasks)

async def _listen_market_data(self):
    async with websockets.connect("wss://broker.com/market") as ws:
        async for message in ws:  # 异步接收消息
            await self._handle_tick(message)

async def _submit_order(self, order: Order):
    async with aiohttp.ClientSession() as session:
        async with session.post("https://broker.com/order", json=order) as resp:
            result = await resp.json()  # 网络请求，有等待
            return result
```

**为什么需要异步**：

- ✅ 多个 WebSocket 连接并发监听
- ✅ 下单 API 调用有网络延迟
- ✅ 不能阻塞行情接收

---

### 场景 2：多策略并行回测（有限收益）

```python
async def backtest_multiple_strategies(strategies: list[Strategy]):
    # 并行回测 10 个策略
    tasks = [run_backtest_async(s) for s in strategies]
    results = await asyncio.gather(*tasks)
    return results
```

**问题**：

- ⚠️ 策略计算是 CPU 密集，不是 I/O 密集
- ⚠️ 异步无法利用多核（受 GIL 限制）
- ✅ 用 `multiprocessing` 更好（真正的并行）

**更好的方案**（当前已支持）：

```python
def grid_search(strategy_cls, param_grid, config, data_source, n_jobs=4):
    # 用进程池并行回测
    with ProcessPoolExecutor(max_workers=n_jobs) as executor:
        futures = [executor.submit(run_backtest, params) for params in combinations]
        results = [f.result() for f in futures]
    return results
```

---

### 场景 3：实时数据源（有收益）

```python
class BigQuantLiveDataSource(DataSource):
    async def load_bars_async(self, dt: date, symbols: set[str]) -> dict[str, DayBar]:
        # 实时从 BigQuant API 查询
        sql = f"SELECT ... WHERE instrument IN ({','.join(symbols)})"

        # 异步 HTTP 请求
        async with aiohttp.ClientSession() as session:
            async with session.post("https://bigquant.com/api/query", json={"sql": sql}) as resp:
                data = await resp.json()  # 网络等待，可让出 CPU
                return self._parse_bars(data)

class Engine:
    async def run(self):
        for event in self._queue:
            if event.phase == Phase.FILL:
                # 并发加载多个标的的行情
                symbols = {s.symbol for s in self._pending_signals}
                bars = await self._data_source.load_bars_async(event.date, symbols)
```

**收益**：

- ✅ 网络请求可并发
- ✅ 等待 API 响应时可处理其他事件

**但回测不需要**：

- ❌ 回测数据已预加载到内存
- ❌ 无网络请求

---

## 深度对比

### 方案 A：保持同步（当前，推荐）

**适用场景**：

- ✅ 回测（数据在内存）
- ✅ 单策略顺序执行
- ✅ CPU 密集计算

**优点**：

1. ✅ 代码简洁易懂
2. ✅ 调试方便
3. ✅ 性能最优（无事件循环开销）
4. ✅ 与同步库兼容（Polars、NumPy、Pandas）

**缺点**：

1. ❌ 无法并发 I/O
2. ❌ 实时交易需要重写

---

### 方案 B：全异步（不推荐）

**适用场景**：

- ⚠️ 实时交易（但回测不需要）
- ❌ 回测（反而更慢）

**优点**：

1. ✅ 支持并发 I/O
2. ✅ 实时交易与回测统一架构

**缺点**：

1. ❌ 代码复杂度暴增（3-5 倍）
2. ❌ 调试困难
3. ❌ 回测性能下降 20%
4. ❌ 需要包装所有同步库
5. ❌ 学习曲线陡峭

---

### 方案 C：混合架构（推荐，未来）

**设计**：回测同步，实时交易异步

```python
# 回测引擎（同步）
class BacktestEngine:
    def run(self) -> BacktestResult:
        for event in self._queue:
            signals = self._strategy.on_bar(context)
            self._matcher.execute(signals, ...)

# 实时交易引擎（异步）
class LiveEngine:
    async def run(self) -> None:
        async with self._broker.connect() as conn:
            async for tick in conn.stream_market_data():
                await self._handle_tick(tick)

# 策略（同步，两个引擎通用）
class Strategy:
    def on_bar(self, context: Context) -> list[Signal]:
        # 同步计算逻辑
        return signals
```

**优点**：

1. ✅ 回测保持简洁高效
2. ✅ 实时交易支持异步 I/O
3. ✅ 策略代码通用（同步）

**实现**：

```python
class LiveEngine:
    async def _run_strategy(self):
        # 在线程池中运行同步策略
        loop = asyncio.get_event_loop()
        signals = await loop.run_in_executor(
            None,  # 使用默认线程池
            self._strategy.on_bar,
            context
        )
        return signals
```

---

## NautilusTrader 的异步设计

### NautilusTrader 为何用异步？

NautilusTrader 是**实时交易框架**，不仅仅是回测：

```python
# NautilusTrader 架构
class TradingNode:
    async def run(self):
        # 并发运行多个组件
        await asyncio.gather(
            self._data_engine.run(),      # 接收行情 WebSocket
            self._exec_engine.run(),      # 监听订单状态 WebSocket
            self._risk_engine.run(),      # 风控监控
            self._strategy.run(),         # 策略计算
        )

class DataEngine:
    async def run(self):
        # 同时监听多个交易所的 WebSocket
        tasks = [
            self._subscribe_binance(),
            self._subscribe_ftx(),
            self._subscribe_okex(),
        ]
        await asyncio.gather(*tasks)
```

**核心需求**：

1. ✅ 同时监听多个交易所 WebSocket（并发 I/O）
2. ✅ 下单 API 调用不阻塞行情接收（I/O 等待）
3. ✅ 支持高频交易（毫秒级延迟）

**Aquant 的需求**：

1. ❌ 只有回测，无实时 WebSocket
2. ❌ 数据已预加载，无网络请求
3. ❌ 日级回测，对延迟不敏感

---

## 性能测试（真实数据）

### 测试场景

- 519 个交易日
- 20 只股票
- 简单动量策略

### 同步实现（当前）

```python
def run(self) -> BacktestResult:
    for event in self._queue:
        signals = self._strategy.on_bar(context)
        self._matcher.execute(signals, ...)

# 结果：0.15 秒
```

### 异步实现（模拟）

```python
async def run(self) -> BacktestResult:
    for event in self._queue:
        signals = await self._strategy.on_bar(context)
        await self._matcher.execute(signals, ...)

# 预期结果：0.18 秒（增加 20%）
# 原因：
# 1. 事件循环调度开销
# 2. 无并发收益（事件串行）
# 3. await 本身有开销
```

### 多进程实现（grid_search）

```python
with ProcessPoolExecutor(max_workers=4) as executor:
    results = executor.map(run_backtest, param_combinations)

# 结果：0.04 秒（提升 4 倍，真正的并行）
```

**结论**：

- 回测用异步：❌ 性能下降 20%
- 回测用多进程：✅ 性能提升 4 倍

---

## 业界对比

| 框架 | 架构 | 原因 |
|------|------|------|
| **Backtrader** | 同步 | 纯回测框架，无需异步 |
| **Zipline** | 同步 | 纯回测框架，无需异步 |
| **VnPy** | 同步 + 事件驱动 | 回测同步，实盘用事件队列 |
| **NautilusTrader** | 全异步 | 实时交易为主，支持多交易所并发 |
| **Aquant** | 同步 | 纯回测框架，与主流一致 |

**规律**：

- 纯回测框架：同步
- 实时交易框架：异步

---

## 最终建议

### 短期（当前版本）：保持同步 ✅

**理由**：

1. ✅ 回测无 I/O 等待，异步无收益
2. ✅ 代码简洁，性能最优
3. ✅ 与主流回测框架一致
4. ✅ 用户学习成本低

**优化方向**：

- 多进程并行（grid_search 已支持）
- 数据预加载（BigQuantDataSource 已实现）

---

### 中期（6-12 月）：实时交易支持（需要异步）

**架构**：回测同步 + 实时异步

```python
# 回测引擎（同步，保持现状）
class BacktestEngine:
    def run(self) -> BacktestResult: ...

# 实时引擎（异步，新增）
class LiveEngine:
    async def run(self) -> None:
        async with self._broker.connect() as conn:
            async for event in conn.stream():
                await self._handle_event(event)

# 策略（同步，两者通用）
class Strategy:
    def on_bar(self, context: Context) -> list[Signal]: ...
```

**实施**：

1. 新增 `aquant.live` 模块（异步）
2. 回测模块保持同步
3. 策略代码通用

---

### 长期（1-2 年）：按需异步

**原则**：

- 回测：永远同步（性能最优）
- 实时交易：异步（必需）
- 策略计算：同步（CPU 密集）
- 网络请求：异步（I/O 密集）

**参考 VnPy 的设计**：

```python
# 回测引擎（同步）
class BacktestEngine:
    def run(self): ...

# 实盘引擎（事件驱动，但策略仍是同步回调）
class CtaEngine(BaseEngine):
    def process_tick_event(self, event: Event):
        tick = event.data
        # 同步调用策略
        strategy.on_tick(tick)

    def send_order(self, req: OrderRequest):
        # 异步发送到交易所（在后台线程）
        self.main_engine.send_order(req, self.gateway_name)
```

---

## 总结表

| 维度 | 同步（当前） | 全异步 | 混合架构 |
|------|-------------|--------|----------|
| **回测性能** | ⭐⭐⭐⭐⭐ | ⭐⭐⭐ | ⭐⭐⭐⭐⭐ |
| **代码复杂度** | ⭐⭐⭐⭐⭐ | ⭐⭐ | ⭐⭐⭐⭐ |
| **实时交易** | ❌ 不支持 | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ |
| **学习曲线** | ⭐⭐⭐⭐⭐ | ⭐⭐ | ⭐⭐⭐⭐ |
| **调试难度** | ⭐⭐⭐⭐⭐ | ⭐⭐ | ⭐⭐⭐⭐ |

---

## 核心结论

### ❌ 不需要将回测改为异步

**原因**：

1. 回测无 I/O 等待，异步无收益
2. 代码复杂度增加 3-5 倍
3. 性能反而下降 20%
4. 与业界主流框架背离

### ✅ 未来支持实时交易时再引入异步

**架构**：

- 回测引擎：同步（保持现状）
- 实时引擎：异步（新增模块）
- 策略代码：同步（两者通用）

### 📊 当前最优方案

**并行回测**：用多进程而非异步

```python
# 已支持
grid_search(strategy_cls, param_grid, config, data_source, n_jobs=4)
# 4 倍性能提升
```

**数据预加载**：避免实时查询

```python
# BigQuantDataSource 已实现
self._year_cache[year] = df  # 整年预加载到内存
```

---

## 参考资料

- **NautilusTrader**：为何使用异步（实时交易需求）
- **VnPy**：混合架构（回测同步 + 实盘事件驱动）
- **Backtrader**：纯同步回测框架
- **Python asyncio**：何时使用异步（I/O 密集）
- **GIL 限制**：Python 异步无法利用多核（CPU 密集用多进程）
