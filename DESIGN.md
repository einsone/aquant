# aquantv2 架构设计文档

## 1. 设计原则

- **单向依赖**：模块间依赖方向严格单向，无循环引用
- **接口隔离**：策略对框架的唯一依赖是 `Strategy` 基类和 `Signal` dataclass
- **框架不限制数据访问**：策略自由使用 duckdb / polars / pyarrow，框架只提供 `context.current_date`
- **事件只携带数据**：路由逻辑在 engine，不放进 event 对象
- **同步撮合**：信号处理和委托结算在同一事件内同步完成，不引入异步 order queue
- **按需加载行情**：框架不预加载全量行情，每日仅查询信号标的与持仓标的的当日行情

---

## 2. 目录结构

```
aquantv2/
├── aquant/
│   ├── core/
│   │   ├── engine.py        # 主事件循环，事件路由
│   │   └── context.py       # 策略运行时上下文（只读）
│   ├── events/
│   │   ├── event.py         # Event 基类，Phase 枚举
│   │   └── queue.py         # 事件队列，按 (date, phase) 排序
│   ├── strategy/
│   │   ├── base.py          # Strategy 抽象基类
│   │   └── signal.py        # Signal dataclass
│   ├── portfolio/
│   │   ├── portfolio.py     # 持仓、现金、净值；维护交易记录
│   │   └── position.py      # Position、NavRecord、Trade dataclass
│   ├── matching/
│   │   ├── matcher.py       # 信号→目标仓位→委托→结算（同步）
│   │   ├── order.py         # Order dataclass
│   │   ├── guards.py        # 委托校验规则链
│   │   └── cost.py          # 佣金、印花税、滑点
│   ├── market/
│   │   ├── calendar.py      # 交易日历
│   │   ├── universe.py      # 每日可交易标的
│   │   └── bar.py           # DayBar dataclass（框架内部用）
│   ├── adjustment/
│   │   ├── adjuster.py      # 除权除息、退市强制平仓
│   │   └── corporate.py     # CorporateAction dataclass
│   ├── analytics/
│   │   ├── metrics.py       # 绩效指标计算（polars，无状态函数）
│   │   └── report.py        # 报告输出（dict / HTML）
│   └── optimization/
│       ├── grid_search.py   # 网格搜索
│       └── walk_forward.py  # Walk-forward 滚动验证
├── tests/
├── examples/
│   └── momentum_demo.py
└── pyproject.toml
```

---

## 3. 核心数据流

每个交易日按 Phase 顺序处理，Phase 值即队列排序键：

