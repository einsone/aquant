# Aquant 重构方案

## 当前架构分析

### 优点
1. **事件驱动核心清晰**：`EventQueue` + `Phase` 枚举实现了良好的事件循环
2. **职责分离明确**：
   - `DataSource` 抽象接口与具体实现分离
   - `Strategy` 抽象基类定义了策略协议
   - `Portfolio` 管理持仓状态
   - `Matcher` 处理撮合逻辑
3. **代码质量高**：类型注解完整，注释清晰，符合 PEP 8
4. **可测试性好**：合成数据示例（demo.py）证明了架构的可测试性

### 主要问题

1. **耦合过紧**：
   - `Engine._strategy` 直接持有策略引用，策略通过 `context` 获取状态
   - `Matcher` 内部硬编码了所有 `Guard`，无法在运行时配置
   - `BigQuantDataSource._attach_source()` 需要手动注入，破坏封装

2. **缺少消息总线**：
   - 事件只用于控制流程，不用于组件通信
   - 组件间通过直接方法调用通信（紧耦合）
   - 难以添加监听器（日志、性能分析、实时监控）

3. **数据访问层单薄**：
   - `DataSource` 接口过于简单，缺少缓存、预加载等高级功能
   - `BigQuantDataSource` 的 `_year_cache` 是临时方案，缺少统一的缓存策略
   - 没有数据管理器层协调多数据源

4. **扩展性受限**：
   - 难以添加新的事件类型（需要修改 `Phase` 枚举和 `Engine.run()` 的 if-elif 链）
   - 难以插入自定义逻辑（例如风控、止损、实时通知）
   - `Strategy` 只能通过 `Context` 被动获取数据，无法主动订阅事件

---

## 重构目标

### 1. 引入消息总线（借鉴 NautilusTrader）
- 所有组件通过消息总线通信
- 事件发布-订阅模式解耦
- 便于添加监听器和插件

### 2. 分层数据访问（借鉴 VnPy）
- **接口层**：`DataSource` 保持不变
- **管理层**：新增 `DataManager` 协调缓存、预加载、多源聚合
- **缓存层**：统一缓存策略（LRU、TTL）

### 3. 可配置的撮合引擎
- `Guard` 可插拔配置
- 支持自定义订单类型
- 支持优先级队列

### 4. 事件系统增强
- 从 "控制流事件" 升级为 "业务事件"
- 支持更多事件类型（订单提交、成交、持仓变动等）
- 事件携带完整上下文

---

## 重构方案（分阶段）

## 阶段 1：引入消息总线（核心重构）

### 1.1 新增 `MessageBus`

**文件**：`aquant/events/bus.py`

```python
from __future__ import annotations

from collections import defaultdict
from typing import TYPE_CHECKING, Callable


if TYPE_CHECKING:
    from aquant.events.event import Event


class MessageBus:
    """轻量级消息总线，实现发布-订阅模式。

    所有组件通过总线通信，实现松耦合。
    支持通配符订阅（例如 "order.*" 匹配所有订单事件）。
    """

    def __init__(self) -> None:
        # topic -> [handlers]
        self._handlers: dict[str, list[Callable[[Event], None]]] = defaultdict(list)
        # 通配符订阅，例如 "order.*"
        self._wildcard_handlers: dict[str, list[Callable[[Event], None]]] = defaultdict(list)

    def subscribe(self, topic: str, handler: Callable[[Event], None]) -> None:
        """订阅指定主题。

        支持通配符：
        - "order.*" 匹配所有以 "order." 开头的主题
        - "*" 匹配所有主题
        """
        if topic.endswith(".*"):
            prefix = topic[:-2]
            self._wildcard_handlers[prefix].append(handler)
        elif topic == "*":
            self._wildcard_handlers[""].append(handler)
        else:
            self._handlers[topic].append(handler)

    def publish(self, topic: str, event: Event) -> None:
        """发布事件到指定主题。"""
        # 精确匹配
        for handler in self._handlers.get(topic, []):
            handler(event)

        # 通配符匹配
        for prefix, handlers in self._wildcard_handlers.items():
            if not prefix or topic.startswith(prefix + "."):
                for handler in handlers:
                    handler(event)

    def unsubscribe(self, topic: str, handler: Callable[[Event], None]) -> None:
        """取消订阅。"""
        if topic.endswith(".*"):
            prefix = topic[:-2]
            if handler in self._wildcard_handlers[prefix]:
                self._wildcard_handlers[prefix].remove(handler)
        else:
            if handler in self._handlers[topic]:
                self._handlers[topic].remove(handler)
```

