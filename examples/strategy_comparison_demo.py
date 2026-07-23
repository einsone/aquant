"""策略对比示例

展示如何使用 StrategyComparison 对比多个策略的回测结果。
"""

from datetime import date

from aquant.core.engine import BacktestConfig, Engine
from aquant.data.synthetic import SyntheticDataSource
from aquant.strategy.base import Strategy
from aquant.strategy.signal import Signal
from aquant.tools.strategy_compare import StrategyComparison


class MomentumStrategy(Strategy):
    """动量策略"""

    warmup_period = 20
    rebalance_mode = "replace"

    def __init__(self, lookback: int = 20, threshold: float = 0.02):
        self.lookback = lookback
        self.threshold = threshold
        self.prices = {}

    def on_bar(self, context):
        # 简化实现：只买入第一个标的
        return [Signal(symbol="000001.SZ", weight=1.0)]


def main():
    # 创建数据源
    symbols = ["000001.SZ", "000002.SZ", "600000.SH"]
    data_source = SyntheticDataSource(symbols=symbols, days=252)

    # 回测配置
    config = BacktestConfig(
        start=date(2023, 1, 1),
        end=date(2023, 12, 31),
        initial_capital=1_000_000,
        show_progress=False,
    )

    # 创建对比分析器
    comparison = StrategyComparison()

    # 测试不同参数组合
    param_combinations = [
        {"lookback": 10, "threshold": 0.01},
        {"lookback": 20, "threshold": 0.02},
        {"lookback": 30, "threshold": 0.03},
    ]

    print("开始运行策略对比...\n")

    for params in param_combinations:
        strategy = MomentumStrategy(lookback=params["lookback"], threshold=params["threshold"])  # type: ignore[arg-type]
        engine = Engine(strategy=strategy, data_source=data_source, config=config)
        result = engine.run()

        name = f"动量策略(lookback={params['lookback']}, threshold={params['threshold']})"
        comparison.add_result(name, result)
        print(f"✓ {name} 完成")

    print("\n" + "=" * 80)

    # 打印对比摘要
    comparison.print_summary()

    # 找出最优策略
    best = comparison.get_best_strategy("sharpe")
    if best:
        print(f"\n推荐策略: {best[0]}")
        print(f"夏普比率: {best[1]:.4f}\n")

    # 生成 HTML 报告
    output_path = comparison.render_html("strategy_comparison.html")
    print(f"HTML 报告已生成: {output_path}")


if __name__ == "__main__":
    main()
