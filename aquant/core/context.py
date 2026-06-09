from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING


if TYPE_CHECKING:
    from datetime import date

    from aquant.portfolio.position import PositionView


@dataclass(frozen=True)
class Context:
    """每次策略回调时传入的只读组合状态快照。

    属性：
        current_date: 当前仿真日期（T 日）。策略查询数据时不得超过此日期。
        positions: 当前持仓的只读视图，以标的代码为键。
            每个 PositionView 包含 shares、tradeable_shares、cost_basis、
            market_value、last_close 字段。
        cash: 当前可用现金。
        total_value: cash 加所有持仓 market_value 之和。
            基于前一日收盘价估值——框架在信号生成前不以当日开盘价重新估值。
    """

    current_date: date
    positions: dict[str, PositionView]
    cash: float
    total_value: float