```
Engine.run()
│
├── 初始化
│     ├── calendar.load()          加载交易日列表
│     ├── universe.preload()       一次性加载全回测区间的可交易标的
│     │                            dict[date, frozenset[str]]
│     ├── adjuster.preload()       一次性加载全区间企业行动和退市数据
│     │                            按 pay_date / ex_date / delist_date 索引
│     ├── 按交易日填充事件队列
│     │     每日固定插入：DAY_START, SIGNAL, VALUATION
│     │     按需插入：ADJUSTMENT（adjuster._pending_cash/_pending_bonus 有数据时）
│     │               DELIST（adjuster._delisted 有数据时）
│     ├── warmup_remaining = strategy.warmup_period  # 单位：交易日
│     ├── start_date 必须是交易日（calendar 中存在），否则引擎在初始化时报错
│     ├── context = Context(current_date=start_date, tradeable=universe[start_date], ...)
│     └── strategy.on_start(context)   # current_date = start_date
│
└── while queue not empty:
      event = queue.pop()          按 (date, phase) 有序弹出
      │
      # 每日状态（按日期变化时重置，不按 event 重置）
      # current_day: date | None = None
      # day_bars: dict[str, DayBar] = {}
      # day_is_warmup: bool
      # 在 DAY_START 阶段设置 day_is_warmup，确保同日后续 phase 看到一致的值
      │
      match event.phase:
        DAY_START    → portfolio.reset_tradeable()
                       day_is_warmup = (warmup_remaining > 0)
                       # 将所有 position.tradeable_shares 重置为 position.shares
                       # 解锁前一日买入的持仓

        ADJUSTMENT   → adjuster.apply(event, portfolio)
                       # apply 完成后再构造 adj_context，策略看到调整后的状态
                       adj_context = Context(current_date=event.date, ...)
                       for action in event.actions:  # event.actions 在初始化时去重填充
                           strategy.on_adjustment(adj_context, action, action_type)
                           # action_type: "cash" | "bonus"，区分同一对象的两次回调
                       # 现金分红：cash 增加，cost_basis 降低
                       # 送股：shares 增加，tradeable_shares 不变（T+1），cost_basis 摊薄

        DELIST       → delist_bars = load_bars(event.date, set(event.symbols))
                       adjuster.force_close(event, portfolio, delist_bars)
                       # event.symbols 来自 adjuster._delisted[date]（初始化时预扫）
                       # 跳过 guard 链，直接结算

        SIGNAL       → context = engine._build_context(event.date)
                       if day_is_warmup:
                           warmup_remaining -= 1
                           strategy.on_bar(context)   # 调用但丢弃返回值
                       else:
                           signals = strategy.on_bar(context)
                           # 新标的 current_weight = 0；weight=0 对无持仓标的是 no-op
                           symbols = {s.symbol for s in signals} | portfolio.symbols
                           day_bars = load_bars(event.date, symbols)
                           base_value = portfolio.total_value   # 缓存，整个 execute 内固定
                           matcher.execute(signals, portfolio, day_bars, base_value)

        VALUATION    → if not day_is_warmup:
                           portfolio.take_snapshot(event.date, day_bars)
                           # day_bars 复用同日 SIGNAL 阶段的缓存，不重复查询
                           # 预热期内跳过，不记录 NavRecord

strategy.on_end(context)   # current_date = end_date（最后一个交易日）
```

**day_bars 作用域**：`day_bars` 是引擎的日级状态变量，每日 SIGNAL 阶段赋值，VALUATION 复用，跨事件迭代不重置。实现时应作为 `engine` 的实例变量而非局部变量。

`load_bars(date, symbols) -> dict[str, DayBar]` 是用户注入的回调。正常交易日调用最多两次：
1. DELIST 阶段：仅加载退市标的行情（无退市时跳过）
2. SIGNAL 阶段：加载 `signal标的 ∪ 持仓标的`，结果缓存供 VALUATION 复用

预热期内无撮合，跳过 VALUATION，仅在有退市时调用 DELIST 的 `load_bars`。

---

## 4. 模块说明

### 4.1 事件系统

```python
# events/event.py
class Phase(IntEnum):
    DAY_START  = 1   # 每日初始化（重置可卖数量）
    ADJUSTMENT = 2   # 企业行动（除权除息）
    DELIST     = 3   # 退市强制平仓
    SIGNAL     = 4   # 策略运行，产生信号，同步撮合
    VALUATION  = 5   # 净值估算，记录快照

@dataclass
class Event:
    date:  date
    phase: Phase

@dataclass
class AdjustmentEvent(Event):
    phase:   Phase = field(default=Phase.ADJUSTMENT, init=False)
    actions: list[CorporateAction] = field(default_factory=list)

@dataclass
class DelistEvent(Event):
    phase:   Phase = field(default=Phase.DELIST, init=False)
    symbols: list[str] = field(default_factory=list)

@dataclass
class SignalEvent(Event):
    phase: Phase = field(default=Phase.SIGNAL, init=False)
```

**相位顺序保证的不变式：**
- ADJUSTMENT 先于 DELIST：同日既有派息又有退市的标的，先派息后清仓，股东不损失当日红利
- ADJUSTMENT 先于 SIGNAL：策略看到的持仓已是除权除息后的状态
- 送股在 ADJUSTMENT 中增加 `position.shares` 但不增加 `tradeable_shares`（DAY_START 已在更早的 phase 重置，ADJUSTMENT 之后不再重置），因此送股当日不可卖出，符合 T+1

