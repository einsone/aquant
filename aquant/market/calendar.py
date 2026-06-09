from __future__ import annotations

from typing import TYPE_CHECKING


if TYPE_CHECKING:
    from datetime import date


def is_trading_day(dt: date, trading_days: list[date]) -> bool:
    return dt in trading_days


class Calendar:
    """交易日历。"""

    def __init__(self) -> None:
        self._days: list[date] = []
        self._day_set: set[date] = set()

    def load(self, trading_days: list[date]) -> None:
        self._days = sorted(trading_days)
        self._day_set = set(self._days)

    def is_trading_day(self, dt: date) -> bool:
        return dt in self._day_set

    def trading_days_between(self, start: date, end: date) -> list[date]:
        return [d for d in self._days if start <= d <= end]

    def __contains__(self, dt: date) -> bool:
        return dt in self._day_set
