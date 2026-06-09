from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Literal


if TYPE_CHECKING:
    from datetime import date


@dataclass
class Position:
    """单个标的的持仓状态（可变，由框架内部维护）。

    属性：
        symbol: 标的代码。
        shares: 当前持有的总股数。
        tradeable_shares: 当日可卖出的股数。买入当日为 0（T+1 规则），
            次日 DAY_START 阶段重置为 shares。送股新增的份额同样当日不可卖。
        cost_basis: 单股全成本（元/股），含买入佣金均摊。多次买入时加权平均。
            用于卖出时计算 pnl：pnl = (卖出价 - cost_basis) x 股数 - 卖出成本。
            反复收取现金分红后可能为负（属正常会计现象，不做截断）。
        market_value: 持仓市值（元），由 take_snapshot 每日收盘后更新。
            停牌时使用 last_close 估值。
        last_close: 最近一次有效收盘价（元/股）。用于停牌期间的估值。
            建仓时初始化为成交价，非停牌日的 take_snapshot 时更新为当日收盘价。
    """

    symbol: str
    shares: int
    tradeable_shares: int
    cost_basis: float
    market_value: float
    last_close: float


@dataclass(frozen=True)
class PositionView:
    """策略可见的只读持仓快照，通过 Context.positions 访问。

    字段含义与 Position 相同，但不可修改。
    """

    symbol: str
    shares: int
    tradeable_shares: int
    cost_basis: float
    market_value: float
    last_close: float

    @classmethod
    def from_position(cls, pos: Position) -> PositionView:
        return cls(symbol=pos.symbol, shares=pos.shares, tradeable_shares=pos.tradeable_shares, cost_basis=pos.cost_basis, market_value=pos.market_value, last_close=pos.last_close)


@dataclass
class NavRecord:
    """每日净值快照，回测结束后批量计算绩效指标。

    属性：
        date: 快照日期。
        total: 组合总市值（现金 + 所有持仓市值）。
        cash: 当日现金余额。
        position_count: 当日持仓标的数量。
    """

    date: date
    total: float
    cash: float
    position_count: int = 0


@dataclass
class Trade:
    """单笔成交记录，存入 Portfolio.trade_log。

    属性：
        date: 成交日期。
        symbol: 标的代码。
        side: "buy" 买入 / "sell" 卖出。
        shares: 成交股数。
        price: 成交价（已含滑点）。
        commission: 本笔佣金（元）。
        stamp_duty: 本笔印花税（元），买入为 0。
        pnl: 本笔盈亏（元）。卖出时按均价成本计算：
            (成交价 - cost_basis) x shares - commission - stamp_duty。
            cost_basis 含买入佣金（均摊到每股），commission 和 stamp_duty
            为本次卖出的成本，不会双重计算。买入时 pnl = 0。
    """

    date: date
    symbol: str
    side: Literal["buy", "sell"]
    shares: int
    price: float
    commission: float
    stamp_duty: float
    pnl: float = field(default=0.0)
