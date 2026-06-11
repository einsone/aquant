from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING


if TYPE_CHECKING:
    from datetime import date

    from aquant.adjustment.corporate import CorporateAction
    from aquant.market.bar import DayBar


class DataSource(ABC):
    """数据源抽象基类。

    继承此类并实现全部方法，传入 Engine 即可驱动回测。
    框架通过这个接口获取所有外部数据，不依赖任何具体数据库或文件格式。

    示例::

        class MyDataSource(DataSource):
            def __init__(self, db_path: str) -> None:
                import duckdb

                self._conn = duckdb.connect(db_path, read_only=True)

            def load_calendar(self, start, end): ...

            def load_bars(self, dt, symbols): ...

            def load_adjustments(self, start, end): ...

            def load_delisted(self, start, end): ...
    """

    @abstractmethod
    def load_calendar(self, start: date, end: date) -> list[date]:
        """返回覆盖 [start, end] 区间的交易日列表，按升序排列。

        框架用此列表驱动事件循环，每个交易日对应一组有序事件。
        start 和 end 无需精确到交易日，框架会自动取列表中 >= start 的第一个
        和 <= end 的最后一个交易日作为实际起止。
        """

    @abstractmethod
    def load_bars(self, dt: date, symbols: set[str]) -> dict[str, DayBar]:
        """返回指定日期、指定标的集合的日行情，以标的代码为键。

        框架每个交易日调用一次，symbols = 当日信号标的 ∪ 当前持仓标的。
        若某标的当日无行情（停牌、数据缺失），不在返回字典中即可，框架会跳过该标的。
        """

    @abstractmethod
    def load_adjustments(self, start: date, end: date) -> list[CorporateAction]:
        """返回 [start, end] 区间内所有企业行动记录。

        每条记录为 CashDividend、BonusShares 或 RightsIssue 之一。
        查询条件建议为：触发日期（pay_date 或 ex_date）>= start，
        确保包含登记日早于 start、但触发日在区间内的记录。
        无企业行动时返回空列表。
        """

    @abstractmethod
    def load_delisted(self, start: date, end: date) -> dict[date, list[str]]:
        """返回 [start, end] 区间内每个退市日期对应的退市标的列表。

        典型实现（查询 cn_stock_delisted 表）::

            SELECT delisted_date, list(symbol)
            FROM cn_stock_delisted
            WHERE delisted_date BETWEEN start AND end
            GROUP BY delisted_date

        无退市记录时返回空字典。
        """
