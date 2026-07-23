from __future__ import annotations

import math
from typing import TYPE_CHECKING, Literal

from aquant.log import get_logger
from aquant.matching.cost import CostModel
from aquant.matching.guards import AvailableSharesGuard, CashGuard, Guard, HaltGuard, LimitGuard, T1Guard, VolumeCapGuard
from aquant.matching.order import Order
from aquant.matching.rules import StockRules, TradingRules
from aquant.strategy.signal import Signal


logger = get_logger(__name__)


if TYPE_CHECKING:
    from datetime import date

    from aquant.events.bus import MessageBus
    from aquant.market.bar import DayBar
    from aquant.portfolio.portfolio import Portfolio


class Matcher:
    def __init__(self, cost_model: CostModel, rebalance_threshold: float = 0.0, volume_cap_ratio: float = 1.0, guards: list[Guard] | None = None, bus: MessageBus | None = None, trading_rules: TradingRules | None = None) -> None:
        self.cost_model = cost_model
        self.rebalance_threshold = rebalance_threshold
        self._bus = bus  # 可选的消息总线，用于发布成交事件

        # 新增：交易规则（默认使用 A 股规则，向后兼容）
        if trading_rules is None:
            self._trading_rules = StockRules(commission_rate=cost_model.commission_rate, min_commission=cost_model.min_commission, stamp_duty_rate=cost_model.stamp_duty_rate, slippage_rate=cost_model.slippage_rate)
        else:
            self._trading_rules = trading_rules

        # 如果未提供 guards，使用默认配置
        if guards is None:
            self._guards: list[Guard] = [HaltGuard(), LimitGuard(), T1Guard(), AvailableSharesGuard(), CashGuard(cost_model.commission_rate, cost_model.min_commission, cost_model.slippage_rate), VolumeCapGuard(volume_cap_ratio)]
        else:
            self._guards = guards

    def execute(self, signals: list[Signal], portfolio: Portfolio, bars: dict[str, DayBar], dt: date, rebalance_mode: str = "incremental") -> None:
        """执行信号列表，结算所有委托。

        replace 模式下，持仓中未出现在 signals 的标的自动补 weight=0 清仓。
        incremental 模式下只处理 signals 中显式列出的标的。

        执行分两遍进行：
        1. 先处理所有减仓/清仓信号（现金流入）
        2. 再执行买入/加仓
        """
        # 在分类和目标仓位计算前快照一次组合净值，作为本批次的统一基准。
        # 用昨收估值（FILL 阶段 portfolio.total_value 尚未以今日开盘价更新），
        # 与 current_weight 分子 last_close 保持时间基准一致。
        base_value = portfolio.total_value

        # 组合价值非正（极端亏损或数据异常）时无法计算目标仓位，跳过所有委托
        if base_value <= 0:
            return

        # 过滤无效信号：weight < 0（做空，当前版本不支持）静默丢弃并记录警告
        invalid = [s for s in signals if s.weight < 0]
        if invalid:
            logger.warning("信号 weight < 0，当前版本不支持做空，已丢弃", symbols=[s.symbol for s in invalid], dt=dt)
            signals = [s for s in signals if s.weight >= 0]

        # 重复 symbol 警告：同一标的出现多条信号时，各条独立执行，前条成交后仓位更新，
        # 后条基于更新后的仓位继续处理，可实现"先止损再建仓"等分步调仓语义。
        symbol_counts: dict[str, int] = {}
        for s in signals:
            symbol_counts[s.symbol] = symbol_counts.get(s.symbol, 0) + 1
        dup_symbols = [sym for sym, cnt in symbol_counts.items() if cnt > 1]
        if dup_symbols:
            logger.warning("信号中存在重复 symbol，各条将依序独立执行", symbols=dup_symbols, dt=dt)

        # 校验权重之和：超过 1 时后排信号会因现金不足被静默截断，发出警告
        total_weight = sum(s.weight for s in signals)
        if total_weight > 1.0 + 1e-9:
            logger.warning("信号权重之和超过 1.0，后排信号可能因现金不足被截断，请检查策略是否正确归一化", total_weight=round(total_weight, 6), dt=dt)

        if rebalance_mode == "replace":
            signal_symbols = {s.symbol for s in signals}
            # 一次性构造清仓信号列表，避免循环内重复重建 signals（O(n²)）
            extra = [Signal(symbol=symbol, weight=0.0, signal_date=dt) for symbol in portfolio.symbols if symbol not in signal_symbols]
            if extra:
                signals = [*signals, *extra]

        # 在处理任何委托前，用当前持仓快照计算各信号的方向，避免批次内成交改变分类
        def _is_sell(s: Signal) -> bool:
            pos = portfolio.positions.get(s.symbol)
            if pos is None:
                return False  # 新建仓，属于买入
            current_weight = pos.shares * pos.last_close / base_value
            return s.weight < current_weight

        sell_signals = [s for s in signals if _is_sell(s)]
        buy_signals = [s for s in signals if not _is_sell(s)]

        # 第一遍：卖出/减仓
        for signal in sell_signals:
            self._process_one(signal, portfolio, bars, base_value, dt, side="sell")

        # 第二遍：买入/加仓
        for signal in buy_signals:
            self._process_one(signal, portfolio, bars, base_value, dt, side="buy")

    def _process_one(self, signal: Signal, portfolio: Portfolio, bars: dict[str, DayBar], base_value: float, dt: date, side: Literal["buy", "sell"]) -> None:
        """处理单条信号，生成并结算委托。

        base_value: 批次起始组合净值（昨收估值），用于计算目标股数和 current_weight，
            保持时间基准一致。target_shares 基于 base_value * signal.weight 计算，
            与文档中"weight 相对于 context.total_value"的语义一致。
        side: 调用方已确定的交易方向（"buy" 或 "sell"），无需在内部重新推断
        """
        bar = bars.get(signal.symbol)
        if bar is None or bar.is_halted or bar.open <= 0:
            return

        pos = portfolio.positions.get(signal.symbol)
        current_shares = pos.shares if pos else 0

        # 按方向选估算价：买入用含买入滑点的价格，卖出用含卖出滑点的价格，
        # 保证 target_shares 与实际结算价基准一致，避免卖出时股数偏多或买入时超额。
        # weight=0 清仓时 target_shares=0，est_fill_price 不参与分子，用卖出价占位无影响。
        est_fill_price = self.cost_model.sell_fill_price(bar.open) if side == "sell" else self.cost_model.buy_fill_price(bar.open)
        target_shares = math.floor(base_value * signal.weight / est_fill_price / 100) * 100

        # 调仓阈值检查：weight=0 清仓指令直接放行；其余按 current_weight 与目标的偏差判断
        if signal.weight != 0.0 and self.rebalance_threshold > 0.0:
            current_weight = current_shares * pos.last_close / base_value if pos else 0.0
            if abs(signal.weight - current_weight) < self.rebalance_threshold:
                return

        delta_shares = target_shares - current_shares
        if delta_shares == 0:
            return

        # 方向一致性校验：高开时 last_close 远低于 open，可能导致分类为 sell 的信号
        # 计算出 target_shares >= current_shares（delta > 0），方向与 side 矛盾，直接跳过。
        # 该场景下无需操作——目标权重已隐含在当前仓位内，市场价格变动使其自然达标。
        if (side == "sell" and delta_shares > 0) or (side == "buy" and delta_shares < 0):
            return

        order = Order(symbol=signal.symbol, side=side, shares=abs(delta_shares), liquidate=(target_shares == 0))

        passed = all(g.check(order, bar, portfolio) for g in self._guards)
        if not passed or order.shares <= 0:
            return

        if side == "buy":
            fill_price = self.cost_model.buy_fill_price(bar.open)
            value = order.shares * fill_price
            commission, stamp_duty = self.cost_model.compute_buy(value)
        else:
            fill_price = self.cost_model.sell_fill_price(bar.open)
            value = order.shares * fill_price
            commission, stamp_duty = self.cost_model.compute_sell(value)

        portfolio.apply_fill(symbol=order.symbol, side=order.side, shares=order.shares, fill_price=fill_price, commission=commission, stamp_duty=stamp_duty, locked=order.locked, dt=dt)

        # 发布订单成交事件（如果消息总线可用）
        if self._bus is not None:
            from aquant.events.event import OrderFilledEvent

            self._bus.publish("order.filled", OrderFilledEvent(date=dt, symbol=order.symbol, side=order.side, shares=order.shares, fill_price=fill_price, commission=commission, stamp_duty=stamp_duty))
