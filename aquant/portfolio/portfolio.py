from __future__ import annotations

from typing import TYPE_CHECKING

from aquant.portfolio.position import NavRecord, Position, PositionView, Trade


if TYPE_CHECKING:
    from datetime import date

    from aquant.market.bar import DayBar


class Portfolio:
    """组合状态管理。

    属性：
        cash: 当前可用现金（元）。扣除佣金、印花税、滑点后的净余额。
        positions: 当前所有持仓，以标的代码为键。
            持仓清空（shares == 0）时自动从字典中删除。
        trade_log: 全部成交记录，每次 apply_fill 追加一条。
            用于计算胜率、盈亏比等交易统计指标。
        _daily_nav: 每日净值快照列表，每个交易日收盘后由 take_snapshot 追加。
            回测结束后传给 analytics.metrics.compute_all 批量计算绩效。
    """

    def __init__(self, initial_capital: float) -> None:
        self.cash: float = initial_capital
        self.positions: dict[str, Position] = {}
        self._daily_nav: list[NavRecord] = []
        self.trade_log: list[Trade] = []

    @property
    def total_value(self) -> float:
        """组合总市值 = 现金 + 所有持仓的 market_value 之和。

        基于上一次 take_snapshot 时的收盘价估值，盘中不实时更新。
        """
        return self.cash + sum(p.market_value for p in self.positions.values())

    @property
    def symbols(self) -> set[str]:
        """当前持仓的标的代码集合。"""
        return set(self.positions.keys())

    def reset_tradeable(self) -> None:
        """每日 DAY_START 阶段调用，解锁前一日买入的仓位。

        将所有持仓的 tradeable_shares 重置为 shares，
        使前一日因 T+1 规则锁定的份额在今日可以卖出。
        """
        for pos in self.positions.values():
            pos.tradeable_shares = pos.shares

    def take_snapshot(self, dt: date, bars: dict[str, DayBar]) -> None:
        """每日 VALUATION 阶段调用，更新估值并记录净值快照。

        非停牌标的以当日收盘价更新 last_close 和 market_value。
        停牌标的 market_value 使用上次有效的 last_close 估算。
        """
        for pos in self.positions.values():
            bar = bars.get(pos.symbol)
            if bar and not bar.is_halted:
                pos.last_close = bar.close
            pos.market_value = pos.shares * pos.last_close
        self._daily_nav.append(NavRecord(date=dt, total=self.total_value, cash=self.cash, position_count=len(self.positions)))

    def position_views(self) -> dict[str, PositionView]:
        """返回所有持仓的只读快照，用于构造 Context。"""
        return {s: PositionView.from_position(p) for s, p in self.positions.items()}

    def apply_fill(self, symbol: str, side: str, shares: int, fill_price: float, commission: float, stamp_duty: float, locked: bool, dt: date) -> None:
        """结算一笔成交，更新现金、持仓和交易记录。"""
        if side == "buy":
            self._apply_buy(symbol, shares, fill_price, commission, locked, dt)
        else:
            self._apply_sell(symbol, shares, fill_price, commission, stamp_duty, dt)

    def _apply_buy(self, symbol: str, shares: int, fill_price: float, commission: float, locked: bool, dt: date) -> None:
        value = shares * fill_price
        self.cash -= value + commission

        if symbol in self.positions:
            pos = self.positions[symbol]
            old_total_cost = pos.cost_basis * pos.shares
            pos.shares += shares
            pos.cost_basis = (old_total_cost + shares * fill_price + commission) / pos.shares
            if not locked:
                pos.tradeable_shares += shares
            # 加仓后市值用成交价更新，与首次建仓路径保持一致
            pos.market_value = pos.shares * fill_price
            pos.last_close = fill_price
        else:
            cost_basis = (shares * fill_price + commission) / shares
            self.positions[symbol] = Position(symbol=symbol, shares=shares, tradeable_shares=0 if locked else shares, cost_basis=cost_basis, market_value=shares * fill_price, last_close=fill_price)

        self.trade_log.append(Trade(date=dt, symbol=symbol, side="buy", shares=shares, price=fill_price, commission=commission, stamp_duty=0.0, pnl=0.0))

    def _apply_sell(self, symbol: str, shares: int, fill_price: float, commission: float, stamp_duty: float, dt: date) -> None:
        pos = self.positions[symbol]
        value = shares * fill_price
        self.cash += value - commission - stamp_duty

        pnl = (fill_price - pos.cost_basis) * shares - commission - stamp_duty

        pos.shares -= shares
        pos.tradeable_shares -= shares

        if pos.shares == 0:
            del self.positions[symbol]
        else:
            # 用成交价更新估值，与 _apply_buy 保持一致
            pos.market_value = pos.shares * fill_price
            pos.last_close = fill_price

        self.trade_log.append(Trade(date=dt, symbol=symbol, side="sell", shares=shares, price=fill_price, commission=commission, stamp_duty=stamp_duty, pnl=pnl))
