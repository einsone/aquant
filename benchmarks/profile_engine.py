"""性能分析工具

使用 cProfile 分析回测引擎的热点路径。
"""

import cProfile
import pstats
from datetime import date
from io import StringIO

from aquant import BacktestConfig, Engine, Signal, Strategy
from aquant.core.context import Context
from aquant.data.alds import ALDSDataSource


class SimpleStrategy(Strategy):
    """简单策略用于性能分析"""

    warmup_period = 20
    rebalance_mode = "replace"

    def __init__(self, universe: list[str], data_source: ALDSDataSource):
        self.universe = universe
        self.data_source = data_source

    def on_bar(self, context: Context) -> list[Signal]:
        weight = 1.0 / len(self.universe) if self.universe else 0.0
        return [Signal(symbol=symbol, weight=weight) for symbol in self.universe]


def profile_backtest():
    """分析回测性能"""
    print("开始性能分析...")
    print()

    # 配置回测
    universe = [
        "000001.SZ",
        "000002.SZ",
        "600000.SH",
        "600036.SH",
        "600519.SH",
    ]

    data_source = ALDSDataSource()
    strategy = SimpleStrategy(universe, data_source)

    config = BacktestConfig(
        start=date(2023, 1, 1),
        end=date(2023, 12, 31),
        initial_capital=1_000_000.0,
        show_progress=False,
    )

    # 性能分析
    profiler = cProfile.Profile()
    profiler.enable()

    engine = Engine(strategy, data_source, config)
    result = engine.run()

    profiler.disable()

    # 输出分析结果
    stream = StringIO()
    stats = pstats.Stats(profiler, stream=stream)

    print("=" * 70)
    print("性能分析结果（按累计时间排序）")
    print("=" * 70)
    print()

    stats.sort_stats("cumulative")
    stats.print_stats(30)  # 显示前 30 个函数

    print(stream.getvalue())
    print()

    print("=" * 70)
    print("性能分析结果（按单次调用时间排序）")
    print("=" * 70)
    print()

    stream = StringIO()
    stats = pstats.Stats(profiler, stream=stream)
    stats.sort_stats("time")
    stats.print_stats(30)

    print(stream.getvalue())
    print()

    # 保存详细报告
    stats_file = "performance_profile.stats"
    stats.dump_stats(stats_file)
    print(f"详细性能分析已保存到: {stats_file}")
    print("可以使用 snakeviz 可视化：uv run snakeviz performance_profile.stats")
    print()


def main():
    """运行性能分析"""
    profile_backtest()


if __name__ == "__main__":
    main()
