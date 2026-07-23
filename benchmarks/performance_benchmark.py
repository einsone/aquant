"""性能基准测试工具

用于测试回测引擎的性能，帮助识别热点路径和优化机会。
"""

import time
from datetime import date
from typing import Any

from aquant import BacktestConfig, Engine, Signal, Strategy
from aquant.core.context import Context
from aquant.data.alds import ALDSDataSource


class SimpleBenchmarkStrategy(Strategy):
    """简单的基准测试策略"""

    warmup_period = 20
    rebalance_mode = "replace"

    def __init__(self, universe: list[str], data_source: ALDSDataSource):
        self.universe = universe
        self.data_source = data_source

    def on_bar(self, context: Context) -> list[Signal]:
        # 等权重持仓
        weight = 1.0 / len(self.universe) if self.universe else 0.0
        return [Signal(symbol=symbol, weight=weight) for symbol in self.universe]


class BenchmarkResult:
    """基准测试结果"""

    def __init__(
        self,
        name: str,
        duration: float,
        trading_days: int,
        symbols_count: int,
        trades_count: int,
    ):
        self.name = name
        self.duration = duration
        self.trading_days = trading_days
        self.symbols_count = symbols_count
        self.trades_count = trades_count

    @property
    def days_per_second(self) -> float:
        """每秒处理的交易日数"""
        return self.trading_days / self.duration if self.duration > 0 else 0

    @property
    def trades_per_second(self) -> float:
        """每秒处理的交易数"""
        return self.trades_count / self.duration if self.duration > 0 else 0

    def __str__(self) -> str:
        return (
            f"{self.name}:\n"
            f"  耗时: {self.duration:.2f}s\n"
            f"  交易日: {self.trading_days}\n"
            f"  股票数: {self.symbols_count}\n"
            f"  交易次数: {self.trades_count}\n"
            f"  速度: {self.days_per_second:.1f} 天/秒\n"
            f"  交易速度: {self.trades_per_second:.1f} 笔/秒"
        )


def benchmark_single_stock_one_year() -> BenchmarkResult:
    """基准测试：单只股票，1 年回测"""
    print("运行基准测试：单只股票，1 年回测...")

    data_source = ALDSDataSource()
    strategy = SimpleBenchmarkStrategy(["000001.SZ"], data_source)

    config = BacktestConfig(
        start=date(2023, 1, 1),
        end=date(2023, 12, 31),
        initial_capital=1_000_000.0,
        show_progress=False,
    )

    start_time = time.time()
    engine = Engine(strategy, data_source, config)
    result = engine.run()
    duration = time.time() - start_time

    trading_days = len(data_source.load_calendar(config.start, config.end))

    return BenchmarkResult(
        name="单只股票 1 年",
        duration=duration,
        trading_days=trading_days,
        symbols_count=1,
        trades_count=len(result.portfolio.trade_log),
    )


def benchmark_ten_stocks_one_year() -> BenchmarkResult:
    """基准测试：10 只股票，1 年回测"""
    print("运行基准测试：10 只股票，1 年回测...")

    universe = [
        "000001.SZ",
        "000002.SZ",
        "000333.SZ",
        "600000.SH",
        "600036.SH",
        "600519.SH",
        "601398.SH",
        "601857.SH",
        "601988.SH",
        "603259.SH",
    ]

    data_source = ALDSDataSource()
    strategy = SimpleBenchmarkStrategy(universe, data_source)

    config = BacktestConfig(
        start=date(2023, 1, 1),
        end=date(2023, 12, 31),
        initial_capital=1_000_000.0,
        show_progress=False,
    )

    start_time = time.time()
    engine = Engine(strategy, data_source, config)
    result = engine.run()
    duration = time.time() - start_time

    trading_days = len(data_source.load_calendar(config.start, config.end))

    return BenchmarkResult(
        name="10 只股票 1 年",
        duration=duration,
        trading_days=trading_days,
        symbols_count=len(universe),
        trades_count=len(result.portfolio.trade_log),
    )


