from __future__ import annotations

from dataclasses import dataclass, field
from enum import IntEnum
from typing import TYPE_CHECKING


if TYPE_CHECKING:
    from datetime import date


class Phase(IntEnum):
    DAY_START = 10
    FILL = 15  # 执行前一交易日缓存的信号，用 T+1 开盘价成交
    ADJUSTMENT = 20
    DELIST = 30
    SIGNAL = 40
    VALUATION = 50


@dataclass
class Event:
    date: date
    phase: Phase

    def __lt__(self, other: Event) -> bool:
        return (self.date, self.phase) < (other.date, other.phase)

    def __le__(self, other: Event) -> bool:
        return (self.date, self.phase) <= (other.date, other.phase)

    def __gt__(self, other: Event) -> bool:
        return (self.date, self.phase) > (other.date, other.phase)

    def __ge__(self, other: Event) -> bool:
        return (self.date, self.phase) >= (other.date, other.phase)

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Event):
            return NotImplemented
        return (self.date, self.phase) == (other.date, other.phase)

    def __hash__(self) -> int:
        return hash((self.date, self.phase))


@dataclass
class DayStartEvent(Event):
    phase: Phase = field(default=Phase.DAY_START, init=False)


@dataclass
class FillEvent(Event):
    """执行前一交易日 SIGNAL 阶段缓存的信号，以当日（T+1）开盘价成交。"""

    phase: Phase = field(default=Phase.FILL, init=False)


@dataclass
class AdjustmentEvent(Event):
    phase: Phase = field(default=Phase.ADJUSTMENT, init=False)


@dataclass
class DelistEvent(Event):
    phase: Phase = field(default=Phase.DELIST, init=False)
    symbols: list[str] = field(default_factory=list)


@dataclass
class SignalEvent(Event):
    phase: Phase = field(default=Phase.SIGNAL, init=False)


@dataclass
class ValuationEvent(Event):
    phase: Phase = field(default=Phase.VALUATION, init=False)


# ---------------------------------------------------------------------------
# 业务事件（用于消息总线）
# ---------------------------------------------------------------------------


@dataclass
class OrderSubmittedEvent(Event):
    """订单提交事件。"""

    symbol: str
    side: str  # "buy" 或 "sell"
    shares: int
    phase: Phase = field(default=Phase.FILL, init=False)


@dataclass
class OrderFilledEvent(Event):
    """订单成交事件。"""

    symbol: str
    side: str  # "buy" 或 "sell"
    shares: int
    fill_price: float
    commission: float
    stamp_duty: float
    phase: Phase = field(default=Phase.FILL, init=False)


@dataclass
class PositionChangedEvent(Event):
    """持仓变动事件。"""

    symbol: str
    old_shares: int
    new_shares: int
    phase: Phase = field(default=Phase.FILL, init=False)


@dataclass
class PortfolioValuationEvent(Event):
    """组合估值事件（每日收盘）。"""

    total_value: float
    cash: float
    position_count: int
    phase: Phase = field(default=Phase.VALUATION, init=False)
