"""数据管理器模块，提供统一的缓存和数据访问管理。

借鉴 VnPy 的 BarManager / TickManager 分层设计，在 DataSource 之上提供：
- 统一的缓存策略
- 数据预加载
- 多数据源聚合（未来扩展）
"""

from __future__ import annotations

from functools import lru_cache
from typing import TYPE_CHECKING


if TYPE_CHECKING:
    from datetime import date

    from aquant.data.source import DataSource
    from aquant.market.bar import DayBar


class DataManager:
    """数据管理器，协调数据源、缓存、预加载。

    使用示例::

        manager = DataManager(data_source, cache_size=256)

        # 加载数据（自动缓存）
        bars = manager.load_bars(date(2024, 1, 2), {"000001.SZ", "600000.SH"})

        # 预加载区间数据
        manager.preload_range(start, end, symbols)

        # 清空缓存
        manager.clear_cache()
    """

    def __init__(self, primary_source: DataSource, cache_size: int = 128) -> None:
        """初始化数据管理器。

        参数
        ----
        primary_source:
            主数据源
        cache_size:
            LRU 缓存大小，默认 128 个条目
        """
        self._primary = primary_source
        self._cache_size = cache_size

        # 使用 lru_cache 实现缓存（需要参数可哈希）
        self._load_bars_cached = lru_cache(maxsize=cache_size)(self._load_bars_impl)

    def load_bars(self, dt: date, symbols: set[str]) -> dict[str, DayBar]:
        """加载指定日期的行情，带 LRU 缓存。

        参数
        ----
        dt:
            交易日期
        symbols:
            标的代码集合

        返回
        ----
        标的代码 -> DayBar 的字典
        """
        # 将 set 转为 frozenset 以便哈希（lru_cache 要求参数可哈希）
        return self._load_bars_cached(dt, frozenset(symbols))

    def _load_bars_impl(self, dt: date, symbols: frozenset[str]) -> dict[str, DayBar]:
        """实际加载逻辑，由 lru_cache 包装。"""
        return self._primary.load_bars(dt, set(symbols))

    def preload_range(self, start: date, end: date, symbols: set[str]) -> None:
        """预加载指定区间的数据到缓存（可选优化）。

        适用场景：已知策略需要的全部标的和日期，可提前批量加载到缓存。

        参数
        ----
        start:
            起始日期
        end:
            结束日期
        symbols:
            标的代码集合
        """
        calendar = self._primary.load_calendar(start, end)
        for dt in calendar:
            self.load_bars(dt, symbols)

    def clear_cache(self) -> None:
        """清空缓存。"""
        self._load_bars_cached.cache_clear()

    def cache_info(self) -> str:
        """返回缓存统计信息（命中率、大小等）。"""
        info = self._load_bars_cached.cache_info()
        return f"hits={info.hits}, misses={info.misses}, size={info.currsize}/{info.maxsize}"
