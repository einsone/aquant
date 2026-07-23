"""组合查询服务模块，提供只读的历史数据查询接口。

借鉴 CQRS（命令查询职责分离）模式，将查询操作从 Portfolio 分离，
让策略能够访问历史净值曲线、成交记录、持仓历史等数据。
"""

from __future__ import annotations

from typing import TYPE_CHECKING


if TYPE_CHECKING:
    from datetime import date

    import polars as pl

    from aquant.portfolio.position import NavRecord, Trade


class PortfolioQueryService:
    """组合查询服务（只读）。

    提供历史数据查询接口，策略可通过 Context.query 访问。

    使用示例::

        class MyStrategy(Strategy):
            def on_bar(self, context: Context) -> list[Signal]:
                # 查询最近 20 日净值曲线
                nav_df = context.query.get_nav_curve(start=context.current_date - timedelta(days=30), end=context.current_date)

                # 查询某标的的最近成交
                trades = context.query.get_recent_trades("000001.SZ", n=10)

                # 基于历史数据做决策
                if nav_df["nav"][-1] < nav_df["nav"].mean():
                    return []  # 净值低于均值时不操作
                ...
    """

    def __init__(self, daily_nav: list[NavRecord], trade_log: list[Trade]) -> None:
        """初始化查询服务。

        参数
        ----
        daily_nav:
            每日净值快照列表（引用 Portfolio._daily_nav）
        trade_log:
            全部成交记录列表（引用 Portfolio.trade_log）
        """
        self._daily_nav = daily_nav
        self._trade_log = trade_log

    def get_nav_curve(self, start: date | None = None, end: date | None = None) -> pl.DataFrame:
        """查询净值曲线。

        参数
        ----
        start:
            起始日期（含），None 表示从第一条记录开始
        end:
            结束日期（含），None 表示到最后一条记录

        返回
        ----
        包含 date, nav, cash, position_count 列的 DataFrame
        """
        import polars as pl

        if not self._daily_nav:
            return pl.DataFrame(schema={"date": pl.Date, "nav": pl.Float64, "cash": pl.Float64, "position_count": pl.Int32})

        filtered = self._daily_nav
        if start is not None:
            filtered = [n for n in filtered if n.date >= start]
        if end is not None:
            filtered = [n for n in filtered if n.date <= end]

        return pl.DataFrame([{"date": n.date, "nav": n.total, "cash": n.cash, "position_count": n.position_count} for n in filtered])

    def get_recent_trades(self, symbol: str | None = None, n: int = 10) -> list[Trade]:
        """查询最近 N 笔成交。

        参数
        ----
        symbol:
            标的代码，None 表示查询所有标的
        n:
            返回的最大记录数

        返回
        ----
        按日期倒序排列的成交记录列表
        """
        trades = self._trade_log if symbol is None else [t for t in self._trade_log if t.symbol == symbol]

        # 按日期倒序
        return sorted(trades, key=lambda t: t.date, reverse=True)[:n]

    def get_trades_by_date_range(self, start: date, end: date, symbol: str | None = None) -> list[Trade]:
        """查询指定日期区间的成交记录。

        参数
        ----
        start:
            起始日期（含）
        end:
            结束日期（含）
        symbol:
            标的代码，None 表示查询所有标的

        返回
        ----
        按日期升序排列的成交记录列表
        """
        filtered = [t for t in self._trade_log if start <= t.date <= end]
        if symbol is not None:
            filtered = [t for t in filtered if t.symbol == symbol]

        return sorted(filtered, key=lambda t: t.date)

    def get_peak_nav(self) -> float:
        """获取历史最高净值。

        返回
        ----
        历史最高净值，若无记录返回 0.0
        """
        if not self._daily_nav:
            return 0.0
        return max(n.total for n in self._daily_nav)

    def get_current_drawdown(self) -> float:
        """获取当前回撤比例。

        返回
        ----
        当前回撤比例（0.0 到 1.0），若无记录返回 0.0
        """
        if not self._daily_nav:
            return 0.0

        peak = max(n.total for n in self._daily_nav)
        current = self._daily_nav[-1].total
        if peak <= 0:
            return 0.0

        return (peak - current) / peak

    def get_win_rate(self, symbol: str | None = None) -> float:
        """计算胜率。

        参数
        ----
        symbol:
            标的代码，None 表示计算全部标的的胜率

        返回
        ----
        胜率（0.0 到 1.0），若无卖出记录返回 0.0
        """
        sells = [t for t in self._trade_log if t.side == "sell"] if symbol is None else [t for t in self._trade_log if t.side == "sell" and t.symbol == symbol]

        if not sells:
            return 0.0

        wins = sum(1 for t in sells if t.pnl > 0)
        return wins / len(sells)

    def get_total_pnl(self, symbol: str | None = None) -> float:
        """计算累计盈亏。

        参数
        ----
        symbol:
            标的代码，None 表示计算全部标的的盈亏

        返回
        ----
        累计盈亏（元）
        """
        sells = [t for t in self._trade_log if t.side == "sell"] if symbol is None else [t for t in self._trade_log if t.side == "sell" and t.symbol == symbol]

        return sum(t.pnl for t in sells)
