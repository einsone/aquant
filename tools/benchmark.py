"""性能基准测试

对比不同配置下的回测性能。
"""

import time
from datetime import date

from aquant import BacktestConfig, Engine, Signal, Strategy
from aquant.data.synthetic import SyntheticDataSource
from aquant.tools.profiler import PerformanceProfiler, Timer


class SimpleStrategy(Strategy):
    """简单均仓策略"""

    def __init__(self, symbols: list[str]):
        super().__init__()
        self.symbols = symbols

    def on_start(self, context):
        self.universe = set(self.symbols)

    def on_bar(self, context):
        weight = 1.0 / len(self.symbols)
        return [Signal(symbol=s, weight=weight) for s in self.symbols]


def benchmark_baseline(symbols: int = 10, days: int = 252, log_level: str = "WARNING"):
    """基准测试

    Args:
        symbols: 股票数量
        days: 交易日数量
        log_level: 日志级别
    """
    print(f"\n{'='*60}")
    print(f"基准测试: {symbols} 只股票, {days} 个交易日")
    print(f"{'='*60}\n")

    # 准备数据
    symbol_list = [f"{i:06d}.SZ" for i in range(1, symbols + 1)]
    data_source = SyntheticDataSource(symbols=symbol_list, days=days)
    strategy = SimpleStrategy(symbols=symbol_list)

    # 配置
    config = BacktestConfig(
        start=date(2023, 1, 1),
        end=date(2023, 12, 31),
        initial_capital=1_000_000,
        log_level=log_level,
        show_progress=False,
    )

    # 运行基准测试
    timer = Timer()

    timer.start("total")
    engine = Engine(strategy=strategy, data_source=data_source, config=config)
    result = engine.run()
    total_time = timer.stop("total")

    # 计算指标
    timer.start("metrics")
    result.compute_metrics()
    metrics_time = timer.stop("metrics")

    print(f"总耗时: {total_time:.2f}s")
    print(f"指标计算: {metrics_time:.2f}s")
    print(f"回测速度: {days / total_time:.0f} 天/秒")
    print(f"总收益率: {result.metrics['total_return']:.2%}")

    return total_time


def benchmark_with_profiler(symbols: int = 10, days: int = 252):
    """使用性能分析器的基准测试"""
    print(f"\n{'='*60}")
    print(f"性能分析: {symbols} 只股票, {days} 个交易日")
    print(f"{'='*60}\n")

    # 准备数据
    symbol_list = [f"{i:06d}.SZ" for i in range(1, symbols + 1)]
    data_source = SyntheticDataSource(symbols=symbol_list, days=days)
    strategy = SimpleStrategy(symbols=symbol_list)

    config = BacktestConfig(
        start=date(2023, 1, 1),
        end=date(2023, 12, 31),
        initial_capital=1_000_000,
        log_level="WARNING",
        show_progress=False,
    )

    # 使用性能分析器
    profiler = PerformanceProfiler()

    with profiler:
        engine = Engine(strategy=strategy, data_source=data_source, config=config)
        result = engine.run()
        result.compute_metrics()

    # 打印最耗时的 20 个函数
    print("\n最耗时的 20 个函数:")
    profiler.print_top(20)

    # 保存详细报告
    profiler.save_report("performance_report.txt")
    print("\n详细报告已保存到: performance_report.txt")


def benchmark_scale(max_symbols: int = 50, step: int = 10):
    """规模测试：测试不同股票数量下的性能"""
    print(f"\n{'='*60}")
    print("规模测试：不同股票数量的性能对比")
    print(f"{'='*60}\n")

    results = []

    for n in range(step, max_symbols + 1, step):
        time_taken = benchmark_baseline(symbols=n, days=252, log_level="ERROR")
        results.append((n, time_taken))

    print(f"\n{'='*60}")
    print("规模测试结果汇总:")
    print(f"{'股票数':<10} {'耗时(秒)':<15} {'速度(天/秒)':<15}")
    print("-" * 40)

    for n, t in results:
        speed = 252 / t
        print(f"{n:<10} {t:<15.2f} {speed:<15.0f}")


if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1:
        test_type = sys.argv[1]

        if test_type == "baseline":
            symbols = int(sys.argv[2]) if len(sys.argv) > 2 else 10
            days = int(sys.argv[3]) if len(sys.argv) > 3 else 252
            benchmark_baseline(symbols=symbols, days=days)

        elif test_type == "profile":
            symbols = int(sys.argv[2]) if len(sys.argv) > 2 else 10
            days = int(sys.argv[3]) if len(sys.argv) > 3 else 252
            benchmark_with_profiler(symbols=symbols, days=days)

        elif test_type == "scale":
            max_symbols = int(sys.argv[2]) if len(sys.argv) > 2 else 50
            benchmark_scale(max_symbols=max_symbols)

        else:
            print(f"未知的测试类型: {test_type}")
            print("用法: python benchmark.py [baseline|profile|scale] [参数]")
    else:
        # 默认运行所有测试
        benchmark_baseline(symbols=10, days=252)
        benchmark_with_profiler(symbols=10, days=252)
        benchmark_scale(max_symbols=30, step=10)
