# Aquant 架构深度优化建议

## 当前架构评估

### 优点
1. ✅ **职责分离清晰**：Engine、Strategy、Portfolio、Matcher 各司其职
2. ✅ **事件驱动基础**：已引入消息总线，支持松耦合通信
3. ✅ **类型安全**：完整的类型注解，ty 类型检查通过
4. ✅ **轻量简洁**：~2800 行代码，学习曲线平缓

### 当前限制与改进空间

---

## 一、领域模型改进（DDD 视角）

### 问题 1：Portfolio 职责过重
**当前**：`Portfolio` 同时负责：
- 持仓管理（Position CRUD）
- 现金管理（cash 增减）
- 交易结算（apply_fill）
- 估值快照（take_snapshot）
- 历史记录（trade_log、_daily_nav）

**改进方案**：领域驱动设计（DDD）拆分

```python
# 核心领域对象
class Position:
    """持仓聚合根"""
    def adjust_shares(self, delta: int) -> None: ...
    def update_cost_basis(self, price: float, shares: int, commission: float) -> None: ...
    def mark_to_market(self, price: float) -> None: ...

class Account:
    """账户聚合根（管理现金）"""
    def deposit(self, amount: float) -> None: ...
    def withdraw(self, amount: float) -> None: ...
    @property
    def available_cash(self) -> float: ...

class Portfolio:
    """组合聚合根（协调持仓和账户）"""
    def __init__(self, account: Account):
        self._account = account
        self._positions: dict[str, Position] = {}
        self._position_repository = PositionRepository()

    def execute_trade(self, trade: Trade) -> None:
        """业务逻辑：执行交易并更新持仓/账户"""
        if trade.side == "buy":
            self._account.withdraw(trade.total_cost)
            self._add_position(trade)
        else:
            self._account.deposit(trade.total_proceeds)
            self._reduce_position(trade)

class PortfolioRepository:
    """持久化接口（从 Portfolio 分离历史记录）"""
    def save_snapshot(self, snapshot: NavRecord) -> None: ...
    def get_snapshots(self, start: date, end: date) -> list[NavRecord]: ...
    def save_trade(self, trade: Trade) -> None: ...
    def get_trades(self) -> list[Trade]: ...
```

**优势**：
- 单一职责：Position 管理持仓，Account 管理现金，Portfolio 协调业务逻辑
- 可测试性：每个聚合根可独立单元测试
- 可扩展性：Repository 模式支持切换存储（内存、数据库）

---

### 问题 2：Context 过于简单，缺少查询能力

**当前**：策略只能访问 `Context.positions`、`Context.cash`，无法：
- 查询历史持仓变化
- 查询近期成交记录
- 查询组合净值曲线

**改进方案**：Query Service 模式

```python
class PortfolioQueryService:
    """组合查询服务（只读）"""

    def __init__(self, repository: PortfolioRepository):
        self._repo = repository

    def get_nav_curve(self, start: date, end: date) -> pl.DataFrame:
        """查询净值曲线"""
        snapshots = self._repo.get_snapshots(start, end)
        return pl.DataFrame([{"date": s.date, "nav": s.total} for s in snapshots])

    def get_recent_trades(self, symbol: str, n: int = 10) -> list[Trade]:
        """查询最近 N 笔成交"""
        return self._repo.get_trades(symbol=symbol, limit=n)

    def get_position_history(self, symbol: str) -> pl.DataFrame:
        """查询持仓历史"""
        ...

class Context:
    """增强的上下文对象"""
    current_date: date
    positions: dict[str, PositionView]
    cash: float
    total_value: float

    # 新增：查询服务
    query: PortfolioQueryService  # 策略可调用 context.query.get_nav_curve()
```

**优势**：
- 策略可以访问历史数据做更复杂的决策
- 查询与命令分离（CQRS 模式）
- 便于添加缓存优化

---

## 二、事件系统深化

### 问题 3：事件缺少溯源能力

**当前**：事件发布后立即处理，无法：
- 重放历史事件
- 调试时单步执行
- 持久化事件流

**改进方案**：Event Sourcing（事件溯源）

```python
class EventStore:
    """事件存储"""
    def append(self, event: Event) -> None:
        """追加事件到存储"""
        self._events.append(event)
        self._persist(event)  # 可选：持久化到磁盘/数据库

    def replay(self, from_date: date | None = None) -> Iterator[Event]:
        """重放事件"""
        for event in self._events:
            if from_date is None or event.date >= from_date:
                yield event

class Engine:
    def __init__(self, ..., event_store: EventStore | None = None):
        self._event_store = event_store or EventStore()
        self._bus = MessageBus()

    def run(self) -> BacktestResult:
        for event in self._queue:
            # 先存储再发布
            self._event_store.append(event)
            self._bus.publish(self._topic_for(event), event)
```