### 4.2 市场行情（按需加载）

```python
# market/bar.py
@dataclass(frozen=True)
class DayBar:
    symbol:      str
    date:        date
    open:        float
    close:       float
    high:        float
    low:         float
    volume:      float        # 单位：股（shares），用于 VolumeCapGuard
    up_limit:    float        # 涨停价
    down_limit:  float        # 跌停价
    is_halted:   bool         # 停牌
    is_delisted: bool         # 退市
```

框架内部需要行情的地方：

| 用途 | 需要字段 |
|---|---|
| 权重→股数换算（T+1 开盘成交）| `open` |
| 净值估算 | `close` |
| 停牌检测（HaltGuard）| `is_halted` 或记录缺失 |
| 涨跌停检测（LimitGuard）| `up_limit`、`down_limit`、`high`、`low` |
| 成交量上限（VolumeCapGuard）| `volume`（股数）|
| 退市强制清仓 | `open` |

框架**不**预加载全量行情。每日查询范围：`signal 标的 ∪ 当前持仓标的`，通过用户注入的 `load_bars` 回调获取，每日调用一次。

### 4.3 Context

策略通过 `context` 访问框架状态，构造为只读：

```python
@dataclass(frozen=True)
class Context:
    current_date: date
    tradeable:    frozenset[str]           # 当日可交易标的（已排除停牌、退市）
    positions:    dict[str, PositionView]  # 只读持仓视图
    cash:         float
    total_value:  float
```

`context` 不提供任何数据查询接口，策略自行管理数据库连接。

`context` 的构造时机：
- `on_start`：`current_date = start_date`，持仓为空，`cash = initial_capital`
- 每次 SIGNAL 事件前：`current_date = event.date`，持仓和现金反映上一日结算后的状态
- `on_end`：`current_date = end_date`（最后一个交易日）

### 4.4 Strategy

```python
class Strategy(ABC):
    warmup_period: int = 0   # 预热期，单位：交易日

    def on_start(self, context: Context) -> None: ...

    @abstractmethod
    def on_bar(self, context: Context) -> list[Signal]: ...

    def on_adjustment(self, context: Context, action: CorporateAction,
                      adjustment_type: Literal["cash", "bonus"]) -> None: ...
    # 在 adjuster.apply 处理完当日所有企业行动后统一回调
    # context 反映的是全部调整完成后的持仓状态，不是单条 action 的增量状态
    # adjustment_type 区分本次回调触发的是现金分红（"cash"）还是送股（"bonus"）

    def on_end(self, context: Context) -> None: ...
```

**`on_bar` 返回值语义：**
- 返回 `[]`：维持现状，不触发任何交易
- 返回含某标的 `weight=0` 的信号：清仓该标的
- 预热期内 `on_bar` 正常调用（策略可初始化内部状态），返回值被引擎丢弃

**多进程优化注意事项：** 使用 `walk_forward(n_jobs != 1)` 时，每个 worker 是独立进程，策略实例会被 pickle 后在子进程重建。持有文件型 DuckDB 连接（`duckdb.connect("file.db")`）的策略会因 DuckDB 单写者限制导致多进程冲突。应在 `on_start` 内创建连接，或使用只读模式 `duckdb.connect("file.db", read_only=True)`。

### 4.5 Signal

```python
@dataclass
class Signal:
    symbol: str
    weight: float   # 目标权重，相对组合总市值；0 = 清仓；负值保留用于做空
    meta:   dict = field(default_factory=dict)
```

### 4.6 CorporateAction