### 1.2 扩展事件类型

**文件**：`aquant/events/event.py`（扩展现有）

```python
# 在现有事件基础上新增业务事件

@dataclass
class OrderSubmittedEvent(Event):
    """订单提交事件。"""
    symbol: str
    side: str
    shares: int
    phase: Phase = field(default=Phase.FILL, init=False)


@dataclass
class OrderFilledEvent(Event):
    """订单成交事件。"""
    symbol: str
    side: str
    shares: int
    fill_price: float
    commission: float
    stamp_duty: float
    phase: Phase = field(default=Phase.FILL, init=False)


@dataclass
class PositionChangedEvent(Event):
    """持仓变动事件。"""
    symbol: str
    old_shares: int
    new_shares: int
    phase: Phase = field(default=Phase.FILL, init=False)


@dataclass
class PortfolioValuationEvent(Event):
    """组合估值事件（每日收盘）。"""
    total_value: float
    cash: float
    position_count: int
    phase: Phase = field(default=Phase.VALUATION, init=False)
```

### 1.3 改造 `Engine` 集成消息总线

**文件**：`aquant/core/engine.py`（部分修改）

```python
class Engine:
    def __init__(self, strategy: Strategy, data_source: DataSource, config: BacktestConfig) -> None:
        # ... 现有代码 ...

        # 新增：消息总线
        self._bus = MessageBus()

        # 注册内部监听器
        self._bus.subscribe("order.filled", self._on_order_filled)
        self._bus.subscribe("portfolio.valuation", self._on_portfolio_valuation)

        # 可选：让策略订阅事件
        if hasattr(strategy, "setup_subscriptions"):
            strategy.setup_subscriptions(self._bus)

    def _on_order_filled(self, event: OrderFilledEvent) -> None:
        """订单成交事件处理器（示例）。"""
        logger.debug("订单成交", symbol=event.symbol, side=event.side, shares=event.shares)

    def _on_portfolio_valuation(self, event: PortfolioValuationEvent) -> None:
        """组合估值事件处理器（示例）。"""
        logger.debug("组合估值", date=str(event.date), total=event.total_value)

    def run(self) -> BacktestResult:
        # ... 在适当位置发布事件 ...

        # 示例：在 FILL 阶段成交后发布事件
        # self._bus.publish("order.filled", OrderFilledEvent(...))

        # 示例：在 VALUATION 阶段发布估值事件
        # self._bus.publish("portfolio.valuation", PortfolioValuationEvent(...))
```

**优势**：
- 策略可以订阅订单成交、持仓变动等事件
- 第三方监听器（日志、监控、通知）无需修改核心代码
- 未来支持实时交易时，只需将事件发布到外部系统

---

## 阶段 2：数据访问层重构

### 2.1 新增 `DataManager`

**文件**：`aquant/data/manager.py`

