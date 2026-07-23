"""演示回测进度条功能。

本示例展示：
1. 默认启用进度条
2. 通过配置禁用进度条
3. 进度条显示回测进度和实时净值

运行：
    uv run python examples/progress_bar_demo.py
"""

from __future__ import annotations

import random
from datetime import date, timedelta

from aquant import BacktestConfig, Engine, Signal, Strategy
from aquant.adjustment.corporate import CorporateAction
from aquant.data.source import DataSource
from aquant.market.bar import DayBar


# 生成测试数据
SYMBOLS = [f"SH{i:06d}" for i in range(1, 11)]  # 10 只股票
START = date(2023, 1, 1)
END = date(2023, 12, 31)


def _trading_days(start: date, end: date) -> list[date]:
    days = []
    d = start
    while d <= end:
        if d.weekday() < 5:
            days.append(d)
        d += timedelta(days=1)
    return days


_DAYS = _trading_days(START, END)

random.seed(42)

# 随机价格序列
_prices: dict[str, list[float]] = {}
for sym in SYMBOLS:
    price = random.uniform(10.0, 50.0)
    series = [price]
    for _ in range(len(_DAYS) - 1):
        price = max(1.0, price * (1 + random.gauss(0, 0.015)))
        series.append(price)
    _prices[sym] = series

_DAY_INDEX = {d: i for i, d in enumerate(_DAYS)}


class DemoDataSource(DataSource):
    """演示数据源。"""

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
            result[sym] = DayBar(symbol=sym, date=dt, open=price * 0.998, close=price, high=price * 1.01, low=price * 0.99, volume=1_000_000, up_limit=price * 1.1, down_limit=price * 0.9, is_halted=False)
        return result

    def load_adjustments(self, start: date, end: date) -> list[CorporateAction]:
        return []

    def load_delisted(self, start: date, end: date) -> dict[date, list[str]]:
        return {}


class SimpleStrategy(Strategy):
    """简单动量策略。"""

    warmup_period = 10
    rebalance_mode = "replace"

    def __init__(self, data_source: DataSource):
        self.data_source = data_source

    def on_bar(self, context):
        # 选择涨幅最大的 3 只股票
        bars = self.data_source.load_bars(context.current_date, set(SYMBOLS))
        if len(bars) < 3:
            return []

        # 计算 10 日涨幅
        momentum = {}
        for sym, bar in bars.items():
            if sym in _prices:
                idx = _DAY_INDEX[context.current_date]
                if idx >= 10:
                    old_price = _prices[sym][idx - 10]
                    momentum[sym] = (bar.close - old_price) / old_price

        if not momentum:
            return []

        # 选择 top 3
        top3 = sorted(momentum.items(), key=lambda x: x[1], reverse=True)[:3]
        weight = 1.0 / 3
        return [Signal(symbol=sym, weight=weight) for sym, _ in top3]


def main():
    """主函数。"""
    print("=" * 70)
    print("回测进度条演示")
    print("=" * 70)
    print()

    data_source = DemoDataSource()

    # 场景 1: 默认启用进度条
    print("场景 1: 默认启用进度条")
    print("-" * 70)
    config1 = BacktestConfig(
        start=START,
        end=END,
        initial_capital=1_000_000.0,
        show_progress=True,  # 默认值
    )
    engine1 = Engine(SimpleStrategy(data_source), data_source, config1)
    result1 = engine1.run()
    print(f"总收益率: {result1.metrics.get('total_return', 0) * 100:.2f}%")
    print()

    # 场景 2: 禁用进度条
    print("\n场景 2: 禁用进度条（使用日志输出）")
    print("-" * 70)
    config2 = BacktestConfig(
        start=START,
        end=END,
        initial_capital=1_000_000.0,
        show_progress=False,  # 禁用进度条
    )
    engine2 = Engine(SimpleStrategy(data_source), data_source, config2)
    result2 = engine2.run()
    print(f"总收益率: {result2.metrics.get('total_return', 0) * 100:.2f}%")
    print()

    print("=" * 70)
    print("演示完成！")
    print()
    print("说明：")
    print("- show_progress=True (默认): 显示实时进度条")
    print("- show_progress=False: 使用日志输出进度")
    print("- 进度条显示日期和实时净值")
    print()


if __name__ == "__main__":
    main()
