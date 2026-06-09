from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING


if TYPE_CHECKING:
    from aquant.market.bar import DayBar
    from aquant.matching.order import Order
    from aquant.portfolio.portfolio import Portfolio


class Guard(ABC):
    @abstractmethod
    def check(self, order: Order, bar: DayBar, portfolio: Portfolio) -> bool: ...


class HaltGuard(Guard):
    """防御性安全网——Matcher 步骤一已过滤停牌，此处作为二次保障。"""

    def check(self, order: Order, bar: DayBar, portfolio: Portfolio) -> bool:
        return not (bar.is_halted or bar.open <= 0)


class LimitGuard(Guard):
    """开盘价触及涨跌停板时拒绝委托。"""

    def check(self, order: Order, bar: DayBar, portfolio: Portfolio) -> bool:
        if order.side == "buy" and bar.open >= bar.up_limit:
            return False
        return not (order.side == "sell" and bar.open <= bar.down_limit)


class T1Guard(Guard):
    """将买入委托标记为当日不可卖出（T+1 规则）。"""

    def check(self, order: Order, bar: DayBar, portfolio: Portfolio) -> bool:
        if order.side == "buy":
            order.locked = True
        return True


class AvailableSharesGuard(Guard):
    """卖出量截断至当日可卖份额，并按手数取整。"""

    def _lot_size_for(self, symbol: str) -> int:
        return 200 if symbol.startswith("688") else 100

    def check(self, order: Order, bar: DayBar, portfolio: Portfolio) -> bool:
        if order.side != "sell":
            return True

        pos = portfolio.positions.get(order.symbol)
        if pos is None:
            return False

        lot = self._lot_size_for(order.symbol)
        max_shares = pos.tradeable_shares
        order.shares = min(order.shares, max_shares)
        order.shares = (order.shares // lot) * lot

        return order.shares > 0


class CashGuard(Guard):
    """资金不足时缩减买入量，并自动对齐手数。

    使用实际成交价（含滑点）计算最大可买量，避免因滑点导致现金变负。
    先假设佣金按比例收取，验证是否达到最低佣金门槛：
    - 若达到：按比例佣金计算结果有效
    - 若未达到：说明实际按最低佣金收取，改用固定佣金重新计算
    """

    def __init__(self, commission_rate: float, min_commission: float, slippage_rate: float) -> None:
        self.commission_rate = commission_rate
        self.min_commission = min_commission
        self.slippage_rate = slippage_rate

    def _lot_size_for(self, symbol: str) -> int:
        return 200 if symbol.startswith("688") else 100

    def check(self, order: Order, bar: DayBar, portfolio: Portfolio) -> bool:
        if order.side != "buy":
            return True

        lot = self._lot_size_for(order.symbol)
        # 用实际成交价（含滑点），与 Matcher 结算时保持一致
        fill_price = bar.open * (1 + self.slippage_rate)
        available = portfolio.cash

        if available <= 0:
            return False

        # 先假设按比例收佣：总成本 = n x fill_price x (1 + rate)
        n = int(available / (fill_price * (1 + self.commission_rate)) / lot) * lot
        commission = n * fill_price * self.commission_rate

        if commission < self.min_commission:
            # 实际按最低佣金收，重新计算：总成本 = n x fill_price + min_commission
            n = int(max(available - self.min_commission, 0) / fill_price / lot) * lot

        order.shares = min(order.shares, n)
        return order.shares >= lot


class VolumeCapGuard(Guard):
    """单笔委托量不超过当日成交量的指定比例，默认关闭（ratio=1.0）。"""

    def __init__(self, ratio: float = 1.0) -> None:
        self.ratio = ratio

    def _lot_size_for(self, symbol: str) -> int:
        return 200 if symbol.startswith("688") else 100

    def check(self, order: Order, bar: DayBar, portfolio: Portfolio) -> bool:
        if self.ratio >= 1.0:
            return True
        lot = self._lot_size_for(order.symbol)
        max_shares = int(bar.volume * self.ratio)
        if order.shares > max_shares:
            # 截断后按手数对齐，防止产生无法正常卖出的零散股
            order.shares = (max_shares // lot) * lot
        return order.shares > 0


class DelistGuard(Guard):
    """禁止买入已退市标的。"""

    def check(self, order: Order, bar: DayBar, portfolio: Portfolio) -> bool:
        return not (order.side == "buy" and bar.is_delisted)


DEFAULT_GUARD_CHAIN: list[type[Guard]] = [HaltGuard, LimitGuard, T1Guard, AvailableSharesGuard, CashGuard, VolumeCapGuard, DelistGuard]
