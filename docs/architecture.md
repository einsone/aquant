# Aquant 架构设计

本文档详细介绍 Aquant 的架构设计理念和实现细节。

## 设计原则

### 1. 简洁优于复杂

- 核心代码 ~3000 行
- 清晰的职责分离
- 最小化概念层次

### 2. 类型安全

- 完整的类型注解
- 使用 `ty` 进行类型检查
- 避免运行时类型错误

### 3. 可扩展性

- 插件式架构（DataSource、RiskRule、TradingRules）
- 事件驱动设计
- 面向接口编程

### 4. 向后兼容

- 新功能不破坏现有代码
- 可选的高级特性
- 渐进式采用

## 核心架构

### 模块层次

```text
aquant/
├── core/           # 核心引擎和上下文
├── strategy/       # 策略基类和信号定义
├── portfolio/      # 组合管理和持仓
├── matching/       # 订单撮合和成本计算
├── market/         # 市场数据结构
├── data/           # 数据源抽象
├── events/         # 事件总线
├── risk/           # 风控管理
├── analytics/      # 绩效分析
└── adjustment/     # 复权处理
```

### 核心组件

#### 1. Engine（引擎）

**职责**：

- 驱动回测事件循环
- 协调各组件交互
- 管理回测生命周期

**事件循环**：

```python
for trading_day in calendar:
    # DAY_START: 日初准备
    portfolio.reset_tradeable()  # 解锁 T+1 持仓

    # SIGNAL: 生成信号
    context = build_context(trading_day)
    signals = strategy.on_bar(context)

    # 风控过滤
    signals = risk_manager.check_signals(signals, portfolio, context)

    # MATCH: 订单撮合
    orders = convert_signals_to_orders(signals)
    for order in orders:
        fill = matcher.match(order, bar)
        if fill:
            portfolio.apply_fill(fill)

    # DAY_END: 日终结算
    portfolio.take_snapshot(trading_day, bars)
```

#### 2. Strategy（策略）

**职责**：

- 实现交易逻辑
- 生成目标持仓信号
- 访问市场数据和组合状态

**接口**：

```python
class Strategy(ABC):
    @abstractmethod
    def on_bar(self, context: Context) -> list[Signal]:
        """每日调用，返回目标持仓信号"""
        pass
```

**信号权重模式**：

策略只需返回目标权重，框架自动处理订单生成：

```python
# 策略视角：只关心目标状态
return [
    Signal(symbol="000001.SZ", weight=0.3),  # 目标 30%
    Signal(symbol="600000.SH", weight=0.2),  # 目标 20%
]

# 框架自动计算：
# - 当前持仓：000001.SZ 10%, 000002.SZ 20%
# - 需要操作：
#   - 000001.SZ: 买入 20%
#   - 600000.SH: 买入 20%
#   - 000002.SZ: 卖出 20%
```

#### 3. Portfolio（组合）

**职责**：

- 管理现金和持仓
- 执行交易结算
- 记录历史数据

**核心数据结构**：

```python
class Portfolio:
    cash: float                        # 可用现金
    positions: dict[str, Position]     # 持仓字典
    trade_log: list[Trade]             # 成交记录
    _daily_nav: list[NavRecord]        # 每日净值快照
```

**持仓结构**：

```python
@dataclass
class Position:
    symbol: str
    shares: int                 # 总股数
    tradeable_shares: int       # 可卖股数（T+1 规则）
    cost_basis: float           # 成本价
    market_value: float         # 市值
    last_close: float           # 最新收盘价
```

#### 4. Matcher（撮合器）

**职责**：

- 将订单转换为成交
- 计算交易成本
- 应用交易规则

**撮合流程**：

