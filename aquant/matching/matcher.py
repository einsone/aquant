from __future__ import annotations

import math
from typing import TYPE_CHECKING

from aquant.matching.cost import CostModel
from aquant.matching.guards import AvailableSharesGuard, CashGuard, DelistGuard, Guard, HaltGuard, LimitGuard, T1Guard, VolumeCapGuard
from aquant.matching.order import Order
from aquant.strategy.signal import Signal


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
            target = math.floor(available_capital * s.weight / bar.open / lot) * lot
            # 目标股数 < 当前股数 → 净减仓 → 排前执行以释放现金
            # T+1 锁定的仓位实际卖出量由 AvailableSharesGuard 截断，排序不受影响
            return 0 if target < current_shares else 1

        signals = sorted(signals, key=_sort_key)

        for signal in signals:
            bar = bars.get(signal.symbol)
            if bar is None or bar.is_halted or bar.open <= 0:
                continue

            lot = self._lot_size_for(signal.symbol)
            target_shares = math.floor(available_capital * signal.weight / bar.open / lot) * lot

            pos = portfolio.positions.get(signal.symbol)
            current_shares = pos.shares if pos else 0
            current_weight = current_shares * bar.open / base_value if base_value > 0 else 0.0
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
