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
    """开盘价触及涨跌停板时拒绝委托。

    使用 1e-6 的容差做浮点比较，避免 A 股价格精度（分）在 float 表示时的微小误差
    导致恰好等于涨跌停价的开盘价被误判为未触板。
    """

    _EPS = 1e-6

    def check(self, order: Order, bar: DayBar, portfolio: Portfolio) -> bool:
        if order.side == "buy" and bar.open >= bar.up_limit - self._EPS:
            return False
        return not (order.side == "sell" and bar.open <= bar.down_limit + self._EPS)


class T1Guard(Guard):
    """将买入委托标记为当日不可卖出（T+1 规则）。"""

    def check(self, order: Order, bar: DayBar, portfolio: Portfolio) -> bool:
        if order.side == "buy":
            order.locked = True
        return True


class AvailableSharesGuard(Guard):
    """卖出量截断至当日可卖份额，并按手数取整。"""

    def check(self, order: Order, bar: DayBar, portfolio: Portfolio) -> bool:
        if order.side != "sell":
            return True

        pos = portfolio.positions.get(order.symbol)
        if pos is None:
            return False

        max_shares = pos.tradeable_shares
        order.shares = min(order.shares, max_shares)
        # 清仓时不按手数取整，直接卖出全部可卖份额，
        # 避免送股/配股产生的非整百股数永远无法清仓
        if not order.liquidate:
            order.shares = (order.shares // 100) * 100

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

    def check(self, order: Order, bar: DayBar, portfolio: Portfolio) -> bool:
        if order.side != "buy":
            return True

        # 用实际成交价（含滑点），与 Matcher 结算时保持一致
        fill_price = bar.open * (1 + self.slippage_rate)
        available = portfolio.cash

        if available <= 0:
            return False

        # 先假设按比例收佣：总成本 = n x fill_price x (1 + rate)
        n = int(available / (fill_price * (1 + self.commission_rate)) / 100) * 100
        commission = n * fill_price * self.commission_rate

        if commission < self.min_commission:
            # 实际按最低佣金收，重新计算：总成本 = n x fill_price + min_commission
            n = int(max(available - self.min_commission, 0) / fill_price / 100) * 100
            # 最低佣金路径同样需要兜底，防止因整数截断导致总成本超出可用资金
            if n > 0 and n * fill_price + self.min_commission > available:
                n = max(n - 100, 0)
        else:
            # 比例路径：验证实际总成本（含佣金）不超出可用资金
            # n * fill_price * rate 可能刚超过 min_commission，但四舍五入后实际成本超出 available
            actual_cost = n * fill_price + commission
            if actual_cost > available:
                n = max(n - 100, 0)

        order.shares = min(order.shares, n)
        return order.shares >= 100


class VolumeCapGuard(Guard):
    """单笔委托量不超过当日成交量的指定比例，默认关闭（ratio=1.0）。"""

    def __init__(self, ratio: float = 1.0) -> None:
        self.ratio = ratio

    def check(self, order: Order, bar: DayBar, portfolio: Portfolio) -> bool:
        if self.ratio >= 1.0:
            return True
        max_shares = int(bar.volume * self.ratio)
        if order.shares > max_shares:
            # 截断后按手数对齐，防止产生无法正常卖出的零散股
            order.shares = (max_shares // 100) * 100
        return order.shares > 0