```python
# adjustment/corporate.py
@dataclass(frozen=True)
class CorporateAction:
    symbol:         str
    register_date:  date
    pay_date:       Optional[date]   # 现金红利到账日；cash_per_share == 0 时为 None
    ex_date:        Optional[date]   # 送股除权日；bonus_ratio == 0 时为 None
    cash_per_share: float            # 税后现金红利（元/股），0.0 表示无现金分红
    bonus_ratio:    float            # 送股比例（0.5 = 每股送 0.5 股），0.0 表示无送股
```

`adjuster.preload()` 按 `pay_date` 和 `ex_date` 分别建立索引，两者可能不同日。同一 `CorporateAction` 对象可同时出现在两个 dict（`pay_date == ex_date` 时）。

`AdjustmentEvent.actions` 在引擎初始化时填充，内容为该日所有涉及的 `CorporateAction` 对象（去重，按 `(symbol, register_date)` 唯一）。`on_adjustment` 回调通过 `adjustment_type` 区分当日是触发了现金分红还是送股。

### 4.7 Matcher（信号→结算，同步）

`matcher.execute(signals, portfolio, bars: dict[str, DayBar], base_value: float)` 完成完整撮合流程。

`base_value` 是调用前由引擎计算的 `portfolio.total_value` 快照，整个 `execute()` 调用内固定不变。好处：每个信号的目标权重基于相同的组合价值，处理顺序不影响结果；同时避免每条信号重复遍历所有持仓。

**步骤一：权重 → 目标股数**

```
bar = bars.get(signal.symbol)
if bar is None or bar.is_halted or bar.open <= 0: skip   # 无行情或开盘价异常则跳过
available_capital = base_value * (1 - cash_buffer)
target_value      = available_capital * signal.weight
lot_size          = 200 if symbol.startswith("688") else 100
target_shares     = floor(target_value / bar.open / lot_size) * lot_size
```

**步骤二：差量计算与阈值过滤**

```
pos            = portfolio.positions.get(signal.symbol)
current_shares = pos.shares if pos else 0
current_weight = current_shares * bar.open / base_value
delta_weight   = signal.weight - current_weight
if abs(delta_weight) < rebalance_threshold: skip
delta_shares   = target_shares - current_shares
if delta_shares == 0: skip
```

`current_weight` 分子用今日 `open`，分母用 `portfolio.total_value`（基于昨日 `last_close`），两者价格基准略有不同，是盘中无法精确估值的合理近似，已在第 6 节决策表中记录。

**步骤三：Guard 链校验**

`Order` dataclass：

```python
@dataclass
class Order:
    symbol: str
    side:   Literal["buy", "sell"]
    shares: int     # guard 链可修改此值
    locked: bool = False  # T1Guard 在买入时设为 True，结算后不增加 tradeable_shares
```

每条 guard 签名：`check(order: Order, bar: DayBar, portfolio: Portfolio) -> bool`
- 可修改 `order.shares`
- 返回 `False` 则拒绝委托，引擎丢弃该 order

| Guard | 行为 |
|---|---|
| `HaltGuard` | 步骤一已过滤 `is_halted` 和 `open <= 0`；guard 链作为防御性二次检查，确保自定义 guard 不依赖步骤一的前提 |
| `LimitGuard` | 买入时 `open >= up_limit` → 拒绝；卖出时 `open <= down_limit` → 拒绝。以开盘价判断，与 T+1 开盘成交语义一致 |
| `T1Guard` | 买入：设 `order.locked = True`，结算后 `tradeable_shares` 不增加 |
| `AvailableSharesGuard` | 卖出截断至 `position.tradeable_shares`，按手数取整；低于最小手数 → 拒绝 |
| `CashGuard` | 资金不足时缩减买入量：`floor((cash - overhead) / open / lot_size) * lot_size`；自身完成手数对齐，不依赖外部 guard；低于最小手数 → 拒绝 |
| `VolumeCapGuard` | `order.shares > bar.volume * ratio` 时截断；`volume` 单位为股；默认 ratio=1.0（关闭）|
| `DelistGuard` | `bar.is_delisted=True` → 拒绝买入 |

**步骤四：结算**

