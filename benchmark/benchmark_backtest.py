"""回测性能基准测试

测量不同场景下的回测速度，识别性能瓶颈。
"""

import time
from datetime import date

from aquant import BacktestConfig, Engine, Signal, Strategy


class SimpleStrategy(Strategy):
    """简单的买入持有策略"""

    warmup_period = 0
    rebalance_mode = "replace"

    def __init__(self, symbols: list[str]):
        self.symbols = symbols

    def on_bar(self, context):
        # 简单策略：均匀分配到所有标的
        n = len(self.symbols)
        if n == 0:
            return []
        weight = 1.0 / n
        return [Signal(symbol=sym, weight=weight) for sym in self.symbols]


class MomentumStrategy(Strategy):
    """动量策略 - 需要更多计算"""

    warmup_period = 20
    rebalance_mode = "replace"

    def __init__(self, symbols: list[str], lookback: int = 20):
        self.symbols = symbols
        self.lookback = lookback
        self.prices = {sym: [] for sym in symbols}

    def on_bar(self, context):
        # 模拟数据查询和计算
        dt = context.current_date

        # 模拟价格数据（实际应该从 data_source 获取）
        for sym in self.symbols:
            if sym not in self.prices:
                self.prices[sym] = []
            # 模拟价格增长
            price = 10.0 * (1 + len(self.prices[sym]) * 0.001)
            self.prices[sym].append(price)
            self.prices[sym] = self.prices[sym][-self.lookback :]

        # 计算动量并排序
        momentum = {}
        for sym in self.symbols:
            if len(self.prices[sym]) >= self.lookback:
                ret = (self.prices[sym][-1] - self.prices[sym][0]) / self.prices[sym][0]
                momentum[sym] = ret

        if not momentum:
            return []

        # 选择动量前 5 名
        top_n = 5
        sorted_syms = sorted(momentum.items(), key=lambda x: x[1], reverse=True)[:top_n]

        weight = 1.0 / min(top_n, len(sorted_syms))
        return [Signal(symbol=sym, weight=weight) for sym, _ in sorted_syms]


def benchmark_scenario(name: str, strategy_cls, symbols: list[str], days: int):
    """运行单个基准测试场景"""
    from aquant.data.synthetic import SyntheticDataSource

    print(f"\n{'=' * 60}")
    print(f"场景: {name}")
    print(f"标的数量: {len(symbols)}")
    print(f"交易日数: {days}")
    print(f"{'=' * 60}")

    # 创建合成数据源
    start_date = date(2023, 1, 1)
    data_source = SyntheticDataSource(symbols=symbols, days=days, start_date=start_date)

    # 创建策略
    if strategy_cls == SimpleStrategy:
        strategy = strategy_cls(symbols=symbols)
    else:
        strategy = strategy_cls(symbols=symbols, lookback=20)

    # 配置回测 - 使用数据源的日历范围
    calendar = data_source.calendar
    end_date = calendar[-1]

    config = BacktestConfig(
        start=start_date,
        end=end_date,
        initial_capital=1_000_000,
        show_progress=False,
    )

    # 运行回测并计时
    engine = Engine(strategy=strategy, data_source=data_source, config=config)

    start_time = time.time()
    result = engine.run()
    elapsed = time.time() - start_time

    # 输出结果
    print(f"\n执行时间: {elapsed:.2f} 秒")
    print(f"速度: {days / elapsed:.0f} 交易日/秒")
    print(f"总收益: {result.metrics.get('total_return', 0):.2%}")
    print(f"夏普比率: {result.metrics.get('sharpe', 0):.2f}")
    print(f"最大回撤: {result.metrics.get('max_drawdown', 0):.2%}")

    return elapsed, days / elapsed


def main():
    """运行所有基准测试"""
    print("=" * 60)
    print("Aquant 回测性能基准测试")
    print("=" * 60)

    results = []

    # 场景 1: 小规模 - 简单策略
    elapsed, speed = benchmark_scenario(
        name="小规模 - 简单策略",
        strategy_cls=SimpleStrategy,
        symbols=[f"00000{i}.SZ" for i in range(1, 11)],  # 10 个标的
        days=252,  # 1 年
    )
    results.append(("小规模-简单", elapsed, speed))

    # 场景 2: 中规模 - 简单策略
    elapsed, speed = benchmark_scenario(
        name="中规模 - 简单策略",
        strategy_cls=SimpleStrategy,
        symbols=[f"{i:06d}.SZ" for i in range(1, 51)],  # 50 个标的
        days=252 * 3,  # 3 年
    )
    results.append(("中规模-简单", elapsed, speed))

    # 场景 3: 大规模 - 简单策略
    elapsed, speed = benchmark_scenario(
        name="大规模 - 简单策略",
        strategy_cls=SimpleStrategy,
        symbols=[f"{i:06d}.SZ" for i in range(1, 101)],  # 100 个标的
        days=252 * 5,  # 5 年
    )
    results.append(("大规模-简单", elapsed, speed))

    # 场景 4: 中规模 - 动量策略（计算密集）
    elapsed, speed = benchmark_scenario(
        name="中规模 - 动量策略",
        strategy_cls=MomentumStrategy,
        symbols=[f"{i:06d}.SZ" for i in range(1, 51)],  # 50 个标的
        days=252 * 3,  # 3 年
    )
    results.append(("中规模-动量", elapsed, speed))

    # 打印汇总
    print(f"\n{'=' * 60}")
    print("性能汇总")
    print(f"{'=' * 60}")
    print(f"{'场景':<20} {'耗时(秒)':<15} {'速度(日/秒)':<15}")
    print("-" * 60)
    for name, elapsed, speed in results:
        print(f"{name:<20} {elapsed:<15.2f} {speed:<15.0f}")

    print(f"\n{'=' * 60}")
    print("基准测试完成")
    print(f"{'=' * 60}")


if __name__ == "__main__":
    main()
