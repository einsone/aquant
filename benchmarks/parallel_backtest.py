"""并行回测工具

支持多个策略同时回测，方便对比不同策略的表现。
"""

import concurrent.futures
import time
from datetime import date
from typing import Any

from aquant import BacktestConfig, Engine, Signal, Strategy
from aquant.core.context import Context
from aquant.data.alds import ALDSDataSource


class StrategyConfig:
    """策略配置"""

    def __init__(self, name: str, strategy: Strategy, description: str = ""):
        self.name = name
        self.strategy = strategy
        self.description = description


def run_single_backtest(
    strategy_config: StrategyConfig,
    data_source: ALDSDataSource,
    backtest_config: BacktestConfig,
) -> tuple[str, dict[str, Any], float]:
    """运行单个回测

    Args:
        strategy_config: 策略配置
        data_source: 数据源
        backtest_config: 回测配置

    Returns:
        (策略名称, 回测指标, 耗时)
    """
    start_time = time.time()

    engine = Engine(strategy_config.strategy, data_source, backtest_config)
    result = engine.run()
    result.compute_metrics()

    duration = time.time() - start_time

    return strategy_config.name, result.metrics, duration


def run_parallel_backtest(
    strategy_configs: list[StrategyConfig],
    backtest_config: BacktestConfig,
    max_workers: int = 4,
) -> dict[str, dict[str, Any]]:
    """并行运行多个策略回测

    Args:
        strategy_configs: 策略配置列表
        backtest_config: 回测配置
        max_workers: 最大并行数

    Returns:
        策略名称 -> 回测结果的字典
    """
    print(f"开始并行回测 {len(strategy_configs)} 个策略...")
    print(f"最大并行数: {max_workers}")
    print()

    data_source = ALDSDataSource()
    results = {}

    with concurrent.futures.ProcessPoolExecutor(max_workers=max_workers) as executor:
        # 提交所有任务
        future_to_strategy = {
            executor.submit(
                run_single_backtest, config, data_source, backtest_config
            ): config
            for config in strategy_configs
        }

        # 等待结果
        for future in concurrent.futures.as_completed(future_to_strategy):
            config = future_to_strategy[future]
            try:
                name, metrics, duration = future.result()
                results[name] = {
                    "metrics": metrics,
                    "duration": duration,
                    "description": config.description,
                }
                print(f"✓ {name} 完成 (耗时: {duration:.2f}s)")
            except Exception as e:
                print(f"✗ {config.name} 失败: {e}")

    print()
    return results


def compare_strategies(results: dict[str, dict[str, Any]]):
    """对比策略表现

    Args:
        results: 策略名称 -> 回测结果的字典
    """
    if not results:
        print("没有可对比的结果")
        return

    print("=" * 100)
    print("策略对比结果")
    print("=" * 100)
    print()

    # 打印表头
    print(f"{'策略名称':<20} {'总收益率':>12} {'夏普比率':>12} {'最大回撤':>12} {'胜率':>10} {'耗时(秒)':>10}")
    print("-" * 100)

    # 按收益率排序
    sorted_results = sorted(
        results.items(),
        key=lambda x: x[1]["metrics"].get("total_return", 0),
        reverse=True,
    )

    for name, data in sorted_results:
        metrics = data["metrics"]
        duration = data["duration"]

        total_return = metrics.get("total_return", 0) * 100
        sharpe = metrics.get("sharpe", 0)
        max_drawdown = metrics.get("max_drawdown", 0) * 100
        win_rate = metrics.get("win_rate", 0) * 100

        print(
            f"{name:<20} {total_return:>11.2f}% {sharpe:>12.2f} {max_drawdown:>11.2f}% {win_rate:>9.1f}% {duration:>10.2f}"
        )

    print()
    print("=" * 100)


def example_parallel_backtest():
    """并行回测示例"""

    # 定义多个策略
    class MomentumStrategy(Strategy):
        warmup_period = 20
        rebalance_mode = "replace"

        def __init__(self, data_source: ALDSDataSource):
            self.data_source = data_source
            self.universe = ["000001.SZ", "000002.SZ", "600000.SH"]

        def on_bar(self, context: Context) -> list[Signal]:
            momentum = {}
            for symbol in self.universe:
                bars = context.query.get_bars(symbol=symbol, count=self.warmup_period)
                if len(bars) == self.warmup_period:
                    momentum[symbol] = (
                        bars[-1].close - bars[0].close
                    ) / bars[0].close

            if momentum:
                best = max(momentum.items(), key=lambda x: x[1])[0]
                return [Signal(symbol=best, weight=1.0)]
            return []

    class EqualWeightStrategy(Strategy):
        warmup_period = 1
        rebalance_mode = "replace"

        def __init__(self, data_source: ALDSDataSource):
            self.data_source = data_source
            self.universe = ["000001.SZ", "000002.SZ", "600000.SH"]

        def on_bar(self, context: Context) -> list[Signal]:
            weight = 1.0 / len(self.universe)
            return [Signal(symbol=s, weight=weight) for s in self.universe]

    class BuyAndHoldStrategy(Strategy):
        warmup_period = 1
        rebalance_mode = "replace"

        def __init__(self, data_source: ALDSDataSource):
            self.data_source = data_source
            self.initialized = False

        def on_bar(self, context: Context) -> list[Signal]:
            if not self.initialized:
                self.initialized = True
                return [Signal(symbol="000001.SZ", weight=1.0)]
            return []

    # 配置策略
    data_source = ALDSDataSource()

    strategy_configs = [
        StrategyConfig(
            name="动量策略",
            strategy=MomentumStrategy(data_source),
            description="买入过去 20 日涨幅最大的股票",
        ),
        StrategyConfig(
            name="等权重策略",
            strategy=EqualWeightStrategy(data_source),
            description="等权重持有 3 只股票",
        ),
        StrategyConfig(
            name="买入持有",
            strategy=BuyAndHoldStrategy(data_source),
            description="买入单只股票并持有",
        ),
    ]

    # 回测配置
    backtest_config = BacktestConfig(
        start=date(2023, 1, 1),
        end=date(2023, 12, 31),
        initial_capital=1_000_000.0,
        show_progress=False,
    )

    # 并行运行
    results = run_parallel_backtest(strategy_configs, backtest_config, max_workers=3)

    # 对比结果
    compare_strategies(results)


def main():
    """运行并行回测示例"""
    example_parallel_backtest()


if __name__ == "__main__":
    main()
