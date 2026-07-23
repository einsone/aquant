"""测试遗传算法优化器"""

from datetime import date, timedelta

from aquant.core.engine import BacktestConfig
from aquant.data.source import DataSource
from aquant.market.bar import DayBar
from aquant.optimization.genetic_algorithm import GeneticAlgorithm, Individual
from aquant.strategy.base import Strategy
from aquant.strategy.signal import Signal


class MockDataSource(DataSource):
    """简单的模拟数据源"""

    def __init__(self):
        self.calendar = [date(2023, 1, 3) + i * timedelta(days=1) for i in range(60)]

    def load_calendar(self, start: date, end: date) -> list[date]:
        return [d for d in self.calendar if start <= d <= end]

    def load_bars(self, dt: date, symbols: set[str]) -> dict[str, DayBar]:
        if dt not in self.calendar:
            return {}

        idx = self.calendar.index(dt)
        bars = {}

        for symbol in symbols:
            price = 10.0 + idx * 0.1
            bars[symbol] = DayBar(symbol=symbol, date=dt, open=price * 0.99, high=price * 1.02, low=price * 0.98, close=price, volume=1000000, up_limit=price * 1.1, down_limit=price * 0.9, is_halted=False)

        return bars

    def load_adjustments(self, start: date, end: date):
        return []

    def load_delisted(self, start: date, end: date):
        return {}


class SimpleStrategy(Strategy):
    """简单测试策略"""

    warmup_period = 1
    rebalance_mode = "replace"

    def __init__(self, data_source, param1: int = 10, param2: float = 0.5):
        self.data_source = data_source
        self.param1 = param1
        self.param2 = param2

    def on_bar(self, context):
        # 简单策略逻辑
        if len(context.universe) > 0:
            symbol = list(context.universe)[0]
            return [Signal(symbol=symbol, weight=1.0)]
        return []


def test_individual_creation():
    """测试个体创建"""
    genes = {"param1": 10, "param2": 0.5}
    ind = Individual(genes)

    assert ind.genes == genes
    assert ind.fitness == 0.0


def test_genetic_algorithm_init():
    """测试遗传算法初始化"""
    data_source = MockDataSource()
    config = BacktestConfig(start=date(2023, 1, 1), end=date(2023, 1, 31), initial_capital=100000, show_progress=False)

    param_ranges = {"param1": (5, 20, int), "param2": (0.1, 1.0, float)}

    ga = GeneticAlgorithm(strategy_class=SimpleStrategy, param_ranges=param_ranges, data_source=data_source, backtest_config=config, population_size=10, generations=5, mutation_rate=0.1, crossover_rate=0.7)

    assert ga.population_size == 10
    assert ga.generations == 5
    assert ga.mutation_rate == 0.1
    assert ga.crossover_rate == 0.7
    assert ga.scoring == "sharpe"


def test_initialize_population():
    """测试种群初始化"""
    data_source = MockDataSource()
    config = BacktestConfig(start=date(2023, 1, 1), end=date(2023, 1, 31), initial_capital=100000, show_progress=False)

    param_ranges = {"param1": (5, 20, int), "param2": (0.1, 1.0, float)}

    ga = GeneticAlgorithm(strategy_class=SimpleStrategy, param_ranges=param_ranges, data_source=data_source, backtest_config=config, population_size=10)

    ga._initialize_population()

    assert len(ga.population) == 10
    for ind in ga.population:
        assert "param1" in ind.genes
        assert "param2" in ind.genes
        assert 5 <= ind.genes["param1"] <= 20
        assert 0.1 <= ind.genes["param2"] <= 1.0