**优势**：
- **调试**：可从任意时间点重放
- **审计**：完整的事件日志
- **分布式**：事件流可分发到多个 Worker

---

### 问题 4：消息总线缺少错误处理

**当前**：订阅者抛异常会中断整个回测

**改进方案**：容错机制

```python
class MessageBus:
    def __init__(self, error_handler: Callable[[Exception, Event], None] | None = None):
        self._error_handler = error_handler or self._default_error_handler

    def publish(self, topic: str, event: Event) -> None:
        for handler in self._handlers.get(topic, []):
            try:
                handler(event)
            except Exception as e:
                self._error_handler(e, event)

    def _default_error_handler(self, error: Exception, event: Event) -> None:
        logger.error("事件处理器异常", error=str(error), event=event)
        # 可选：发布 ErrorEvent，让监控系统捕获
```

**优势**：
- 单个监听器异常不影响其他监听器
- 便于集成外部监控系统

---

## 三、性能优化

### 问题 5：数据访问效率低

**当前**：
- `BigQuantDataSource.load_bars()` 每次查询单日数据
- 策略需要多日数据时，循环调用 `load_bars()`，产生大量小查询

**改进方案**：批量加载 + 时间窗口缓存

```python
class DataManager:
    def __init__(self, source: DataSource):
        self._source = source
        self._window_cache: dict[str, pl.DataFrame] = {}  # symbol -> 滚动窗口数据

    def load_bars_window(self, symbol: str, end_date: date, window: int) -> pl.DataFrame:
        """加载滚动窗口数据（如最近 20 日）"""
        cache_key = f"{symbol}:{end_date}"
        if cache_key in self._window_cache:
            return self._window_cache[cache_key]

        # 批量加载 window 日数据
        start_date = end_date - timedelta(days=window * 2)  # 考虑节假日
        calendar = self._source.load_calendar(start_date, end_date)

        bars = []
        for dt in calendar[-window:]:
            bar = self._source.load_bars(dt, {symbol}).get(symbol)
            if bar:
                bars.append(bar)

        df = pl.DataFrame(bars)
        self._window_cache[cache_key] = df
        return df
```

**优势**：
- 减少查询次数
- 适合技术指标计算（均线、动量等需要历史数据）

---

### 问题 6：策略计算无法并行

**当前**：`Engine.run()` 串行执行所有事件

**改进方案**：Actor 模型（借鉴 NautilusTrader）

```python
class StrategyActor:
    """策略 Actor，独立线程运行"""
    def __init__(self, strategy: Strategy, input_queue: Queue, output_queue: Queue):
        self._strategy = strategy
        self._input = input_queue
        self._output = output_queue

    def run(self) -> None:
        while True:
            event = self._input.get()
            if isinstance(event, SignalEvent):
                signals = self._strategy.on_bar(self._build_context(event))
                self._output.put(signals)

class Engine:
    def __init__(self, strategies: list[Strategy], ...):
        # 每个策略一个 Actor
        self._actors = [StrategyActor(s, Queue(), Queue()) for s in strategies]

    def run(self) -> BacktestResult:
        # 启动所有 Actor 线程
        threads = [Thread(target=actor.run) for actor in self._actors]
        for t in threads:
            t.start()

        # 主线程分发事件
        for event in self._queue:
            for actor in self._actors:
                actor.input_queue.put(event)
```

**优势**：
- 多策略并行计算
- 适合 CPU 密集型策略（机器学习推理）

**注意**：需要解决状态同步问题（Portfolio 是共享状态）

---

## 四、扩展性增强

### 问题 7：难以支持多品种（期货、期权）

**当前**：代码假设股票交易规则（T+1、印花税、涨跌停）

**改进方案**：交易规则抽象

