"""基于 BigQuant DAI 的 DataSource 实现。

通过 ``bigquantdai`` SDK 的 ``dai.query(sql).arrow()`` 接口按需查询，
避免整表读入内存。表名（如 cn_stock_real_bar1d、cn_stock_status、
cn_stock_basic_info 等）与列名以实际 DAI schema 为准。

依赖::

    pip install bigquantdai
"""

from __future__ import annotations

from functools import cached_property
from typing import TYPE_CHECKING, cast

import polars as pl

from aquant.adjustment.corporate import BonusShares, CashDividend, CorporateAction, RightsIssue
from aquant.data.source import DataSource
from aquant.market.bar import DayBar


if TYPE_CHECKING:
    from datetime import date


class BigQuantDataSource(DataSource):
    """从 BigQuant DAI 拉取行情、企业行动与退市数据的数据源。"""

    def __init__(self, access_key: str, secret_key: str) -> None:
        from bigquantdai import dai

        dai.login(access_key, secret_key)
        self._dai = dai
        # 按年缓存 cn_stock_real_bar1d ⨝ cn_stock_status 的结果，
        # 外层键为年份，内层按交易日切分以便 load_bars O(1) 取当日。
        self._year_cache: dict[int, dict[date, pl.DataFrame]] = {}

    def _query(self, sql: str) -> pl.DataFrame:
        # 统一查询入口：执行 SQL 并将 Arrow 结果转为 polars DataFrame。
        # pl.from_arrow 的 stub 返回 DataFrame | Series，DAI 返回 Arrow Table
        # 故运行时必为 DataFrame；用 cast 收窄类型，无运行时开销。
        return cast("pl.DataFrame", pl.from_arrow(self._dai.query(sql).arrow()))

    @cached_property
    def trading_days_df(self) -> pl.DataFrame:
        sql = "SELECT date FROM trading_days WHERE market_code = 'CN'"
        return self._query(sql).with_columns(pl.col("date").cast(pl.Date))

    @cached_property
    def delisted_df(self) -> pl.DataFrame:
        # 全量加载退市标的：cn_stock_basic_info 中 delist_date 非空者。
        sql = "SELECT instrument, delist_date FROM cn_stock_basic_info WHERE delist_date IS NOT NULL"
        return self._query(sql).with_columns(pl.col("delist_date").cast(pl.Date))

    def load_calendar(self, start: date, end: date) -> list[date]:
        # 从缓存的全量交易日历中筛出 [start, end] 区间，升序返回。
        days = self.trading_days_df.filter(pl.col("date").is_between(start, end)).sort("date").get_column("date").to_list()
        return days

    def _year_bars(self, year: int) -> dict[date, pl.DataFrame]:
        # 整年加载并缓存：以未复权日行情为基表，左连状态表取停牌标志，
        # 构造出 DayBar 所需的全部列；最后按交易日切分，便于 load_bars 取当日。
        cached = self._year_cache.get(year)
        if cached is not None:
            return cached

        sql = f"SELECT b.date, b.instrument, b.open, b.close, b.high, b.low, b.volume, b.upper_limit, b.lower_limit, s.suspended FROM cn_stock_real_bar1d b LEFT JOIN cn_stock_status s ON b.date = s.date AND b.instrument = s.instrument WHERE b.date BETWEEN '{year}-01-01' AND '{year}-12-31'"
        df = self._query(sql)
        if df.is_empty():
            # 该年无行情（区间超出数据范围等），缓存空结果避免重复查询。
            self._year_cache[year] = {}
            return self._year_cache[year]

        df = df.with_columns(
            pl.col("date").cast(pl.Date),
            # suspended 缺失视为未停牌
            pl.col("suspended").fill_null(0).cast(pl.Boolean).alias("is_halted"),
        )
        by_date = {k[0]: v for k, v in df.partition_by("date", as_dict=True).items()}
        self._year_cache[year] = by_date
        return by_date

    def load_bars(self, dt: date, symbols: set[str]) -> dict[str, DayBar]:
        # 从按年缓存中直接取 dt 当日的小表，再筛 symbols。
        # 当日无行情的标的（停牌无 bar、数据缺失）不出现在结果中。
        day_all = self._year_bars(dt.year).get(dt)
        if day_all is None:
            return {}
        day_df = day_all.filter(pl.col("instrument").is_in(symbols))
        result: dict[str, DayBar] = {}
        for row in day_df.iter_rows(named=True):
            sym = row["instrument"]
            result[sym] = DayBar(symbol=sym, date=row["date"], open=row["open"], close=row["close"], high=row["high"], low=row["low"], volume=row["volume"], up_limit=row["upper_limit"], down_limit=row["lower_limit"], is_halted=row["is_halted"])
        return result

    def load_adjustments(self, start: date, end: date) -> list[CorporateAction]:
        # 查询区间内的分红与配股，映射为 CashDividend / BonusShares / RightsIssue。
        # 触发日期（分红/送转的 ex_date、配股的 exright_date）落在 [start, end] 内即纳入，
        # 即使股权登记日早于 start。一行分红记录可能同时含现金和送转，拆成多条。
        actions: list[CorporateAction] = []

        # --- 分红 / 送转 ---
        div_sql = f"SELECT instrument, register_date, ex_date, cash_after_tax, bonus_rate, conversed_rate FROM cn_stock_dividend WHERE ex_date BETWEEN '{start}' AND '{end}'"
        div_df = self._query(div_sql)
        for row in div_df.iter_rows(named=True):
            sym = row["instrument"]
            register_date = row["register_date"]
            ex_date = row["ex_date"]

            cash = row["cash_after_tax"] or 0.0  # 每股税后现金，已是每股口径
            if cash > 0:
                actions.append(
                    CashDividend(
                        symbol=sym,
                        register_date=register_date,
                        pay_date=ex_date,  # 表无派息日，以除息日为到账日
                        amount_per_share=cash,
                    )
                )

            # 送股 + 转增，均为每10股口径，合并后除以 10 得每股比例
            bonus_per10 = (row["bonus_rate"] or 0.0) + (row["conversed_rate"] or 0.0)
            if bonus_per10 > 0:
                actions.append(BonusShares(symbol=sym, register_date=register_date, ex_date=ex_date, ratio=bonus_per10 / 10.0))

        # --- 配股 ---
        allot_sql = f"SELECT instrument, register_date, exright_date, allotment_rate, allotment_price FROM cn_stock_allotment WHERE exright_date BETWEEN '{start}' AND '{end}'"
        allot_df = self._query(allot_sql)
        for row in allot_df.iter_rows(named=True):
            rate_per10 = row["allotment_rate"] or 0.0  # 每10股口径
            price = row["allotment_price"] or 0.0
            if rate_per10 > 0 and price > 0:
                actions.append(RightsIssue(symbol=row["instrument"], register_date=row["register_date"], ex_date=row["exright_date"], ratio=rate_per10 / 10.0, price_per_share=price))

        return actions

    def load_delisted(self, start: date, end: date) -> dict[date, list[str]]:
        # 从全量缓存中筛出退市日落在 [start, end] 内的标的，按退市日聚合。
        grouped = self.delisted_df.filter(pl.col("delist_date").is_between(start, end)).group_by("delist_date").agg(pl.col("instrument"))
        return {row["delist_date"]: row["instrument"] for row in grouped.iter_rows(named=True)}
