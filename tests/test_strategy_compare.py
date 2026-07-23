"""测试策略对比工具"""

from datetime import date

from aquant.core.engine import BacktestConfig, Engine
from aquant.data.synthetic import SyntheticDataSource
from aquant.strategy.base import Strategy
from aquant.strategy.signal import Signal
from aquant.tools.strategy_compare import StrategyComparison


class SimpleStrategy(Strategy):
    """简单测试策略"""

    warmup_period = 1
    rebalance_mode = "replace"

    def __init__(self, weight: float = 0.5):
        self.weight = weight

    def on_bar(self, context):
        return [Signal(symbol="000001.SZ", weight=self.weight)]


def test_strategy_comparison_basic():
    """测试基本的策略对比功能"""
    data_source = SyntheticDataSource(symbols=["000001.SZ", "000002.SZ"], days=50)
    config = BacktestConfig(
        start=date(2023, 1, 1),
        end=date(2023, 3, 31),
        initial_capital=100000,
        show_progress=False,
    )

    # 运行两个策略
    strategy1 = SimpleStrategy(weight=0.3)
    engine1 = Engine(strategy=strategy1, data_source=data_source, config=config)
    result1 = engine1.run()

    strategy2 = SimpleStrategy(weight=0.5)
    engine2 = Engine(strategy=strategy2, data_source=data_source, config=config)
    result2 = engine2.run()

    # 对比
    comparison = StrategyComparison()
    comparison.add_result("策略A (30%)", result1)
    comparison.add_result("策略B (50%)", result2)

    # 验证
    assert len(comparison.results) == 2
    assert "策略A (30%)" in comparison.results
    assert "策略B (50%)" in comparison.results


def test_strategy_comparison_metrics_table():
    """测试指标表格生成"""
    data_source = SyntheticDataSource(symbols=["000001.SZ"], days=50)
    config = BacktestConfig(
        start=date(2023, 1, 1),
        end=date(2023, 3, 31),
        initial_capital=100000,
        show_progress=False,
    )

    strategy = SimpleStrategy(weight=0.5)
    engine = Engine(strategy=strategy, data_source=data_source, config=config)
    result = engine.run()

    comparison = StrategyComparison()
    comparison.add_result("测试策略", result)

    df = comparison.get_metrics_table()

    assert len(df) == 1
    assert "策略名称" in df.columns
    assert df["策略名称"][0] == "测试策略"


def test_strategy_comparison_best_strategy():
    """测试最优策略识别"""
    data_source = SyntheticDataSource(symbols=["000001.SZ"], days=50)
    config = BacktestConfig(
        start=date(2023, 1, 1),
        end=date(2023, 3, 31),
        initial_capital=100000,
        show_progress=False,
    )

    # 运行多个策略
    results = []
    for weight in [0.3, 0.5, 0.7]:
        strategy = SimpleStrategy(weight=weight)
        engine = Engine(strategy=strategy, data_source=data_source, config=config)
        results.append(engine.run())

    comparison = StrategyComparison()
    comparison.add_result("策略A", results[0])
    comparison.add_result("策略B", results[1])
    comparison.add_result("策略C", results[2])

    best = comparison.get_best_strategy("sharpe")
    assert best is not None
    assert best[0] in ["策略A", "策略B", "策略C"]
    assert isinstance(best[1], float)


def test_strategy_comparison_empty():
    """测试空对比"""
    comparison = StrategyComparison()

    df = comparison.get_metrics_table()
    assert len(df) == 0

    best = comparison.get_best_strategy()
    assert best is None


def test_strategy_comparison_print_summary():
    """测试打印摘要"""
    data_source = SyntheticDataSource(symbols=["000001.SZ"], days=50)
    config = BacktestConfig(
        start=date(2023, 1, 1),
        end=date(2023, 3, 31),
        initial_capital=100000,
        show_progress=False,
    )

    strategy = SimpleStrategy(weight=0.5)
    engine = Engine(strategy=strategy, data_source=data_source, config=config)
    result = engine.run()

    comparison = StrategyComparison()
    comparison.add_result("测试策略", result)

    # 只验证不抛出异常
    comparison.print_summary()


def test_strategy_comparison_html_generation(tmp_path):
    """测试 HTML 报告生成"""
    data_source = SyntheticDataSource(symbols=["000001.SZ"], days=50)
    config = BacktestConfig(
        start=date(2023, 1, 1),
        end=date(2023, 3, 31),
        initial_capital=100000,
        show_progress=False,
    )

    strategy = SimpleStrategy(weight=0.5)
    engine = Engine(strategy=strategy, data_source=data_source, config=config)
    result = engine.run()

    comparison = StrategyComparison()
    comparison.add_result("测试策略", result)

    output_path = tmp_path / "comparison.html"
    result_path = comparison.render_html(str(output_path))

    assert output_path.exists()
    assert result_path == str(output_path.resolve())

    # 验证 HTML 内容
    content = output_path.read_text(encoding="utf-8")
    assert "策略对比报告" in content
    assert "测试策略" in content
    assert "<table>" in content
