from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING


if TYPE_CHECKING:
    from datetime import date


@dataclass(frozen=True)
class DayBar:
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
    is_delisted: bool