```python
fill_price  = bar.open * (1 + slippage)   # 买入；卖出为 * (1 - slippage)
value       = order.shares * fill_price
commission  = max(value * commission_rate, min_commission)
stamp_duty  = value * stamp_duty_rate if order.side == "sell" else 0.0

portfolio.apply_fill(order, fill_price, commission, stamp_duty)
```

`apply_fill` 更新以下状态，并在 `shares == 0` 时从 `portfolio.positions` 中删除该仓位：
- `position.shares`
- `position.tradeable_shares`（买入且 `order.locked` 时不增加）
- `position.cost_basis`：买入时加权平均，**不含佣金**；卖出时不变；反复分红后可能为负（属正常会计现象，不做截断）
- `position.market_value`：首次建仓时初始化为 `shares * bar.open`；后续由 `take_snapshot` 更新
- `position.last_close`：首次建仓时初始化为 `bar.open`；后续由 `take_snapshot` 更新
- `portfolio.cash`
- `portfolio.trade_log`（追加 `Trade`）

`Trade.pnl` 计算：`(fill_price - cost_basis) * shares - commission - stamp_duty`，其中 `cost_basis` 不含买入佣金，因此卖出盈亏中也不摊销买入佣金——这是有意的近似，实现简单且保守（略微低估盈利）。

### 4.8 Portfolio

```python
class Portfolio:
    cash:       float
    positions:  dict[str, Position]
    _daily_nav: list[NavRecord]
    trade_log:  list[Trade]

    @property
    def total_value(self) -> float:
        return self.cash + sum(p.market_value for p in self.positions.values())

    @property
    def symbols(self) -> set[str]:
        return set(self.positions.keys())

    def reset_tradeable(self) -> None:
        for pos in self.positions.values():
            pos.tradeable_shares = pos.shares

    def take_snapshot(self, date: date, bars: dict[str, DayBar]) -> None:
        for pos in self.positions.values():
            bar = bars.get(pos.symbol)
            if bar and not bar.is_halted:
                pos.last_close = bar.close
            pos.market_value = pos.shares * pos.last_close
        self._daily_nav.append(NavRecord(date=date, total=self.total_value, cash=self.cash))
```

`Position` dataclass：

```python
@dataclass
class Position:
    symbol:           str
    shares:           int
    tradeable_shares: int     # 当日可卖数量（T+1 约束）
    cost_basis:       float   # 单股平均成本（用于 pnl 计算）
    market_value:     float   # 最近估值（take_snapshot 时更新）
    last_close:       float   # 最近有效收盘价（停牌时估值用，建仓时初始化为成交价）
```

`NavRecord` dataclass：

```python
@dataclass
class NavRecord:
    date:  date
    total: float   # 组合总市值
    cash:  float
```

`Trade` dataclass：

```python
@dataclass
class Trade:
    date:       date
    symbol:     str
    side:       Literal["buy", "sell"]
    shares:     int
    price:      float
    commission: float
    stamp_duty: float
    pnl:        float   # 卖出：(price - cost_basis) * shares - commission - stamp_duty；买入为 0
```

### 4.9 Adjuster（企业行动与退市）

