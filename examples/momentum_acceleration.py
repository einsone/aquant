"""加速动量策略示例（BigQuant DAI 数据源）。

策略逻辑
--------
在每个交易日收盘后，筛选满足"量价加速"条件的主板 A 股：

1. 前 5 日（[T-10, T-5]）涨幅 ≥ 3%              —— 有基础动量
2. 近 5 日（[T-5, T]）涨幅 > 前 5 日涨幅 x 2     —— 核心：加速上涨
3. 近 5 日涨幅在 [5%, 30%] 之间                 —— 排除炒作尾声
4. 近 5 日均换手率 ≥ 前 5 日均换手率 x 1.3       —— 量价同步
5. 近 5 日均换手率在 [0.3%, 20%]               —— 兜底过滤
6. 非 ST、主板（000/001/002/003/600/601/603/605）

等权重分配仓位，按 return_5d / return_prev_5d 降序取前 N 只。

运行::

    BIGQUANT_ACCESS_KEY=xxx BIGQUANT_SECRET_KEY=yyy \\
        uv run python examples/momentum_acceleration.py
"""

from __future__ import annotations

import os
from datetime import date, timedelta
from typing import TYPE_CHECKING

from aquant import BacktestConfig, Engine, Signal, Strategy
from aquant.data.bigquant import BigQuantDataSource
from aquant.log import get_logger, setup_logging


if TYPE_CHECKING:
    import polars as pl

    from aquant.core.context import Context


logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# 工具函数：在交易日列表中回溯 N 个自然日对应的交易日
# ---------------------------------------------------------------------------


def _prev_trading_day(calendar: list[date], ref: date, natural_days: int) -> date:
    """返回 ref 向前推 natural_days 个自然日后，最近的一个交易日（≤ 目标日）。"""
    target = ref - timedelta(days=natural_days)
    # 在已排序的 calendar 中找最后一个 <= target 的元素
    lo, hi = 0, len(calendar) - 1
    result = calendar[0]
    while lo <= hi:
        mid = (lo + hi) // 2
        if calendar[mid] <= target:
            result = calendar[mid]
            lo = mid + 1
        else:
            hi = mid - 1
    return result


# ---------------------------------------------------------------------------
# 策略实现
# ---------------------------------------------------------------------------


