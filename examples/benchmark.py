"""性能测试脚本。

测试不同数据规模下的回测性能。
"""

import time
from datetime import date, timedelta

from aquant.core.context import Context
from aquant.core.engine import BacktestConfig, Engine
from aquant.data.csv import CSVDataSource, create_sample_csv
from aquant.strategy.base import Strategy
from aquant.strategy.signal import Signal


class SimpleStrategy(Strategy):
    """简单策略用于性能测试。"""

    warmup_period: int = 20
    rebalance_mode: str = "replace"

    def __init__(self, symbols: list[str], data_source: CSVDataSource):
        self.symbols = symbols
        self.data_source = data_source
        self.price_history = {}

    def on_bar(self, context: Context) -> list[Signal]:
        # 从数据源加载当日行情
        bars = self.data_source.load_bars(context.current_date, set(self.symbols))

        for symbol, bar in bars.items():
            if symbol not in self.price_history:
                self.price_history[symbol] = []
            self.price_history[symbol].append(bar.close)
            self.price_history[symbol] = self.price_history[symbol][-20:]

        momentum = {}
        for symbol, prices in self.price_history.items():
            if len(prices) >= 20:
                momentum[symbol] = (prices[-1] - prices[0]) / prices[0]

        if momentum:
            top = sorted(momentum.items(), key=lambda x: x[1], reverse=True)[:5]
            weight = 1.0 / len(top)
            return [Signal(symbol=s, weight=weight) for s, _ in top]

        return []


def benchmark_backtest(num_symbols: int, num_days: int):
    """性能测试。

    参数
    ----
    num_symbols : int
        股票数量
    num_days : int
        回测天数
    """
    print(f"\n{'=' * 60}")
    print(f"性能测试: {num_symbols} 只股票 × {num_days} 天")
    print(f"{'=' * 60}")

    # 生成股票代码
    symbols = [f"{str(i).zfill(6)}.SZ" for i in range(num_symbols)]

    # 计算日期范围
    end_date = date.today()
    start_date = end_date - timedelta(days=int(num_days * 1.5))  # 考虑非交易日

    # 生成测试数据
    print("生成测试数据...")
    start_time = time.time()
    create_sample_csv(data_dir="./data/benchmark", start=start_date, end=end_date, symbols=symbols)
    data_gen_time = time.time() - start_time
    print(f"  数据生成耗时: {data_gen_time:.2f} 秒")

    # 配置回测
    config = BacktestConfig(start=start_date, end=end_date, initial_capital=1_000_000.0)

    # 创建引擎
    data_source = CSVDataSource(data_dir="./data/benchmark")
    strategy = SimpleStrategy(symbols=symbols, data_source=data_source)
    engine = Engine(strategy=strategy, data_source=data_source, config=config)

    # 运行回测
    print("运行回测...")
    start_time = time.time()
    result = engine.run()
    backtest_time = time.time() - start_time

    # 输出结果
    print(f"  回测耗时: {backtest_time:.2f} 秒")
    print(f"  交易日数: {len(result.portfolio._daily_nav)} 天")
    print(f"  总交易次数: {len(result.portfolio.trade_log)} 笔")
    print(f"  平均每天耗时: {backtest_time / len(result.portfolio._daily_nav) * 1000:.2f} 毫秒")

    # 计算吞吐量
    total_bars = num_symbols * len(result.portfolio._daily_nav)
    throughput = total_bars / backtest_time
    print(f"  吞吐量: {throughput:.0f} bars/秒")

    return {"num_symbols": num_symbols, "num_days": len(result.portfolio._daily_nav), "backtest_time": backtest_time, "throughput": throughput}


def main():
    """运行性能测试。"""
    print("Aquant 性能测试")
    print("=" * 60)

    # 测试不同规模
    test_cases = [
        (10, 100),  # 10 只股票，100 天
        (50, 100),  # 50 只股票，100 天
        (100, 100),  # 100 只股票，100 天
        (100, 250),  # 100 只股票，250 天（一年）
    ]

    results = []
    for num_symbols, num_days in test_cases:
        result = benchmark_backtest(num_symbols, num_days)
        results.append(result)

    # 汇总结果
    print("\n" + "=" * 60)
    print("性能测试汇总")
    print("=" * 60)
    print(f"{'股票数':<10} {'天数':<10} {'耗时(秒)':<15} {'吞吐量(bars/s)':<20}")
    print("-" * 60)
    for r in results:
        print(f"{r['num_symbols']:<10} {r['num_days']:<10} {r['backtest_time']:<15.2f} {r['throughput']:<20.0f}")

    print("\n测试完成！")


if __name__ == "__main__":
    main()
