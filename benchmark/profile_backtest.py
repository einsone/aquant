"""使用 cProfile 分析回测性能瓶颈"""

import cProfile
import pstats
from datetime import date
from io import StringIO

from aquant import BacktestConfig, Engine, Signal, Strategy
from aquant.data.synthetic import SyntheticDataSource


class SimpleStrategy(Strategy):
    """简单的买入持有策略"""

    warmup_period = 0
    rebalance_mode = "replace"

    def __init__(self, symbols: list[str]):
        self.symbols = symbols

    def on_bar(self, context):
        n = len(self.symbols)
        if n == 0:
            return []
        weight = 1.0 / n
        return [Signal(symbol=sym, weight=weight) for sym in self.symbols]


def run_backtest():
    """运行一个中等规模的回测用于分析"""
    # 50 个标的，3 年数据
    symbols = [f"{i:06d}.SZ" for i in range(1, 51)]
    days = 252 * 3

    # 创建数据源和策略
    data_source = SyntheticDataSource(symbols=symbols, days=days, start_date=date(2023, 1, 1))
    strategy = SimpleStrategy(symbols=symbols)

    # 配置回测
    calendar = data_source.calendar
    config = BacktestConfig(
        start=calendar[0],
        end=calendar[-1],
        initial_capital=1_000_000,
        show_progress=False,
    )

    # 运行回测
    engine = Engine(strategy=strategy, data_source=data_source, config=config)
    result = engine.run()

    return result


def main():
    """使用 cProfile 分析性能"""
    print("=" * 60)
    print("性能分析 - 使用 cProfile")
    print("=" * 60)
    print("\n运行回测并收集性能数据...\n")

    # 创建 profiler
    profiler = cProfile.Profile()

    # 运行回测
    profiler.enable()
    result = run_backtest()
    profiler.disable()

    # 生成统计报告
    s = StringIO()
    ps = pstats.Stats(profiler, stream=s)
    ps.strip_dirs()

    print("=" * 60)
    print("前 20 个最耗时的函数（按累计时间排序）")
    print("=" * 60)
    ps.sort_stats("cumulative")
    ps.print_stats(20)
    print(s.getvalue())

    s = StringIO()
    ps = pstats.Stats(profiler, stream=s)
    ps.strip_dirs()

    print("\n" + "=" * 60)
    print("前 20 个最耗时的函数（按自身时间排序）")
    print("=" * 60)
    ps.sort_stats("time")
    ps.print_stats(20)
    print(s.getvalue())

    print("\n" + "=" * 60)
    print("回测结果")
    print("=" * 60)
    print(f"总收益: {result.metrics.get('total_return', 0):.2%}")
    print(f"夏普比率: {result.metrics.get('sharpe', 0):.2f}")
    print(f"最大回撤: {result.metrics.get('max_drawdown', 0):.2%}")
    print("=" * 60)


if __name__ == "__main__":
    main()