class MomentumAccelerationStrategy(Strategy):
    """量价加速动量策略。

    参数
    ----
    top_n:
        每日最多持仓股数，默认 10 只（0 表示不限数量，取所有通过筛选的标的）。
    warmup_days:
        预热期（交易日），用于确保首个信号日已有足够数据。默认 15 天。
    """

    rebalance_mode: str = "replace"

    def __init__(self, top_n: int = 10, warmup_days: int = 15) -> None:
        self.top_n = top_n
        self.warmup_period = warmup_days
        self._calendar: list[date] = []
        self._dai_source: BigQuantDataSource | None = None

    def on_start(self, context: Context) -> None:
        # 缓存交易日历和 DAI 引用，避免在 on_bar 中重复查询
        # _dai_source 由 Engine 注入的 data_source 持有，这里通过 context 拿不到，
        # 改为在构造阶段手动传入；见下方 _attach_source 方法。
        pass

    def _attach_source(self, source: BigQuantDataSource, calendar: list[date]) -> None:
        """在创建 Engine 后、run() 前调用，将数据源和日历注入策略。"""
        self._dai_source = source
        self._calendar = sorted(calendar)

    def on_bar(self, context: Context) -> list[Signal]:
        if self._dai_source is None:
            raise RuntimeError("请先调用 strategy._attach_source(source, calendar) 注入数据源")

        dt = context.current_date

        # 计算三个关键时间节点
        d_today = dt
        d_5 = _prev_trading_day(self._calendar, dt, natural_days=5)
        d_10 = _prev_trading_day(self._calendar, dt, natural_days=10)

        sql = f"""
        SELECT *
        FROM (
            SELECT
                instrument,
                ROUND((close_today - close_5d) / close_5d * 100, 2)      AS return_5d,
                ROUND((close_5d  - close_10d) / close_10d * 100, 2)      AS return_prev_5d,
                ROUND(AVG(CASE WHEN date BETWEEN '{d_5}' AND '{d_today}'
                              THEN turn * 100 END), 4)                    AS avg_turn_5d,
                ROUND(AVG(CASE WHEN date BETWEEN '{d_10}' AND '{d_5}'
                              THEN turn * 100 END), 4)                    AS avg_turn_prev_5d
            FROM (
                SELECT
                    instrument,
                    date,
                    turn,
                    MAX(CASE WHEN date = '{d_today}' THEN close / adjust_factor END)
                        OVER (PARTITION BY instrument)  AS close_today,
                    MAX(CASE WHEN date = '{d_5}'    THEN close / adjust_factor END)
                        OVER (PARTITION BY instrument)  AS close_5d,
                    MAX(CASE WHEN date = '{d_10}'   THEN close / adjust_factor END)
                        OVER (PARTITION BY instrument)  AS close_10d
                FROM cn_stock_prefactors
                WHERE
                    st_status = 0
                    AND date BETWEEN '{d_10}' AND '{d_today}'
                    AND regexp_matches(instrument, '^(000|001|002|003|600|601|603|605)')
            )
            GROUP BY instrument, close_today, close_5d, close_10d
            HAVING
                close_today IS NOT NULL
                AND close_5d  IS NOT NULL
                AND close_10d IS NOT NULL
        )
        WHERE
            return_prev_5d >= 3
            AND return_5d > return_prev_5d * 2
            AND return_5d BETWEEN 5 AND 30
            AND avg_turn_5d   >= avg_turn_prev_5d * 1.3
            AND avg_turn_5d   BETWEEN 0.3 AND 20
        ORDER BY return_5d / return_prev_5d DESC
        """

        df: pl.DataFrame = self._dai_source._query(sql)

        if df.is_empty():
            logger.debug("无满足条件的标的", date=str(dt))
            return []

        # 限制持仓数量
        if self.top_n > 0:
            df = df.head(self.top_n)

        n = len(df)
        weight = 1.0 / n  # 等权
        signals = [Signal(symbol=row["instrument"], weight=weight) for row in df.iter_rows(named=True)]
        logger.debug("生成信号", date=str(dt), count=n, symbols=[s.symbol for s in signals])
        return signals

    def on_end(self, context: Context) -> None:
        pass


# ---------------------------------------------------------------------------
# 入口
# ---------------------------------------------------------------------------


def main() -> None:
    setup_logging()  # 确保日志系统已初始化（log.py 首次 import 虽然会自动初始化，但显式调用更可靠）

    access_key = os.environ.get("BIGQUANT_ACCESS_KEY", "")
    secret_key = os.environ.get("BIGQUANT_SECRET_KEY", "")

    logger.info("启动加速动量策略回测", start="2024-01-02", end="2024-12-31", top_n=10)

    source = BigQuantDataSource(access_key=access_key, secret_key=secret_key)

    start = date(2024, 1, 2)
    end = date(2024, 12, 31)

    config = BacktestConfig(
        start=start,
        end=end,
        initial_capital=1_000_000,
        commission_rate=0.0003,
        min_commission=5.0,
        stamp_duty_rate=0.001,
        slippage_rate=0.0005,
        rebalance_threshold=0.02,  # 权重偏差 < 2% 不触发调仓，减少无效换手
    )

    strategy = MomentumAccelerationStrategy(top_n=10, warmup_days=15)

    # 提前加载日历，注入策略（策略 on_bar 中需要用来计算回溯交易日）
    calendar = source.load_calendar(start, end)
    strategy._attach_source(source, calendar)

    engine = Engine(strategy=strategy, data_source=source, config=config)
    result = engine.run()
    # engine.run() 内部已调用 compute_metrics()，此处无需重复调用

    # ---- 控制台摘要 ----
    from aquant.analytics.report import _METRIC_LABELS, _fmt

    print("\n=== 加速动量策略回测结果 ===")
    for k, v in result.metrics.items():
        label = _METRIC_LABELS.get(k, k)
        print(f"  {label:<20} {_fmt(k, v)}")

    print(f"\n  {'总成交笔数':<20} {len(result.portfolio.trade_log)} 笔")
    print(f"  {'最终组合市值':<19} {result.portfolio.total_value:,.0f} 元")

    # ---- 生成 HTML 报告并在浏览器打开 ----
    report_path = result.render_html(path="momentum_acceleration_report.html", open_browser=True)
    print(f"\n📊 HTML 报告已生成: {report_path}")


if __name__ == "__main__":
    main()