```python
class Adjuster:
    _pending_cash:  dict[date, list[CorporateAction]]  # key = pay_date，仅 cash_per_share > 0
    _pending_bonus: dict[date, list[CorporateAction]]  # key = ex_date，仅 bonus_ratio > 0
    _delisted:      dict[date, list[str]]               # key = delist_date

    def preload(self, start: date, end: date, load_fn: Callable) -> None:
        # 企业行动：pay_date >= start OR ex_date >= start
        # 仅当 cash_per_share > 0 时索引到 _pending_cash
        # 仅当 bonus_ratio > 0 时索引到 _pending_bonus
        # 同一 CorporateAction 可同时出现在两个 dict（pay_date == ex_date 时）
        # 退市：delist_date 在 [start, end]，填充 _delisted
        ...

    def apply(self, event: AdjustmentEvent, portfolio: Portfolio) -> None:
        date = event.date
        for action in self._pending_cash.get(date, []):
            pos = portfolio.positions.get(action.symbol)
            if pos is None:
                continue
            cash = pos.shares * action.cash_per_share
            portfolio.cash += cash
            pos.cost_basis -= action.cash_per_share
            # cost_basis 可能为负（多次分红后），不做截断，属正常会计现象

        for action in self._pending_bonus.get(date, []):
            pos = portfolio.positions.get(action.symbol)
            if pos is None:
                continue
            new_shares = int(pos.shares * action.bonus_ratio)
            if new_shares == 0:
                continue
            old_total_cost = pos.cost_basis * pos.shares
            pos.shares += new_shares
            pos.cost_basis = old_total_cost / pos.shares  # 摊薄
            # tradeable_shares 不变——送股当日不可卖（T+1）
            # 注：送股可能产生非手数对齐的持仓（如持 100 股，bonus_ratio=0.15 → 新增 15 股）
            # 多余的零散股（凑不满一手）在 AvailableSharesGuard 卖出时会被截掉，实际不可卖

    def force_close(self, event: DelistEvent, portfolio: Portfolio,
                    bars: dict[str, DayBar]) -> None:
        # bars 由 engine 在 DELIST 阶段调用 load_bars 后传入
        to_close = [s for s in event.symbols if s in portfolio.positions]
        if not to_close:
            return
        for symbol in to_close:
            pos = portfolio.positions[symbol]
            bar = bars.get(symbol)
            price = bar.open if bar and bar.open > 0 else pos.last_close
            # 跳过 guard 链，直接结算
            ...
```

### 4.10 Universe（外部注入）

```python
# 用户提供，Engine 初始化时调用一次，结果缓存
def load_universe(start: date, end: date) -> dict[date, frozenset[str]]: ...
```

### 4.11 Analytics

回测结束后，`portfolio._daily_nav` 和 `portfolio.trade_log` 转为 polars DataFrame，批量计算。

**基准对齐**：基准由用户以 `pl.DataFrame({"date": [...], "return": [...]})` 注入。analytics 模块按 `date` 列 join 组合日收益后提取对齐的 `pl.Series`，再传入各计算函数；日期不匹配时报错而非静默错位。

所有计算函数接收已对齐的 `pl.Series`，无状态：

```python
def sharpe(returns: pl.Series, risk_free: float = 0.0) -> float: ...
def max_drawdown(nav: pl.Series) -> tuple[float, int]: ...
# 返回 (最大回撤比例, 持续时间（交易日数）)
# 映射到 metrics dict: {"max_drawdown": float, "max_drawdown_duration_days": int}
def information_ratio(returns: pl.Series, benchmark: pl.Series) -> float: ...
# 两个 Series 均为按 date join 后的对齐序列，长度相同
```

| 类别 | 指标 |
|---|---|
| 收益 | 累计收益、年化收益、超额年化收益 |
| 风险 | 年化波动率、最大回撤、最大回撤持续时间 |
| 风险调整 | Sharpe、Calmar、信息比率（IR）|
| 相对基准 | Alpha、Beta |
| 交易统计 | 年化换手率、平均持仓数、胜率、盈亏比 |
| 时序 | 月度收益热力图、滚动 6/12 月 Sharpe |

### 4.12 Optimization

```python
results = grid_search(
    strategy_cls=MomentumStrategy,
    param_grid={"lookback": [20, 60, 120], "top_n": [20, 30, 50]},
    config=BacktestConfig(...),
    metric="sharpe",
)  # 返回 polars DataFrame，列 = 参数名 + 所有绩效指标，行 = 每组参数组合

results = walk_forward(
    strategy_cls=MomentumStrategy,
    param_grid=...,
    config=...,
    train_window=252,   # 交易日
    test_window=63,     # 交易日
    n_jobs=-1,          # multiprocessing；策略须在 on_start 内建立 DB 连接
)
# 返回 polars DataFrame，列 = 参数名 + 绩效指标 + fold_start + fold_end，行 = 每个测试折
```