```python
def match(self, order: Order, bar: DayBar) -> Fill | None:
    # 1. 检查 Guard（订单级检查）
    for guard in self._guards:
        if not guard.check(order, portfolio):
            return None

    # 2. 计算成交价格（开盘价 + 滑点）
    fill_price = calculate_fill_price(order.side, bar.open)

    # 3. 计算交易成本
    commission, stamp_duty = calculate_cost(order.side, order.shares * fill_price)

    # 4. 生成成交
    return Fill(symbol, side, shares, fill_price, commission, stamp_duty)
```

## 高级特性

### 1. CQRS 模式 - Query Service

**问题**：策略需要查询历史数据（净值曲线、回撤、胜率等）

**方案**：查询服务模式

```python
class PortfolioQueryService:
    """只读查询接口"""

    def get_nav_curve(self, start: date, end: date) -> pl.DataFrame:
        """查询净值曲线"""
        pass

    def get_current_drawdown(self) -> float:
        """查询当前回撤"""
        pass

    def get_win_rate(self, symbol: str | None) -> float:
        """查询胜率"""
        pass
```

策略通过 `context.query` 访问：

```python
def on_bar(self, context: Context) -> list[Signal]:
    # 查询当前回撤，回撤过大时减仓
    current_dd = context.query.get_current_drawdown()
    if current_dd > 0.1:
        return []  # 空仓

    return signals
```

### 2. 可插拔风控系统

**问题**：需要在信号生成后进行组合级风控

**方案**：RiskManager + RiskRule

```python
class RiskRule(ABC):
    """风控规则抽象基类"""

    @abstractmethod
    def check(self, signal: Signal, portfolio: Portfolio, context: Context) -> bool:
        """返回 True 表示通过，False 表示拦截"""
        pass
```

**内置规则**：

- `MaxPositionSizeRule`: 单标的权重上限
- `MaxDrawdownRule`: 回撤超限时停止买入
- `MaxLeverageRule`: 杠杆率跟踪
- `ConcentrationRule`: 集中度限制

**使用方式**：

```python
risk_manager = RiskManager(rules=[
    MaxPositionSizeRule(max_ratio=0.2),
    MaxDrawdownRule(max_dd=0.15),
    ConcentrationRule(top_n=5, max_concentration=0.6),
])

# 在 Engine 中使用
engine = Engine(strategy, data_source, config, risk_manager=risk_manager)
```

**执行流程**：

```text
策略生成信号 → RiskManager 过滤 → 通过的信号进入撮合
```

### 3. 交易规则抽象 - TradingRules

**问题**：不同品种有不同的交易规则（T+1、手续费等）

**方案**：TradingRules 抽象

```python
class TradingRules(ABC):
    """交易规则抽象基类"""

    @abstractmethod
    def can_trade_today(self, symbol: str, position: Position | None) -> bool:
        """判断是否可以交易（T+N 规则）"""
        pass

    @abstractmethod
    def compute_cost(self, side: str, value: float) -> tuple[float, float]:
        """计算交易成本（佣金、印花税）"""
        pass

    @abstractmethod
    def get_lot_size(self, symbol: str) -> int:
        """获取最小交易单位"""
        pass
```

**内置规则**：

- `StockRules`: A 股（T+1、印花税、100 股/手）
- `FuturesRules`: 期货（T+0、手续费、1 手）

**使用方式**：

```python
# 期货回测
futures_rules = FuturesRules()
matcher = Matcher(guards=[], trading_rules=futures_rules)
```

### 4. 事件驱动架构 - Message Bus

**设计**：松耦合的事件通信

```python
class MessageBus:
    def subscribe(self, topic: str, handler: Callable[[Event], None]) -> None:
        """订阅事件"""
        pass

    def publish(self, topic: str, event: Event) -> None:
        """发布事件"""
        pass
```

**业务事件**：

- `OrderSubmittedEvent`: 订单提交
- `OrderFilledEvent`: 订单成交
- `PositionChangedEvent`: 持仓变化
- `PortfolioValuationEvent`: 组合估值

**应用场景**：

- 实时监控
- 日志记录
- 事件回放（调试）
- 策略组合

