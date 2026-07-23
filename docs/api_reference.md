# Aquant API 参考

完整的 API 参考文档。

## 核心模块

### aquant.core.engine

#### Engine

回测引擎，驱动整个回测流程。

```python
class Engine:
    def __init__(
        self,
        strategy: Strategy,
        data_source: DataSource,
        config: BacktestConfig,
        risk_manager: RiskManager | None = None,
    ):
        """初始化回测引擎

        参数
        ----
        strategy : Strategy
            策略实例
        data_source : DataSource
            数据源实例
        config : BacktestConfig
            回测配置
        risk_manager : RiskManager, optional
            风控管理器，默认无风控
        """
```

**方法**：

- `run() -> BacktestResult`: 执行回测，返回结果

#### BacktestConfig

回测配置。

```python
@dataclass
class BacktestConfig:
    start: date                    # 回测起始日期
    end: date                      # 回测结束日期
    initial_capital: float         # 初始资金
    universe: list[str]            # 股票池
    benchmark: str | None = None   # 基准代码（可选）
```

#### BacktestResult

回测结果。

```python
@dataclass
class BacktestResult:
    portfolio: Portfolio           # 组合对象
    metrics: dict                  # 绩效指标
    config: BacktestConfig        # 回测配置
```

### aquant.core.context

#### Context

策略上下文，提供市场数据和组合状态访问。

```python
@dataclass(frozen=True)
class Context:
    current_date: date                          # 当前日期
    bars: dict[str, DayBar]                     # 当日行情
    positions: dict[str, PositionView]          # 当前持仓（只读）
    cash: float                                 # 可用现金
    total_value: float                          # 组合总市值
    query: PortfolioQueryService                # 历史数据查询服务
```

## 策略模块

### aquant.strategy.base

#### Strategy

策略基类。

```python
class Strategy(ABC):
    @abstractmethod
    def on_bar(self, context: Context) -> list[Signal]:
        """每日调用，生成目标持仓信号

        参数
        ----
        context : Context
            当前上下文

        返回
        ----
        list[Signal]
            目标持仓信号列表
        """
```

### aquant.strategy.signal

#### Signal

目标持仓信号。

```python
@dataclass
class Signal:
    symbol: str                    # 标的代码
    weight: float                  # 目标权重（0.0-1.0）
    signal_date: date | None       # 信号日期（框架自动填充）
    meta: dict                     # 自定义元数据
```

## 组合模块

### aquant.portfolio.portfolio

#### Portfolio

组合管理器。

```python
class Portfolio:
    def __init__(self, initial_capital: float):
        """初始化组合

        参数
        ----
        initial_capital : float
            初始资金
        """

    @property
    def cash(self) -> float:
        """可用现金"""

    @property
    def total_value(self) -> float:
        """组合总市值"""

    @property
    def positions(self) -> dict[str, Position]:
        """当前持仓"""

    @property
    def trade_log(self) -> list[Trade]:
        """成交记录"""
```

### aquant.portfolio.position

#### Position

持仓状态。

```python
@dataclass
class Position:
    symbol: str                    # 标的代码
    shares: int                    # 总股数
    tradeable_shares: int          # 可卖股数（T+1）
    cost_basis: float              # 成本价
    market_value: float            # 市值
    last_close: float              # 最新收盘价
```

#### PositionView

只读持仓视图（通过 Context 访问）。

```python
@dataclass(frozen=True)
class PositionView:
    symbol: str
    shares: int
    tradeable_shares: int
    cost_basis: float
    market_value: float
    last_close: float
```

#### Trade

成交记录。

```python
@dataclass
class Trade:
    date: date                     # 成交日期
    symbol: str                    # 标的代码
    side: str                      # 买卖方向（"buy"/"sell"）
    shares: int                    # 成交股数
    price: float                   # 成交价格
    commission: float              # 佣金
    stamp_duty: float              # 印花税
    pnl: float                     # 盈亏（卖出时计算）
```

#### NavRecord

净值记录。

```python
@dataclass
class NavRecord:
    date: date                     # 日期
    total: float                   # 总市值
    cash: float                    # 现金
    position_count: int            # 持仓数量
```

### aquant.portfolio.query

#### PortfolioQueryService

组合查询服务（只读）。