```python
class TradingRules(ABC):
    """交易规则抽象"""
    @abstractmethod
    def can_trade_today(self, symbol: str, position: Position | None) -> bool:
        """是否可交易（T+1 规则、锁定期等）"""

    @abstractmethod
    def compute_cost(self, side: str, value: float) -> tuple[float, float]:
        """计算成本（佣金、印花税、手续费）"""

    @abstractmethod
    def get_lot_size(self, symbol: str) -> int:
        """最小交易单位（股票 100 股，期货 1 手）"""

class StockRules(TradingRules):
    """A 股交易规则"""
    def can_trade_today(self, symbol: str, position: Position | None) -> bool:
        if position is None:
            return True
        return position.tradeable_shares > 0  # T+1

    def compute_cost(self, side: str, value: float) -> tuple[float, float]:
        commission = max(value * 0.0003, 5.0)
        stamp_duty = value * 0.001 if side == "sell" else 0.0
        return commission, stamp_duty

    def get_lot_size(self, symbol: str) -> int:
        return 100

class FuturesRules(TradingRules):
    """期货交易规则"""
    def can_trade_today(self, symbol: str, position: Position | None) -> bool:
        return True  # 期货 T+0

    def compute_cost(self, side: str, value: float) -> tuple[float, float]:
        # 期货按合约收取手续费
        return value * 0.00005, 0.0

    def get_lot_size(self, symbol: str) -> int:
        return 1  # 1 手

class Matcher:
    def __init__(self, rules: TradingRules, ...):
        self._rules = rules

    def execute(self, signals, portfolio, bars, dt, mode) -> None:
        for signal in signals:
            if not self._rules.can_trade_today(signal.symbol, portfolio.positions.get(signal.symbol)):
                continue

            lot_size = self._rules.get_lot_size(signal.symbol)
            target_shares = round(target_value / price / lot_size) * lot_size
            # ...
```

**优势**：
- 支持多品种无需修改核心代码
- 用户自定义交易规则

---

### 问题 8：缺少风控层

**当前**：只有 Guard 做订单级别检查，无组合级别风控

**改进方案**：分层风控

```python
class RiskManager:
    """组合级风控管理器"""

    def __init__(self, rules: list[RiskRule]):
        self._rules = rules

    def check_signals(self, signals: list[Signal], portfolio: Portfolio, context: Context) -> list[Signal]:
        """检查信号是否违反风控规则"""
        approved = []
        for signal in signals:
            if all(rule.check(signal, portfolio, context) for rule in self._rules):
                approved.append(signal)
            else:
                logger.warning("信号被风控拦截", symbol=signal.symbol, weight=signal.weight)
        return approved

class RiskRule(ABC):
    """风控规则抽象"""
    @abstractmethod
    def check(self, signal: Signal, portfolio: Portfolio, context: Context) -> bool: ...

class MaxPositionSizeRule(RiskRule):
    """单标的持仓上限"""
    def __init__(self, max_ratio: float = 0.2):
        self._max_ratio = max_ratio

    def check(self, signal: Signal, portfolio: Portfolio, context: Context) -> bool:
        return signal.weight <= self._max_ratio

class MaxDrawdownRule(RiskRule):
    """最大回撤限制"""
    def __init__(self, max_dd: float = 0.2):
        self._max_dd = max_dd

    def check(self, signal: Signal, portfolio: Portfolio, context: Context) -> bool:
        # 查询当前回撤
        peak = context.query.get_peak_nav()
        current_dd = (peak - context.total_value) / peak
        return current_dd < self._max_dd

class Engine:
    def __init__(self, strategy, data_source, config, risk_manager: RiskManager | None = None):
        self._risk_manager = risk_manager or RiskManager([])

    def run(self) -> BacktestResult:
        # ...
        if event.phase == Phase.SIGNAL:
            raw_signals = self._strategy.on_bar(context)
            # 风控过滤
            approved_signals = self._risk_manager.check_signals(raw_signals, self._portfolio, context)
            self._pending_signals = approved_signals
```

**优势**：
- 组合级风控（最大回撤、杠杆率、集中度）
- 可插拔规则
- 真实交易时复用相同风控逻辑

---

## 五、可观测性增强

### 问题 9：难以分析性能瓶颈

**改进方案**：分布式追踪（类似 OpenTelemetry）

```python
class Tracer:
    """性能追踪器"""
    def __init__(self):
        self._spans: list[Span] = []

    @contextmanager
    def span(self, name: str):
        start = time.perf_counter()
        yield
        elapsed = time.perf_counter() - start
        self._spans.append(Span(name=name, duration_ms=elapsed * 1000))

    def report(self) -> pl.DataFrame:
        return pl.DataFrame(self._spans).group_by("name").agg([
            pl.col("duration_ms").mean().alias("avg_ms"),
            pl.col("duration_ms").max().alias("max_ms"),
            pl.len().alias("count"),
        ])

class Engine:
    def __init__(self, ..., tracer: Tracer | None = None):
        self._tracer = tracer or Tracer()

    def run(self) -> BacktestResult:
        for event in self._queue:
            with self._tracer.span(f"phase_{event.phase.name}"):
                # ... 处理事件
                pass

        # 输出性能报告
        print(self._tracer.report())
```