```python
from __future__ import annotations

from functools import lru_cache
from typing import TYPE_CHECKING


if TYPE_CHECKING:
    from datetime import date
    from aquant.data.source import DataSource
    from aquant.market.bar import DayBar


class DataManager:
    """数据管理器，协调数据源、缓存、预加载。

    借鉴 VnPy 的 BarManager / TickManager 分层设计：
    - 屏蔽数据源差异
    - 统一缓存策略
    - 支持多数据源聚合
    """

    def __init__(self, primary_source: DataSource, cache_size: int = 128) -> None:
        self._primary = primary_source
        self._cache_size = cache_size

        # 使用 lru_cache 装饰器缓存
        self._load_bars_cached = lru_cache(maxsize=cache_size)(self._load_bars_impl)

    def load_bars(self, dt: date, symbols: set[str]) -> dict[str, DayBar]:
        """加载指定日期的行情，带缓存。"""
        # 将 set 转为 frozenset 以便哈希
        return self._load_bars_cached(dt, frozenset(symbols))

    def _load_bars_impl(self, dt: date, symbols: frozenset[str]) -> dict[str, DayBar]:
        """实际加载逻辑，由 lru_cache 包装。"""
        return self._primary.load_bars(dt, set(symbols))

    def preload_range(self, start: date, end: date, symbols: set[str]) -> None:
        """预加载指定区间的数据到缓存（可选优化）。"""
        calendar = self._primary.load_calendar(start, end)
        for dt in calendar:
            self.load_bars(dt, symbols)

    def clear_cache(self) -> None:
        """清空缓存。"""
        self._load_bars_cached.cache_clear()
```

**优势**：
- `BigQuantDataSource` 的 `_year_cache` 可以移除，由 `DataManager` 统一管理
- 未来支持多数据源聚合（主数据源 + 备用数据源）
- 支持不同缓存策略（LRU、FIFO、TTL）

### 2.2 改造 `BigQuantDataSource`

**文件**：`aquant/data/bigquant.py`（简化）

```python
# 移除 _year_cache，简化为纯查询层
class BigQuantDataSource(DataSource):
    def __init__(self, access_key: str, secret_key: str) -> None:
        from bigquantdai import dai
        dai.login(access_key, secret_key)
        self._dai = dai

    def load_bars(self, dt: date, symbols: set[str]) -> dict[str, DayBar]:
        # 直接查询当日数据，不做缓存（缓存由 DataManager 负责）
        sql = f"""
        SELECT b.instrument, b.open, b.close, b.high, b.low, b.volume,
               b.upper_limit, b.lower_limit, s.suspended
        FROM cn_stock_real_bar1d b
        LEFT JOIN cn_stock_status s
          ON b.date = s.date AND b.instrument = s.instrument
        WHERE b.date = '{dt}' AND b.instrument IN ({','.join(f"'{s}'" for s in symbols)})
        """
        df = self._query(sql)
        # ... 转换为 DayBar dict ...
```

### 2.3 改造 `Engine` 使用 `DataManager`

```python
class Engine:
    def __init__(self, strategy: Strategy, data_source: DataSource, config: BacktestConfig) -> None:
        # ... 现有代码 ...

        # 新增：数据管理器
        self._data_manager = DataManager(data_source, cache_size=256)

    def run(self) -> BacktestResult:
        # ... 所有 data_source.load_bars 改为 data_manager.load_bars ...
```

---

## 阶段 3：可配置的撮合引擎

### 3.1 `Matcher` 支持可插拔 `Guard`

**文件**：`aquant/matching/matcher.py`（修改）

```python
class Matcher:
    def __init__(
        self,
        cost_model: CostModel,
        rebalance_threshold: float = 0.0,
        volume_cap_ratio: float = 1.0,
        guards: list[Guard] | None = None  # 新增：可选的自定义 Guard 列表
    ) -> None:
        self.cost_model = cost_model
        self.rebalance_threshold = rebalance_threshold

        # 如果未提供 guards，使用默认配置
        if guards is None:
            self._guards = [
                HaltGuard(),
                LimitGuard(),
                T1Guard(),
                AvailableSharesGuard(),
                CashGuard(cost_model.commission_rate, cost_model.min_commission, cost_model.slippage_rate),
                VolumeCapGuard(volume_cap_ratio)
            ]
        else:
            self._guards = guards

    def add_guard(self, guard: Guard) -> None:
        """运行时添加 Guard。"""
        self._guards.append(guard)
```

**优势**：
- 用户可以自定义 `Guard`（例如风控、止损）
- 测试时可以注入 Mock Guard

---

## 阶段 4：事件驱动策略增强

### 4.1 策略支持事件订阅

**文件**：`aquant/strategy/base.py`（扩展）