```python
class PortfolioQueryService:
    def get_nav_curve(
        self,
        start: date | None = None,
        end: date | None = None,
    ) -> pl.DataFrame:
        """查询净值曲线

        返回
        ----
        DataFrame with columns: [date, nav, cash, position_count]
        """

    def get_recent_trades(
        self,
        symbol: str | None = None,
        n: int = 10,
    ) -> list[Trade]:
        """查询最近 N 笔成交

        参数
        ----
        symbol : str, optional
            标的代码，None 表示所有标的
        n : int
            最大返回条数
        """

    def get_trades_by_date_range(
        self,
        start: date,
        end: date,
        symbol: str | None = None,
    ) -> list[Trade]:
        """查询指定日期区间的成交"""

    def get_peak_nav(self) -> float:
        """获取历史最高净值"""

    def get_current_drawdown(self) -> float:
        """获取当前回撤（相对历史最高）"""

    def get_win_rate(self, symbol: str | None = None) -> float:
        """计算胜率（盈利交易 / 总交易）"""

    def get_total_pnl(self, symbol: str | None = None) -> float:
        """计算累计盈亏"""
```

## 风控模块

### aquant.risk

#### RiskManager

风控管理器。

```python
class RiskManager:
    def __init__(self, rules: list[RiskRule] | None = None):
        """初始化风控管理器

        参数
        ----
        rules : list[RiskRule], optional
            风控规则列表
        """

    def check_signals(
        self,
        signals: list[Signal],
        portfolio: Portfolio,
        context: Context,
    ) -> list[Signal]:
        """检查信号，过滤违反风控规则的信号"""
```

#### RiskRule

风控规则抽象基类。

```python
class RiskRule(ABC):
    @abstractmethod
    def check(
        self,
        signal: Signal,
        portfolio: Portfolio,
        context: Context,
    ) -> bool:
        """检查信号是否通过

        返回
        ----
        bool
            True 表示通过，False 表示拦截
        """
```

#### 内置风控规则

##### MaxPositionSizeRule

单标的权重上限。

```python
class MaxPositionSizeRule(RiskRule):
    def __init__(self, max_ratio: float = 0.2):
        """
        参数
        ----
        max_ratio : float
            单标的最大权重，默认 0.2（20%）
        """
```

##### MaxDrawdownRule

最大回撤限制。

```python
class MaxDrawdownRule(RiskRule):
    def __init__(self, max_dd: float = 0.2):
        """
        参数
        ----
        max_dd : float
            最大回撤阈值，默认 0.2（20%）
        """
```

##### MaxLeverageRule

杠杆率跟踪。

```python
class MaxLeverageRule(RiskRule):
    def __init__(self, max_leverage: float = 1.0):
        """
        参数
        ----
        max_leverage : float
            最大杠杆倍数，默认 1.0（不加杠杆）
        """
```

##### ConcentrationRule

集中度限制。

```python
class ConcentrationRule(RiskRule):
    def __init__(self, top_n: int = 5, max_concentration: float = 0.6):
        """
        参数
        ----
        top_n : int
            前 N 大持仓，默认 5
        max_concentration : float
            前 N 大持仓权重之和上限，默认 0.6（60%）
        """
```

## 数据模块

### aquant.data.source

#### DataSource

数据源抽象基类。

```python
class DataSource(ABC):
    @abstractmethod
    def load_calendar(self, start: date, end: date) -> list[date]:
        """加载交易日历

        返回
        ----
        list[date]
            交易日列表（升序）
        """

    @abstractmethod
    def load_bars(
        self,
        dt: date,
        symbols: set[str],
    ) -> dict[str, DayBar]:
        """加载日行情

        返回
        ----
        dict[str, DayBar]
            标的代码 -> 行情数据
        """
```

### aquant.market.bar

#### DayBar

日行情数据。

```python
@dataclass(frozen=True)
class DayBar:
    symbol: str                    # 标的代码
    date: date                     # 日期
    open: float                    # 开盘价
    close: float                   # 收盘价
    high: float                    # 最高价
    low: float                     # 最低价
    volume: float                  # 成交量
    up_limit: float                # 涨停价
    down_limit: float              # 跌停价
    is_halted: bool                # 是否停牌
```

## 分析模块

### aquant.analytics.metrics

#### 绩效指标函数

