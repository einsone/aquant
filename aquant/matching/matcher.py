from __future__ import annotations

import math
from typing import TYPE_CHECKING

from aquant.log import get_logger
from aquant.matching.cost import CostModel
from aquant.matching.guards import AvailableSharesGuard, CashGuard, DelistGuard, Guard, HaltGuard, LimitGuard, T1Guard, VolumeCapGuard
from aquant.matching.order import Order
from aquant.strategy.signal import Signal


logger = get_logger(__name__)


if TYPE_CHECKING:
    from datetime import date

    from aquant.market.bar import DayBar
    from aquant.portfolio.portfolio import Portfolio


class Matcher:
    def __init__(self, cost_model: CostModel, cash_buffer: float = 0.02, rebalance_threshold: float = 0.0, volume_cap_ratio: float = 1.0) -> None:
        self.cost_model = cost_model
        self.cash_buffer = cash_buffer
        self.rebalance_threshold = rebalance_threshold
        self._guards: list[Guard] = [HaltGuard(), LimitGuard(), T1Guard(), AvailableSharesGuard(), CashGuard(cost_model.commission_rate, cost_model.min_commission, cost_model.slippage_rate), VolumeCapGuard(volume_cap_ratio), DelistGuard()]

    def _lot_size_for(self, symbol: str) -> int:
        return 200 if symbol.startswith("688") else 100

    def execute(self, signals: list[Signal], portfolio: Portfolio, bars: dict[str, DayBar], base_value: float, dt: date, rebalance_mode: str = "incremental") -> None:
        """执行信号列表，结算所有委托。

        replace 模式下，持仓中未出现在 signals 的标的自动补 weight=0 清仓。
        incremental 模式下只处理 signals 中显式列出的标的。
        """
        # 组合价值非正（极端亏损或数据异常）时无法计算目标仓位，跳过所有委托
        if base_value <= 0:
            return

        # 校验权重之和：超过 1 时后排信号会因现金不足被静默截断，发出警告
        total_weight = sum(s.weight for s in signals)
        if total_weight > 1.0 + 1e-9:
            logger.warning("信号权重之和超过 1.0，后排信号可能因现金不足被截断，请检查策略是否正确归一化", total_weight=round(total_weight, 6), dt=dt)

        if rebalance_mode == "replace":
            signal_symbols = {s.symbol for s in signals}
            for symbol in list(portfolio.symbols):
                if symbol not in signal_symbols:
                    # signal_date 用成交日（dt，即 T+1），而非信号生成日（T）
                    signals = [*signals, Signal(symbol=symbol, weight=0.0, signal_date=dt)]

        available_capital = base_value * (1 - self.cash_buffer)

        # 卖出优先：先处理 weight=0 或减仓信号，释放现金后再处理买入
        # 避免资金轮换时新买入因现金不足被 CashGuard 截断
        def _sort_key(s: Signal) -> int:
            pos = portfolio.positions.get(s.symbol)
            current_shares = pos.shares if pos else 0
            bar = bars.get(s.symbol)
            if bar is None or bar.open <= 0:
                return 1
            lot = self._lot_size_for(s.symbol)
            est_fill_price = self.cost_model.buy_fill_price(bar.open)
            target = math.floor(available_capital * s.weight / est_fill_price / lot) * lot
            return 0 if target < current_shares else 1

        signals = sorted(signals, key=_sort_key)

        for signal in signals:
            bar = bars.get(signal.symbol)
            if bar is None or bar.is_halted or bar.open <= 0:
                continue

            lot = self._lot_size_for(signal.symbol)
            # 用买入成交价（含滑点）计算目标股数，与实际结算价保持一致，
            # 避免按 open 算出的股数在成交时超出 available_capital
            est_fill_price = self.cost_model.buy_fill_price(bar.open)
            target_shares = math.floor(available_capital * signal.weight / est_fill_price / lot) * lot

            pos = portfolio.positions.get(signal.symbol)
            current_shares = pos.shares if pos else 0
            # 用 last_close 与 base_value（昨日收盘估值）保持时间基准一致，
            # 避免分子用今日 open、分母用昨日收盘导致 delta_weight 失真
            last_price = pos.last_close if pos else bar.open
            current_weight = current_shares * last_price / base_value if base_value > 0 else 0.0
            delta_weight = signal.weight - current_weight

            # weight=0 是明确的清仓指令，绕过调仓阈值；否则微小偏差不触发交易
            if signal.weight != 0.0 and abs(delta_weight) < self.rebalance_threshold:
                continue

            delta_shares = target_shares - current_shares
            if delta_shares == 0:
                continue

            side = "buy" if delta_shares > 0 else "sell"
            order = Order(symbol=signal.symbol, side=side, shares=abs(delta_shares))

            passed = all(g.check(order, bar, portfolio) for g in self._guards)
            if not passed or order.shares <= 0:
                continue

            if side == "buy":
                fill_price = self.cost_model.buy_fill_price(bar.open)
                value = order.shares * fill_price
                commission, stamp_duty = self.cost_model.compute_buy(value)
            else:
                fill_price = self.cost_model.sell_fill_price(bar.open)
                value = order.shares * fill_price
                commission, stamp_duty = self.cost_model.compute_sell(value)

            portfolio.apply_fill(symbol=order.symbol, side=order.side, shares=order.shares, fill_price=fill_price, commission=commission, stamp_duty=stamp_duty, locked=order.locked, dt=dt)
