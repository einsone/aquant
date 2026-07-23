"""数据预加载器模块。

提供批量数据预加载功能，减少 I/O 次数，提升回测性能。
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from aquant.log import get_logger


if TYPE_CHECKING:
    from datetime import date

    from aquant.data.source import DataSource
    from aquant.market.bar import DayBar


logger = get_logger(__name__)


class DataPreloader:
    """数据预加载器。

    批量预加载多天数据并缓存，减少数据源的频繁访问。

    使用示例::

        preloader = DataPreloader(data_source, trading_days, symbols)
        bars = preloader.get_bars(date(2024, 1, 2))
    """

    def __init__(self, data_source: DataSource, trading_days: list[date], symbols: set[str], batch_size: int = 50):
        """初始化预加载器。

        参数
        ----
        data_source : DataSource
            数据源
        trading_days : list[date]
            交易日列表
        symbols : set[str]
            股票代码集合
        batch_size : int
            每批加载的天数，默认 50
        """
        self.data_source = data_source
        self._cache: dict[date, dict[str, DayBar]] = {}
        self._batch_size = batch_size

        # 批量预加载
        self._preload(trading_days, symbols)

    def _preload(self, trading_days: list[date], symbols: set[str]) -> None:
        """批量加载所有交易日数据。

        参数
        ----
        trading_days : list[date]
            交易日列表
        symbols : set[str]
            股票代码集合
        """
        total_days = len(trading_days)
        logger.info("开始预加载数据", total_days=total_days, symbols_count=len(symbols), batch_size=self._batch_size)

        loaded_count = 0

        # 分批加载（避免内存溢出）
        for i in range(0, len(trading_days), self._batch_size):
            batch = trading_days[i : i + self._batch_size]

            for dt in batch:
                try:
                    self._cache[dt] = self.data_source.load_bars(dt, symbols)
                    loaded_count += 1
                except Exception as e:
                    logger.warning("加载数据失败", date=str(dt), error=str(e))
                    self._cache[dt] = {}

            # 进度日志
            if (i + self._batch_size) % (self._batch_size * 5) == 0 or (i + self._batch_size) >= total_days:
                progress = min(100, int((loaded_count / total_days) * 100))
                logger.info("预加载进度", loaded=loaded_count, total=total_days, progress=f"{progress}%")

        logger.info("预加载完成", total_days=loaded_count, cache_size_mb=self._estimate_cache_size())

    def _estimate_cache_size(self) -> float:
        """估算缓存大小（MB）。

        返回
        ----
        float
            缓存大小估计（MB）
        """
        import sys

        total_size = 0
        for bars in self._cache.values():
            total_size += sys.getsizeof(bars)
            for bar in bars.values():
                total_size += sys.getsizeof(bar)

        return total_size / (1024 * 1024)

    def get_bars(self, dt: date) -> dict[str, DayBar]:
        """从缓存获取指定日期的数据。

        参数
        ----
        dt : date
            交易日期

        返回
        ----
        dict[str, DayBar]
            股票代码 -> 行情数据的字典
        """
        return self._cache.get(dt, {})

    def clear_cache(self) -> None:
        """清空缓存。"""
        self._cache.clear()
        logger.info("缓存已清空")
