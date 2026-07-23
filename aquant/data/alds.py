"""基于 ALDS 的 DataSource 实现。

ALDS (A-share Local Data System) 是本地 A 股数据管理系统。
"""

from __future__ import annotations

from functools import cached_property
from typing import TYPE_CHECKING

import polars as pl

from aquant.data.source import DataSource
from aquant.market.bar import DayBar


if TYPE_CHECKING:
    from datetime import date
    from typing import Any


class ALDSDataSource(DataSource):
    """从 ALDS 获取 A 股行情数据的数据源。

    使用示例::

        data_source = ALDSDataSource()
        bars = data_source.load_bars(date(2024, 1, 2), {"000001.SZ", "600000.SH"})
    """

    def __init__(self):
        """初始化 ALDS 数据源。"""
        try:
            import alds  # type: ignore[import-not-found]

            self._alds: Any = alds
        except ImportError as e:
            raise ImportError("需要安装 alds 库。请运行: pip install alds") from e

        # 缓存：年份 -> {日期 -> DataFrame}
        self._year_cache: dict[int, dict[date, pl.DataFrame]] = {}

    @cached_property
    def trading_days_df(self) -> pl.DataFrame:
        """获取交易日历。"""
        # 从 ALDS 获取交易日历
        calendar = self._alds.get_trading_calendar()
        return pl.DataFrame({"date": calendar}).with_columns(pl.col("date").cast(pl.Date))

    def load_calendar(self, start: date, end: date) -> list[date]:
        """加载交易日历。

        参数
        ----
        start : date
            起始日期
        end : date
            结束日期

        返回
        ----
        list[date]
            交易日列表（升序）
        """
        days = self.trading_days_df.filter(pl.col("date").is_between(start, end)).sort("date").get_column("date").to_list()
        return days

    def _year_bars(self, year: int) -> dict[date, pl.DataFrame]:
        """按年加载并缓存行情数据。

        参数
        ----
        year : int
            年份

        返回
        ----
        dict[date, pl.DataFrame]
            日期 -> 当日所有股票行情的字典
        """
        cached = self._year_cache.get(year)
        if cached is not None:
            return cached

        # 从 ALDS 加载整年数据
        df = self._alds.get_bars(
            start=f"{year}-01-01",
            end=f"{year}-12-31",
            adjust="none",  # 不复权
        )

        if df is None or len(df) == 0:
            self._year_cache[year] = {}
            return self._year_cache[year]

        # 转换为 polars DataFrame
        df = pl.from_pandas(df)

        # 确保列名符合预期
        df = df.rename({"symbol": "instrument", "upper_limit": "up_limit", "lower_limit": "down_limit", "suspended": "is_halted"})

        # 类型转换
        df = df.with_columns(pl.col("date").cast(pl.Date), pl.col("is_halted").fill_null(False).cast(pl.Boolean))

        # 按日期分组
        by_date = {k[0]: v for k, v in df.partition_by("date", as_dict=True).items()}

        self._year_cache[year] = by_date
        return by_date

    def load_bars(self, dt: date, symbols: set[str]) -> dict[str, DayBar]:
        """加载指定日期的行情数据。

        参数
        ----
        dt : date
            交易日期
        symbols : set[str]
            股票代码集合

        返回
        ----
        dict[str, DayBar]
            股票代码 -> 行情数据的字典
        """
        # 从缓存中获取当日数据
        day_all = self._year_bars(dt.year).get(dt)
        if day_all is None:
            return {}

        # 筛选指定股票
        day_df = day_all.filter(pl.col("instrument").is_in(symbols))

        result: dict[str, DayBar] = {}
        for row in day_df.iter_rows(named=True):
            sym = row["instrument"]
            result[sym] = DayBar(symbol=sym, date=row["date"], open=row["open"], close=row["close"], high=row["high"], low=row["low"], volume=row["volume"], up_limit=row["up_limit"], down_limit=row["down_limit"], is_halted=row["is_halted"])

        return result

    def load_adjustments(self, start: date, end: date) -> list:
        """加载复权数据。

        参数
        ----
        start : date
            起始日期
        end : date
            结束日期

        返回
        ----
        list
            复权事件列表
        """
        # TODO: 实现从 ALDS 加载复权数据
        return []

    def load_delisted(self, start: date, end: date) -> dict[date, list[str]]:
        """加载退市数据。

        参数
        ----
        start : date
            起始日期
        end : date
            结束日期

        返回
        ----
        dict[date, list[str]]
            日期 -> 退市股票列表的字典
        """
        # TODO: 实现从 ALDS 加载退市数据
        return {}