def benchmark_single_stock_three_years() -> BenchmarkResult:
    """基准测试：单只股票，3 年回测"""
    print("运行基准测试：单只股票，3 年回测...")

    data_source = ALDSDataSource()
    strategy = SimpleBenchmarkStrategy(["000001.SZ"], data_source)

    config = BacktestConfig(
        start=date(2021, 1, 1),
        end=date(2023, 12, 31),
        initial_capital=1_000_000.0,
        show_progress=False,
    )

    start_time = time.time()
    engine = Engine(strategy, data_source, config)
    result = engine.run()
    duration = time.time() - start_time

    trading_days = len(data_source.load_calendar(config.start, config.end))

    return BenchmarkResult(
        name="单只股票 3 年",
        duration=duration,
        trading_days=trading_days,
        symbols_count=1,
        trades_count=len(result.portfolio.trade_log),
    )


def benchmark_frequent_rebalance() -> BenchmarkResult:
    """基准测试：高频调仓策略"""
    print("运行基准测试：高频调仓策略...")

    class FrequentRebalanceStrategy(Strategy):
        warmup_period = 5
        rebalance_mode = "replace"

        def __init__(self, universe: list[str], data_source: ALDSDataSource):
            self.universe = universe
            self.data_source = data_source
            self.count = 0

        def on_bar(self, context: Context) -> list[Signal]:
            # 每天轮换持仓
            self.count += 1
            idx = self.count % len(self.universe)
            return [Signal(symbol=self.universe[idx], weight=1.0)]

    universe = ["000001.SZ", "000002.SZ", "600000.SH", "600519.SH"]

    data_source = ALDSDataSource()
    strategy = FrequentRebalanceStrategy(universe, data_source)

    config = BacktestConfig(
        start=date(2023, 1, 1),
        end=date(2023, 12, 31),
        initial_capital=1_000_000.0,
        show_progress=False,
    )

    start_time = time.time()
    engine = Engine(strategy, data_source, config)
    result = engine.run()
    duration = time.time() - start_time

    trading_days = len(data_source.load_calendar(config.start, config.end))

    return BenchmarkResult(
        name="高频调仓策略",
        duration=duration,
        trading_days=trading_days,
        symbols_count=len(universe),
        trades_count=len(result.portfolio.trade_log),
    )


def run_all_benchmarks() -> list[BenchmarkResult]:
    """运行所有基准测试"""
    print("=" * 70)
    print("aquant 性能基准测试")
    print("=" * 70)
    print()

    results = []

    # 基准测试 1：单只股票 1 年
    results.append(benchmark_single_stock_one_year())
    print()

    # 基准测试 2：10 只股票 1 年
    results.append(benchmark_ten_stocks_one_year())
    print()

    # 基准测试 3：单只股票 3 年
    results.append(benchmark_single_stock_three_years())
    print()

    # 基准测试 4：高频调仓
    results.append(benchmark_frequent_rebalance())
    print()

    return results


def print_summary(results: list[BenchmarkResult]):
    """打印基准测试摘要"""
    print("=" * 70)
    print("基准测试摘要")
    print("=" * 70)
    print()

    for result in results:
        print(result)
        print()

    print("=" * 70)
    print("性能指标说明：")
    print("- 天/秒：每秒可以处理的回测交易日数（越高越好）")
    print("- 笔/秒：每秒可以处理的交易笔数（越高越好）")
    print()
    print("典型性能参考：")
    print("- 单只股票：应达到 500+ 天/秒")
    print("- 10 只股票：应达到 200+ 天/秒")
    print("- 高频交易：应达到 100+ 笔/秒")
    print("=" * 70)


def main():
    """运行基准测试主函数"""
    results = run_all_benchmarks()
    print_summary(results)


if __name__ == "__main__":
    main()