### 5. 数据管理 - DataManager

**问题**：频繁从数据源加载数据效率低

**方案**：LRU 缓存 + 预加载

```python
class DataManager:
    def __init__(self, primary_source: DataSource, cache_size: int = 128):
        self._primary = primary_source
        self._load_bars_cached = lru_cache(maxsize=cache_size)(self._load_bars_impl)

    def load_bars(self, dt: date, symbols: set[str]) -> dict[str, DayBar]:
        """加载行情（自动缓存）"""
        return self._load_bars_cached(dt, frozenset(symbols))

    def preload_range(self, start: date, end: date, symbols: set[str]) -> None:
        """预加载区间数据"""
        calendar = self._primary.load_calendar(start, end)
        for dt in calendar:
            self.load_bars(dt, symbols)
```

## 设计模式应用

| 模式 | 应用场景 | 组件 |
|------|---------|------|
| Strategy | 策略算法可替换 | Strategy |
| Template Method | 策略生命周期统一 | Strategy.on_bar() |
| Abstract Factory | 数据源可替换 | DataSource |
| Repository | 持久化抽象 | PortfolioQueryService |
| Guard/Chain of Responsibility | 订单检查链 | Guard |
| Decorator | 规则组合 | RiskRule |
| Observer | 事件通知 | MessageBus |
| Facade | 简化接口 | Engine |

## 性能考虑

### 1. 缓存策略

- DataManager: LRU 缓存行情数据
- QueryService: 直接访问内存列表

### 2. 数据结构选择

- Position: dataclass（高效、类型安全）
- 日收益率: Polars Series（向量化计算）
- 交易记录: list（顺序追加）

### 3. 避免过早优化

- 当前性能瓶颈在数据加载，不在计算
- 优先保证代码清晰
- 性能关键路径使用 Polars

## 扩展点

框架预留的扩展接口：

1. **DataSource**: 自定义数据源
2. **Strategy**: 自定义策略
3. **RiskRule**: 自定义风控规则
4. **Guard**: 自定义订单检查
5. **TradingRules**: 自定义交易规则
6. **Event Handler**: 自定义事件处理器

## 限制与权衡

### 当前限制

1. **仅支持日频回测**
   - 原因：简化设计，覆盖大部分场景
   - 未来：可扩展到分钟级

2. **仅支持做多**
   - 原因：A 股市场特点
   - 未来：Signal.weight 支持负值

3. **单账户模式**
   - 原因：简化资金管理
   - 未来：支持子账户

### 设计权衡

| 权衡 | 选择 | 理由 |
|------|------|------|
| 信号模式 vs 订单模式 | 信号模式 | 更简洁，适合大部分策略 |
| 同步 vs 异步 | 同步 | 回测无需异步，降低复杂度 |
| Repository vs 直接访问 | 直接访问 | 单进程内存访问足够快 |
| 事件驱动 vs 直接调用 | 混合 | 核心流程直接调用，扩展使用事件 |

## 与其他框架对比

| 特性 | Aquant | Backtrader | Zipline | VeighNa |
|------|--------|------------|---------|---------|
| 定位 | 轻量级信号回测 | 全功能回测 | 量化研究 | 实盘交易 |
| 复杂度 | 低 | 中 | 高 | 高 |
| 学习曲线 | 平缓 | 陡峭 | 陡峭 | 陡峭 |
| 类型安全 | ✅ | ❌ | ❌ | 部分 |
| 中文文档 | ✅ | ❌ | ❌ | ✅ |
| 实盘对接 | ❌ | ✅ | ❌ | ✅ |

## 未来规划

1. **性能优化**
   - Numba 加速关键计算
   - 并行回测多个策略

2. **功能扩展**
   - 分钟级回测
   - 做空支持
   - 期权支持

3. **生态建设**
   - 更多数据源适配器
   - 策略模板库
   - 因子库集成
