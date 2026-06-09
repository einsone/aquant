"""端到端使用示例，使用合成内存数据。

运行：
    uv run python examples/demo.py
"""

from __future__ import annotations

import random
from datetime import date, timedelta

from aquant import BacktestConfig, Engine, Signal, Strategy
from aquant.adjustment.corporate import CorporateAction
from aquant.data.source import DataSource
from aquant.market.bar import DayBar
from aquant.optimization import grid_search


# ---------------------------------------------------------------------------
# 1. 生成合成数据
# ---------------------------------------------------------------------------

SYMBOLS = [f"SH{i:06d}" for i in range(1, 21)]  # 20 只虚拟股票
START = date(2022, 1, 4)
END = date(2023, 12, 29)


def _trading_days(start: date, end: date) -> list[date]:
    days = []
    d = start
    while d <= end:
        if d.weekday() < 5:
            days.append(d)
        d += timedelta(days=1)
    return days


_DAYS = _trading_days(START, END)

random.seed(42)  # 在生成价格序列前设置随机种子，保证可复现

# 随机游走价格序列
_prices: dict[str, list[float]] = {}
for sym in SYMBOLS:
    price = random.uniform(5.0, 100.0)
    series = [price]
    for _ in range(len(_DAYS) - 1):
        price = max(1.0, price * (1 + random.gauss(0, 0.02)))
        series.append(price)
    _prices[sym] = series

_DAY_INDEX = {d: i for i, d in enumerate(_DAYS)}


# ---------------------------------------------------------------------------
# 2. 实现 DataSource
# ---------------------------------------------------------------------------


class DemoDataSource(DataSource):
    """使用合成内存数据的演示数据源。实际使用时替换为真实数据库查询。"""

    def load_calendar(self, start: date, end: date) -> list[date]:
        return _trading_days(start, end)

    def load_bars(self, dt: date, symbols: set[str]) -> dict[str, DayBar]:
        idx = _DAY_INDEX.get(dt)
        if idx is None:
            return {}
        result = {}
        for sym in symbols:
            if sym not in _prices:
                continue
            price = _prices[sym][idx]
            result[sym] = DayBar(symbol=sym, date=dt, open=price * 0.998, close=price, high=price * 1.01, low=price * 0.99, volume=1_000_000, up_limit=price * 1.1, down_limit=price * 0.9, is_halted=False, is_delisted=False)
        return result

    def load_adjustments(self, start: date, end: date) -> list[CorporateAction]:
        return []

    def load_delisted(self, start: date, end: date) -> dict[date, list[str]]:
        # 实际实现：查询 cn_stock_delisted 表
        # SELECT delisted_date, list(symbol)
        # FROM cn_stock_delisted
        # WHERE delisted_date BETWEEN start AND end
        # GROUP BY delisted_date
        return {}


# ---------------------------------------------------------------------------
# 3. 实现等权重动量策略（replace 模式：每日输出完整目标持仓）
# ---------------------------------------------------------------------------


class MomentumStrategy(Strategy):
    warmup_period: int = 20
    rebalance_mode: str = "replace"  # 未出现在信号中的持仓自动清仓

    def __init__(self, lookback: int = 20, top_n: int = 5) -> None:
        self.lookback = lookback
        self.top_n = top_n

    def on_bar(self, context):
        dt = context.current_date
        idx = _DAY_INDEX.get(dt)
        if idx is None or idx < self.lookback:
            return []

        scored = []
        for sym in SYMBOLS:
            p_now = _prices[sym][idx]
            p_past = _prices[sym][idx - self.lookback]
            if p_past > 0:
                scored.append((sym, p_now / p_past - 1))

        scored.sort(key=lambda x: x[1], reverse=True)
        top = scored[: self.top_n]

        if not top:
            return []

        weight = 1.0 / len(top)
        return [Signal(symbol=sym, weight=weight) for sym, _ in top]


# ---------------------------------------------------------------------------
# 4. 单次回测
# ---------------------------------------------------------------------------


def run_single() -> None:
    config = BacktestConfig(start=START, end=END, initial_capital=1_000_000, commission_rate=0.0003, stamp_duty_rate=0.001, slippage_rate=0.0005, cash_buffer=0.02)

    result = Engine(strategy=MomentumStrategy(lookback=20, top_n=5), data_source=DemoDataSource(), config=config).run()

    print("=== 单次回测 ===")
    for k, v in result.metrics.items():
        if isinstance(v, float):
            print(f"  {k}: {v:.4f}")
        else:
            print(f"  {k}: {v}")

    print(f"\n总成交笔数: {len(result.portfolio.trade_log)}")
    print(f"最终组合市值: {result.portfolio.total_value:,.0f}")


# ---------------------------------------------------------------------------
# 5. 网格搜索
# ---------------------------------------------------------------------------


def run_grid_search() -> None:
    config = BacktestConfig(start=START, end=END, initial_capital=1_000_000)

    results = grid_search(strategy_cls=MomentumStrategy, param_grid={"lookback": [10, 20], "top_n": [3, 5]}, config=config, data_source=DemoDataSource(), metric="sharpe")

    print("\n=== 网格搜索结果 ===")
    print(results.select(["lookback", "top_n", "sharpe", "annualized_return", "max_drawdown"]))


if __name__ == "__main__":
    run_single()
    run_grid_search()