```python
def total_return(nav: pl.Series) -> float:
    """累计收益率"""

def annualized_return(nav: pl.Series, trading_days: int = 252) -> float:
    """年化收益率"""

def annualized_volatility(returns: pl.Series, trading_days: int = 252) -> float:
    """年化波动率"""

def sharpe(returns: pl.Series, risk_free: float = 0.0, trading_days: int = 252) -> float:
    """夏普比率"""

def max_drawdown(nav: pl.Series) -> tuple[float, int]:
    """最大回撤和持续天数"""

def calmar(nav: pl.Series, trading_days: int = 252) -> float:
    """卡玛比率"""

def win_rate(trade_log: list) -> float:
    """胜率"""

def profit_loss_ratio(trade_log: list) -> float:
    """盈亏比"""

def compute_all(
    daily_nav: list[NavRecord],
    trade_log: list,
    benchmark_df: pl.DataFrame | None = None,
    trading_days: int = 252,
) -> dict:
    """计算所有绩效指标

    返回
    ----
    dict
        包含所有指标的字典
    """
```

### aquant.analytics.report

#### render_html

生成 HTML 回测报告。

```python
def render_html(
    result: BacktestResult,
    path: str | None = None,
    open_browser: bool = False,
) -> str:
    """生成 HTML 回测报告

    参数
    ----
    result : BacktestResult
        回测结果
    path : str, optional
        保存路径，None 则不保存
    open_browser : bool
        是否自动打开浏览器

    返回
    ----
    str
        HTML 内容
    """
```

## 交易规则模块

### aquant.matching.rules

#### TradingRules

交易规则抽象基类。

```python
class TradingRules(ABC):
    @abstractmethod
    def can_trade_today(
        self,
        symbol: str,
        position: Position | None,
    ) -> bool:
        """判断是否可以交易（T+N 规则）"""

    @abstractmethod
    def compute_cost(
        self,
        side: str,
        value: float,
    ) -> tuple[float, float]:
        """计算交易成本

        返回
        ----
        tuple[float, float]
            (佣金, 印花税/手续费)
        """

    @abstractmethod
    def get_lot_size(self, symbol: str) -> int:
        """获取最小交易单位"""
```

#### 内置交易规则

##### StockRules

A 股交易规则（T+1）。

```python
class StockRules(TradingRules):
    def __init__(
        self,
        commission_rate: float = 0.0003,
        min_commission: float = 5.0,
        stamp_duty_rate: float = 0.001,
        slippage_rate: float = 0.0005,
    ):
        """
        参数
        ----
        commission_rate : float
            佣金费率，默认万三
        min_commission : float
            最低佣金，默认 5 元
        stamp_duty_rate : float
            印花税率，默认千一
        slippage_rate : float
            滑点率，默认万五
        """
```

##### FuturesRules

期货交易规则（T+0）。

```python
class FuturesRules(TradingRules):
    def __init__(
        self,
        fee_rate: float = 0.00005,
        fee_per_lot: float = 0.0,
        slippage_rate: float = 0.0002,
    ):
        """
        参数
        ----
        fee_rate : float
            手续费率，默认万 0.5
        fee_per_lot : float
            每手固定手续费，默认 0
        slippage_rate : float
            滑点率，默认万 2
        """
```

## 事件模块

### aquant.events.bus

#### MessageBus

消息总线。

```python
class MessageBus:
    def subscribe(
        self,
        topic: str,
        handler: Callable[[Event], None],
    ) -> None:
        """订阅事件

        参数
        ----
        topic : str
            事件主题，支持通配符（如 "order.*"）
        handler : Callable
            事件处理函数
        """

    def publish(self, topic: str, event: Event) -> None:
        """发布事件"""

    def unsubscribe(
        self,
        topic: str,
        handler: Callable[[Event], None],
    ) -> None:
        """取消订阅"""
```

### aquant.events.event

#### 业务事件

```python
@dataclass
class OrderSubmittedEvent(Event):
    symbol: str
    side: str
    shares: int

@dataclass
class OrderFilledEvent(Event):
    symbol: str
    side: str
    shares: int
    fill_price: float
    commission: float
    stamp_duty: float

@dataclass
class PositionChangedEvent(Event):
    symbol: str
    old_shares: int
    new_shares: int

@dataclass
class PortfolioValuationEvent(Event):
    total_value: float
    cash: float
    position_count: int
```

## 类型定义

### 常用类型

```python
# 日期类型
from datetime import date

# 数据帧类型
import polars as pl
DataFrame = pl.DataFrame
Series = pl.Series

# 订单方向
Side = Literal["buy", "sell"]

# 持仓字典
Positions = dict[str, Position]
PositionViews = dict[str, PositionView]

# 行情字典
Bars = dict[str, DayBar]
```
