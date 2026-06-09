from __future__ import annotations

from typing import TYPE_CHECKING


if TYPE_CHECKING:
    from aquant.core.engine import BacktestConfig


class CostModel:
    """交易成本计算模型。

    封装佣金、印花税、滑点的计算逻辑，由 Matcher 和 Adjuster.force_close 使用。

    属性：
        commission_rate: 佣金费率，按成交金额双边收取。例：0.0003 = 万分之三。
        min_commission: 单笔最低佣金（元）。小额交易按此收取，防止佣金过低失真。
        stamp_duty_rate: 印花税税率（A 股证券交易税），仅卖出单边收取。
            例：0.001 = 千分之一。历史上有过 0.3%（2008 年前）→ 0.1%（2008）→ 0.05%（2023）。
        slippage_rate: 滑点比例，模拟委托对市场的冲击成本。
            买入时成交价 = open x (1 + slippage_rate)，
            卖出时成交价 = open x (1 - slippage_rate)。
    """

    def __init__(self, commission_rate: float = 0.0003, min_commission: float = 5.0, stamp_duty_rate: float = 0.001, slippage_rate: float = 0.0005) -> None:
        self.commission_rate = commission_rate
        self.min_commission = min_commission
        self.stamp_duty_rate = stamp_duty_rate
        self.slippage_rate = slippage_rate

    @classmethod
    def from_config(cls, config: BacktestConfig) -> CostModel:
        """从 BacktestConfig 构造，避免 engine 里手写字段映射。"""
        return cls(commission_rate=config.commission_rate, min_commission=config.min_commission, stamp_duty_rate=config.stamp_duty_rate, slippage_rate=config.slippage_rate)

    def buy_fill_price(self, open_price: float) -> float:
        """买入成交价 = 开盘价 x (1 + 滑点)。"""
        return open_price * (1 + self.slippage_rate)

    def sell_fill_price(self, open_price: float) -> float:
        """卖出成交价 = 开盘价 x (1 - 滑点)。"""
        return open_price * (1 - self.slippage_rate)

    def compute_buy(self, value: float) -> tuple[float, float]:
        """返回 (佣金, 印花税)。买入不收印花税，印花税始终为 0。"""
        commission = max(value * self.commission_rate, self.min_commission)
        return commission, 0.0

    def compute_sell(self, value: float) -> tuple[float, float]:
        """返回 (佣金, 印花税)。印花税 = 成交金额 x stamp_duty_rate，仅卖出收取。"""
        commission = max(value * self.commission_rate, self.min_commission)
        stamp_duty = value * self.stamp_duty_rate
        return commission, stamp_duty