**输出示例**：
```
┌─────────────────┬────────┬────────┬───────┐
│ name            │ avg_ms │ max_ms │ count │
├─────────────────┼────────┼────────┼───────┤
│ phase_SIGNAL    │ 12.5   │ 45.2   │ 519   │
│ phase_FILL      │ 8.3    │ 32.1   │ 519   │
│ phase_VALUATION │ 3.2    │ 15.6   │ 519   │
└─────────────────┴────────┴────────┴───────┘
```

---

## 六、架构模式建议

### 推荐的最终架构：六边形架构（Hexagonal Architecture）

```
              ┌──────────────────────────┐
              │   Application Core       │
              │  (Domain Logic)          │
              │                          │
              │  Portfolio, Account,     │
              │  Position, Strategy      │
              └────────┬─────────────────┘
                       │
        ┌──────────────┼──────────────┐
        │              │              │
   ┌────▼────┐   ┌────▼────┐   ┌────▼────┐
   │ Adapters│   │ Adapters│   │ Adapters│
   │ (Ports) │   │ (Ports) │   │ (Ports) │
   └────┬────┘   └────┬────┘   └────┬────┘
        │              │              │
   ┌────▼────┐   ┌────▼────┐   ┌────▼────┐
   │BigQuant │   │ Local   │   │ Message │
   │   DAI   │   │  File   │   │  Queue  │
   └─────────┘   └─────────┘   └─────────┘
```

**核心思想**：
- **Domain Core**（内层）：纯业务逻辑，不依赖外部
- **Ports**（接口）：定义与外部交互的契约
- **Adapters**（外层）：实现具体的数据源、消息队列等

**优势**：
- 核心逻辑可独立测试（不依赖数据库）
- 轻松切换数据源（BigQuant → DuckDB → ClickHouse）
- 支持实时与回测共享核心逻辑

---

## 七、优先级建议

### 立即可做（高 ROI，低成本）
1. ✅ **容错消息总线**（问题 4）：2 小时，提升稳定性
2. ✅ **Query Service**（问题 2）：4 小时，策略能力提升 50%
3. ✅ **TradingRules 抽象**（问题 7）：6 小时，支持期货/期权
4. ✅ **RiskManager 风控层**（问题 8）：8 小时，真实交易必备

### 中期重构（1-2 周）
5. **DDD 拆分 Portfolio**（问题 1）：需要大量测试确保兼容性
6. **Event Sourcing**（问题 3）：需要设计存储格式
7. **DataManager 窗口缓存**（问题 5）：需要测试性能提升

### 长期演进（1-3 月）
8. **Actor 模型并行**（问题 6）：架构变动大，需要重新设计状态管理
9. **六边形架构重构**：适合 2.0 大版本

---

## 八、总结

### 当前架构评分（1-10）
- **正确性**：9/10（逻辑严谨，测试通过）
- **性能**：7/10（串行执行，有优化空间）
- **扩展性**：7/10（消息总线已引入，但领域模型仍紧耦合）
- **可维护性**：8/10（代码清晰，但 Portfolio 职责偏重）
- **可观测性**：6/10（缺少性能分析工具）

### 优化后预期提升
- **扩展性**：7/10 → **9/10**（支持多品种、风控可插拔）
- **性能**：7/10 → **8.5/10**（批量加载、并行策略）
- **可维护性**：8/10 → **9/10**（DDD 拆分，职责清晰）
- **可观测性**：6/10 → **9/10**（事件溯源、性能追踪）

### 最关键的三个改进
1. **Query Service**：让策略能访问历史数据，解锁高级策略
2. **TradingRules 抽象**：支持多品种，拓展用户群
3. **RiskManager**：真实交易的护城河

---

## 参考资料

- **领域驱动设计**：Eric Evans - Domain-Driven Design
- **事件溯源**：Martin Fowler - Event Sourcing Pattern
- **六边形架构**：Alistair Cockburn - Hexagonal Architecture
- **CQRS**：Greg Young - CQRS Pattern
- **NautilusTrader**：Actor 模型在量化交易中的应用
- **Backtrader**：多品种交易框架设计
