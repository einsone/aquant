from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING


if TYPE_CHECKING:
    from datetime import date


class AssetType(StrEnum):
    """资产类型枚举。"""

    STOCK = "STOCK"  # 股票
    FUTURE = "FUTURE"  # 期货
    OPTION = "OPTION"  # 期权


@dataclass(frozen=True)
class DayBar:
    """日行情数据。

    属性：
        symbol: 标的代码
        date: 交易日期
        open: 开盘价
        close: 收盘价
        high: 最高价
        low: 最低价
        volume: 成交量
        up_limit: 涨停价
        down_limit: 跌停价
        is_halted: 是否停牌
        asset_type: 资产类型，默认为 STOCK
    """

    symbol: str
    date: date
    open: float
    close: float
    high: float
    low: float
    volume: float
    up_limit: float
    down_limit: float
    is_halted: bool
    asset_type: AssetType = AssetType.STOCK