```python
class Strategy(ABC):
    # ... 现有代码 ...

    def setup_subscriptions(self, bus: MessageBus) -> None:  # noqa: B027
        """可选钩子：策略可订阅事件。

        示例::

            def setup_subscriptions(self, bus):
                bus.subscribe("order.filled", self.on_order_filled)
                bus.subscribe("portfolio.valuation", self.on_valuation)

        在 Engine.__init__() 后、run() 前调用。
        """
        pass
```

### 4.2 示例策略使用事件

```python
class EventDrivenStrategy(Strategy):
    def setup_subscriptions(self, bus: MessageBus) -> None:
        bus.subscribe("order.filled", self.on_order_filled)

    def on_order_filled(self, event: OrderFilledEvent) -> None:
        """订单成交后触发（事件驱动）。"""
        logger.info("我的订单成交了", symbol=event.symbol, price=event.fill_price)

    def on_bar(self, context: Context) -> list[Signal]:
        # 传统的 bar 驱动逻辑
        ...
```

---

## 总体架构对比

### 重构前
```
Engine (上帝对象)
  ├── Strategy (直接调用)
  ├── DataSource (直接查询)
  ├── Portfolio (直接修改)
  └── Matcher (直接执行)
```
- **紧耦合**：组件间直接方法调用
- **难扩展**：添加新功能需要修改 `Engine`

### 重构后
```
MessageBus (中央通信枢纽)
  ├── Engine (发布/订阅事件)
  ├── Strategy (订阅事件 + 发布信号)
  ├── DataManager (缓存 + 聚合)
  │    └── DataSource (纯查询层)
  ├── Portfolio (发布持仓变动事件)
  └── Matcher (发布成交事件)
```
- **松耦合**：组件通过消息总线通信
- **易扩展**：新增监听器无需修改现有代码

---

## 实施计划

### 优先级 P0（必须做）
1. ✅ 引入 `MessageBus`（`aquant/events/bus.py`）
2. ✅ 扩展事件类型（`OrderFilledEvent` 等）
3. ✅ `Engine` 集成消息总线

### 优先级 P1（应该做）
4. 新增 `DataManager`（`aquant/data/manager.py`）
5. 简化 `BigQuantDataSource`（移除 `_year_cache`）
6. `Matcher` 支持可插拔 `Guard`

### 优先级 P2（可以做）
7. 策略支持事件订阅（`setup_subscriptions` 钩子）
8. 添加性能分析监听器（订阅所有事件，统计耗时）
9. 添加实时通知监听器（订阅成交事件，推送到外部系统）

---

## 兼容性保证

### 向后兼容
- 所有现有 API 保持不变
- `demo.py` 和 `momentum_acceleration.py` 无需修改即可运行
- 新功能通过可选参数提供

### 迁移路径
1. 第一阶段：内部重构，不影响用户代码
2. 第二阶段：提供新 API，旧 API 标记为 `@deprecated`
3. 第三阶段（若需要）：移除旧 API

---

## 性能影响评估

### 消息总线开销
- 每个事件多一次函数调用（~100ns）
- 订阅者列表查找 O(1)
- 预期性能损失 < 1%

### 数据管理器开销
- LRU 缓存命中率 > 90%（相同标的重复查询）
- 缓存未命中时性能与原实现相同
- 预期性能提升 10-30%（减少重复查询）

---

## 后续演进方向

1. **实时交易支持**：
   - 消息总线桥接到外部消息队列（RabbitMQ、Kafka）
   - 事件持久化（Event Sourcing）

2. **分布式回测**：
   - 将事件序列化后分发到多个 Worker
   - 每个 Worker 独立回放事件

3. **可视化调试**：
   - 订阅所有事件，实时绘制状态图
   - 时光机：暂停、回退、单步执行

---

## 参考资料

- [NautilusTrader 架构文档](https://nautilustrader.io/docs/concepts/architecture)
- [VnPy 数据模块设计](https://www.vnpy.com/docs/cn/data_recorder.html)
- Martin Fowler - Event-Driven Architecture
- 《企业应用架构模式》- 领域事件