---

## 5. 模块依赖关系

```
engine
  ├── events/queue
  ├── market/calendar, universe, bar
  ├── adjustment/adjuster, corporate
  ├── strategy/base              ← 用户策略继承此处
  ├── matching/matcher
  │     ├── matching/guards
  │     ├── matching/cost
  │     └── portfolio/portfolio
  └── analytics/metrics, report

optimization → engine
strategy（用户代码）→ strategy/base, strategy/signal, core/context
```

`portfolio` 不依赖 `matcher`，`matcher` 调用 `portfolio.apply_fill()`，单向。

---

## 6. 关键设计决策汇总

| 问题 | 决策 |
|---|---|
| 撮合模式 | 同步：信号处理和结算在 SIGNAL 事件内一步完成 |
| 行情加载 | 按需：每日一次，`signal标的 ∪ 持仓标的`，VALUATION 复用 SIGNAL 缓存 |
| 空信号语义 | `[]` = 维持现状；清仓需显式返回 `weight=0` |
| 阈值计算基准 | 权重偏差（`\|target_weight - current_weight\|`），与组合规模无关 |
| `start_date` 约束 | 必须是交易日，初始化时校验；`on_start` 的 `tradeable = universe[start_date]` |
| `initial_capital` 约束 | 必须 > 0，`BacktestConfig` 初始化时校验；防止 `base_value == 0` 除零 |
| 去重键 `(symbol, register_date)` | 假设同标的同登记日只有一条企业行动记录；数据源有重复时行为未定义 |
| `on_adjustment` 批量语义 | 当日所有 action apply 完成后统一回调；context 反映全部调整后状态 |
| `HaltGuard` 定位 | 步骤一已过滤停牌，HaltGuard 作为防御性安全网保留；不影响正常流程 |
| `day_is_warmup` | DAY_START 阶段设置，确保同日所有后续 phase 看到一致的预热状态 |
| `base_value` 缓存 | `matcher.execute` 入参，调用前由引擎计算一次；execute 内不重算 |
| 事件队列结构 | 初始化后转为排序列表，顺序遍历；不使用 heapq（无运行时插入需求）|
| `on_adjustment` 回调时机 | `adjuster.apply` 完成后构造 `adj_context`，策略看到调整后的持仓状态 |
| `event.actions` 填充 | 初始化时由引擎填充，按 `(symbol, register_date)` 去重 |
| `CorporateAction` 日期字段 | `Optional[date]`；无现金分红时 `pay_date=None`，无送股时 `ex_date=None` |
| `on_adjustment` 类型区分 | 增加 `adjustment_type: Literal["cash", "bonus"]` 参数 |
| `weight=0` 对无持仓标的 | delta_weight=0，被阈值过滤，no-op；不报错 |
| 无持仓新标的 position | `current_shares = 0`，`current_weight = 0`；matcher 创建新 Position |
| `on_adjustment` context | 单独构造，`current_date = event.date`（非 SIGNAL 的 context）|
| load_bars 调用次数 | 每日最多两次：DELIST（仅退市日）+ SIGNAL；VALUATION 复用 SIGNAL 缓存 |
| `preload` 过滤条件 | `cash_per_share > 0` 才索引到 `_pending_cash`；`bonus_ratio > 0` 才索引到 `_pending_bonus` |
| `Position.market_value` 初始化 | `apply_fill` 首次建仓时初始化为 `shares * bar.open` |
| `cost_basis` 负值 | 多次分红后可能为负，属正常会计现象，不截断 |
| 送股零散股 | 送股可能产生非手数对齐持仓，零散部分在 `AvailableSharesGuard` 卖出时被截掉 |
| T+1 实现 | `position.tradeable_shares`；DAY_START 重置；T1Guard 和送股均不增加 tradeable_shares |
| 送股 T+1 | ADJUSTMENT 增加 `shares` 但不增加 `tradeable_shares`，相位顺序的自然结果 |
| 退市检测 | 初始化预扫，`_delisted[date]` 填充 `DelistEvent.symbols`；非名称匹配 |
| 停牌估值 | `position.last_close`（非停牌日的 take_snapshot 时更新），不标 NaN |
| `last_close` 初始化 | 建仓时初始化为成交价（`bar.open`） |
| CashGuard | 自身完成缩减后的手数对齐，不依赖外部 guard |
| 送股 cost_basis | `old_total_cost / new_shares`，不引入 `total_cost` 字段 |
| 零仓位清理 | `apply_fill` 后 `shares == 0` 时从 `portfolio.positions` 删除 |
| pnl 计算方式 | 均价成本法，不含买入佣金；卖出时扣除卖出侧成本 |
| LimitGuard 判断依据 | 以 `open` 价判断涨跌停，与 T+1 开盘成交一致 |
| 预热期单位 | 交易日，引擎用 `warmup_remaining` 计数器递减；预热期内跳过撮合和 VALUATION |
| on_start / on_end context | `current_date = start_date` / `current_date = end_date` |
| 最大回撤持续时间单位 | 交易日数（NavRecord 每条对应一个交易日）|
| 基准数据格式 | `pl.DataFrame` 含 `date` 和 `return` 列，按 date join，不匹配时报错 |
| 企业行动预加载范围 | `pay_date >= start OR ex_date >= start` |
| 并行优化 | multiprocessing，策略须在 `on_start` 内建立 DB 连接 |
| `volume` 单位 | 股数（shares） |

