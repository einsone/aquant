"""交易规则抽象模块，支持多品种交易。

不同品种有不同的交易规则：
- 股票：T+1、印花税、100 股为一手
- 期货：T+0、手续费、1 手为最小单位
- 期权：T+0、不同的手续费结构

通过 TradingRules 抽象，框架可以支持任意品种，无需修改核心代码。
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING


if TYPE_CHECKING:
    from aquant.portfolio.position import Position


class TradingRules(ABC):
    """交易规则抽象基类。

    子类需实现具体品种的交易规则，包括：
    - T+N 规则：是否可以当日卖出
    - 交易成本：佣金、印花税、手续费等
    - 最小交易单位：股票 100 股，期货 1 手等
    """

    @abstractmethod
    def can_trade_today(self, symbol: str, position: Position | None) -> bool:
        """判断今日是否可以交易该标的。

        参数
        ----
        symbol:
            标的代码
        position:
            当前持仓，None 表示无持仓

        返回
        ----
        True 表示可以交易（买入或卖出）
        """

    @abstractmethod
    def compute_cost(self, side: str, value: float) -> tuple[float, float]:
        """计算交易成本。

        参数
        ----
        side:
            "buy" 或 "sell"
        value:
            成交金额（shares * price）

        返回
        ----
        (佣金, 印花税/手续费) 元组
        """

    @abstractmethod
    def get_lot_size(self, symbol: str) -> int:
        """获取最小交易单位。

        参数
        ----
        symbol:
            标的代码

        返回
        ----
        最小交易单位（股票 100 股，期货 1 手）
        """


class StockRules(TradingRules):
    """A 股交易规则。

    - T+1：买入当日不可卖出
    - 佣金：按成交金额双边收取，有最低佣金
    - 印花税：卖出单边收取
    - 滑点：按成交金额比例
    - 最小单位：100 股（一手）
    """

    def __init__(self, commission_rate: float = 0.0003, min_commission: float = 5.0, stamp_duty_rate: float = 0.001, slippage_rate: float = 0.0005) -> None:
        """初始化 A 股交易规则。

        参数
        ----
        commission_rate:
            佣金费率，按成交金额双边收取。默认万分之三（0.0003）。
        min_commission:
            单笔最低佣金（元）。默认 5 元。
        stamp_duty_rate:
            印花税税率，仅卖出单边收取。默认千分之一（0.001）。
        slippage_rate:
            滑点比例，按成交金额估算市场冲击成本。默认万分之五（0.0005）。
        """
        self.commission_rate = commission_rate
        self.min_commission = min_commission
        self.stamp_duty_rate = stamp_duty_rate
        self.slippage_rate = slippage_rate

    def can_trade_today(self, symbol: str, position: Position | None) -> bool:
        """A 股 T+1 规则：买入当日不可卖出。"""
        if position is None:
            return True  # 无持仓，可以买入
        return position.tradeable_shares > 0  # 有可卖股数才能卖出

    def compute_cost(self, side: str, value: float) -> tuple[float, float]:
        """计算 A 股交易成本（佣金 + 印花税）。"""
        commission = max(value * self.commission_rate, self.min_commission)
        stamp_duty = value * self.stamp_duty_rate if side == "sell" else 0.0
        return commission, stamp_duty

    def get_lot_size(self, symbol: str) -> int:
        """A 股最小交易单位：100 股。"""
        return 100

    def buy_fill_price(self, open_price: float) -> float:
        """买入成交价（含滑点）。"""
        return open_price * (1 + self.slippage_rate)

    def sell_fill_price(self, open_price: float) -> float:
        """卖出成交价（含滑点）。"""
        return open_price * (1 - self.slippage_rate)


class FuturesRules(TradingRules):
    """期货交易规则。

    - T+0：当日可以多次买卖
    - 手续费：按成交金额或固定每手收取
    - 保证金：按合约价值比例
    - 最小单位：1 手
    """

    def __init__(self, fee_rate: float = 0.00005, fee_per_lot: float = 0.0, slippage_rate: float = 0.0002) -> None:
        """初始化期货交易规则。

        参数
        ----
        fee_rate:
            手续费率，按成交金额收取。默认万分之 0.5（0.00005）。
        fee_per_lot:
            每手固定手续费（元）。默认 0（按比例收取）。
        slippage_rate:
            滑点比例。默认万分之 2（0.0002）。
        """
        self.fee_rate = fee_rate
        self.fee_per_lot = fee_per_lot
        self.slippage_rate = slippage_rate

    def can_trade_today(self, symbol: str, position: Position | None) -> bool:
        """期货 T+0：随时可交易。"""
        return True

    def compute_cost(self, side: str, value: float) -> tuple[float, float]:
        """计算期货交易成本（手续费）。

        返回
        ----
        (手续费, 0.0)，期货无印花税，第二个值为 0
        """
        fee = value * self.fee_rate
        # 注意：fee_per_lot 需要知道手数，这里简化处理，只按比例
        return fee, 0.0

    def get_lot_size(self, symbol: str) -> int:
        """期货最小交易单位：1 手。"""
        return 1

    def buy_fill_price(self, open_price: float) -> float:
        """买入成交价（含滑点）。"""
        return open_price * (1 + self.slippage_rate)

    def sell_fill_price(self, open_price: float) -> float:
        """卖出成交价（含滑点）。"""
        return open_price * (1 - self.slippage_rate)
