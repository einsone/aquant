from __future__ import annotations

from typing import TYPE_CHECKING


if TYPE_CHECKING:
    from collections.abc import Callable
    from datetime import date


class Universe:
    """每日可交易标的集合，引擎初始化时一次性加载。"""

    def __init__(self) -> None:
        self._data: dict[date, frozenset[str]] = {}

    def preload(self, start: date, end: date, load_fn: Callable[[date, date], dict[date, frozenset[str]]]) -> None:
        self._data = load_fn(start, end)

    def get(self, dt: date) -> frozenset[str]:
        return self._data.get(dt, frozenset())