---

## 7. 策略示例

```python
import duckdb
import pyarrow as pa
from aquant import Strategy, Signal

class MomentumStrategy(Strategy):
    warmup_period = 250   # 交易日

    def __init__(self, lookback: int = 20, top_n: int = 30):
        self.lookback = lookback
        self.top_n = top_n
        self._conn = None

    def on_start(self, context):
        # 在 on_start 内建立连接，多进程优化时每个 worker 独立创建
        self._conn = duckdb.connect("data.duckdb", read_only=True)

    def on_bar(self, context):
        dt = context.current_date
        tradeable_tbl = pa.table({"symbol": list(context.tradeable)})
        self._conn.register("tradeable", tradeable_tbl)

        df = self._conn.execute("""
            SELECT b.symbol,
                   b.close / lag(b.close, ?) OVER (
                       PARTITION BY b.symbol ORDER BY b.date
                   ) - 1 AS momentum
            FROM cn_stock_bar1d b
            INNER JOIN tradeable t USING (symbol)
            WHERE b.date <= ?
            QUALIFY b.date = ?
            ORDER BY momentum DESC
            LIMIT ?
        """, [self.lookback, dt, dt, self.top_n]).pl()

        if df.is_empty():
            return []

        n = len(df)
        return [Signal(symbol=row["symbol"], weight=1 / n)
                for row in df.iter_rows(named=True)]
```

```python
import polars as pl
from aquant import Engine, BacktestConfig

engine = Engine(
    strategy=MomentumStrategy(lookback=20, top_n=30),
    load_universe=load_universe,          # (start, end) -> dict[date, frozenset[str]]
    load_bars=load_bars,                  # (date, symbols) -> dict[str, DayBar]
    load_adjustments=load_adjustments,    # (start, end) -> list[CorporateAction]
    config=BacktestConfig(
        start="2015-01-01",
        end="2024-12-31",
        initial_capital=10_000_000,
        benchmark=pl.DataFrame({"date": [...], "return": [...]}),
        commission_rate=0.0003,
        min_commission=5.0,
        stamp_duty_rate=0.001,
        slippage_rate=0.0005,
        cash_buffer=0.02,
        rebalance_threshold=0.01,
    ),
)

result = engine.run()
print(result.metrics)
result.report("output.html")
```