def test_crossover():
    """测试交叉操作"""
    data_source = MockDataSource()
    config = BacktestConfig(start=date(2023, 1, 1), end=date(2023, 1, 31), initial_capital=100000, show_progress=False)

    param_ranges = {"param1": (5, 20, int), "param2": (0.1, 1.0, float)}

    ga = GeneticAlgorithm(
        strategy_class=SimpleStrategy,
        param_ranges=param_ranges,
        data_source=data_source,
        backtest_config=config,
        crossover_rate=1.0,  # 100% 交叉
    )

    parents = [Individual({"param1": 10, "param2": 0.5}), Individual({"param1": 15, "param2": 0.8})]

    offspring = ga._crossover(parents)

    assert len(offspring) == 2
    assert isinstance(offspring[0], Individual)
    assert isinstance(offspring[1], Individual)


def test_mutation():
    """测试变异操作"""
    data_source = MockDataSource()
    config = BacktestConfig(start=date(2023, 1, 1), end=date(2023, 1, 31), initial_capital=100000, show_progress=False)

    param_ranges = {"param1": (5, 20, int), "param2": (0.1, 1.0, float)}

    ga = GeneticAlgorithm(
        strategy_class=SimpleStrategy,
        param_ranges=param_ranges,
        data_source=data_source,
        backtest_config=config,
        mutation_rate=1.0,  # 100% 变异
    )

    offspring = [Individual({"param1": 10, "param2": 0.5})]
    original_genes = offspring[0].genes.copy()

    ga._mutation(offspring)

    # 100% 变异率应该改变参数
    assert offspring[0].genes != original_genes


def test_selection():
    """测试选择操作"""
    data_source = MockDataSource()
    config = BacktestConfig(start=date(2023, 1, 1), end=date(2023, 1, 31), initial_capital=100000, show_progress=False)

    param_ranges = {"param1": (5, 20, int), "param2": (0.1, 1.0, float)}

    ga = GeneticAlgorithm(strategy_class=SimpleStrategy, param_ranges=param_ranges, data_source=data_source, backtest_config=config, population_size=10)

    # 创建有不同适应度的种群
    ga.population = [Individual({"param1": i, "param2": 0.5}) for i in range(5, 15)]
    for i, ind in enumerate(ga.population):
        ind.fitness = float(i)

    parents = ga._selection()

    assert len(parents) == 10


def test_replacement():
    """测试精英保留替换"""
    data_source = MockDataSource()
    config = BacktestConfig(start=date(2023, 1, 1), end=date(2023, 1, 31), initial_capital=100000, show_progress=False)

    param_ranges = {"param1": (5, 20, int), "param2": (0.1, 1.0, float)}

    ga = GeneticAlgorithm(strategy_class=SimpleStrategy, param_ranges=param_ranges, data_source=data_source, backtest_config=config, population_size=10)

    # 创建种群和后代
    ga.population = [Individual({"param1": i, "param2": 0.5}) for i in range(5, 15)]
    for i, ind in enumerate(ga.population):
        ind.fitness = float(i)

    offspring = [Individual({"param1": i, "param2": 0.6}) for i in range(10, 15)]
    for i, ind in enumerate(offspring):
        ind.fitness = float(i + 10)

    new_population = ga._replacement(offspring)

    # 应该保留最优的 10 个个体
    assert len(new_population) == 10
    # 最佳个体应该被保留
    assert max(ind.fitness for ind in new_population) >= max(ind.fitness for ind in ga.population)


def test_run_optimization():
    """测试完整优化流程"""
    data_source = MockDataSource()
    config = BacktestConfig(start=date(2023, 1, 1), end=date(2023, 1, 31), initial_capital=100000, show_progress=False)

    param_ranges = {"param1": (5, 20, int), "param2": (0.1, 1.0, float)}

    ga = GeneticAlgorithm(strategy_class=SimpleStrategy, param_ranges=param_ranges, data_source=data_source, backtest_config=config, population_size=5, generations=2)

    best_params = ga.run(verbose=False)

    assert isinstance(best_params, dict)
    assert "param1" in best_params
    assert "param2" in best_params
    assert ga.best_individual is not None
    assert len(ga.history) == 2  # 2 代
