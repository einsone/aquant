"""遗传算法优化工具

使用遗传算法寻找策略的最优参数。
"""

import random
from datetime import date
from typing import Any

from aquant import BacktestConfig, Engine, Strategy
from aquant.data.source import DataSource


class Individual:
    """个体（一组参数）"""

    def __init__(self, genes: dict[str, Any]):
        self.genes = genes
        self.fitness: float = 0.0

    def __repr__(self) -> str:
        return f"Individual(genes={self.genes}, fitness={self.fitness:.4f})"


class GeneticAlgorithm:
    """遗传算法优化器"""

    def __init__(self, strategy_class: type[Strategy], param_ranges: dict[str, tuple], data_source: DataSource, backtest_config: BacktestConfig, population_size: int = 20, generations: int = 10, mutation_rate: float = 0.1, crossover_rate: float = 0.7, scoring: str = "sharpe"):
        """
        Args:
            strategy_class: 策略类
            param_ranges: 参数范围，格式：{参数名: (最小值, 最大值, 类型)}
                例如：{"fast_period": (5, 20, int), "threshold": (0.01, 0.1, float)}
            data_source: 数据源
            backtest_config: 回测配置
            population_size: 种群大小
            generations: 迭代代数
            mutation_rate: 变异率
            crossover_rate: 交叉率
            scoring: 优化目标指标
        """
        self.strategy_class = strategy_class
        self.param_ranges = param_ranges
        self.data_source = data_source
        self.backtest_config = backtest_config
        self.population_size = population_size
        self.generations = generations
        self.mutation_rate = mutation_rate
        self.crossover_rate = crossover_rate
        self.scoring = scoring
        self.population: list[Individual] = []
        self.best_individual: Individual | None = None
        self.history: list[dict] = []

    def run(self, verbose: bool = True) -> dict[str, Any]:
        """运行遗传算法

        Args:
            verbose: 是否打印进度

        Returns:
            最优参数
        """
        if verbose:
            print("=" * 80)
            print("遗传算法优化")
            print("=" * 80)
            print(f"种群大小: {self.population_size}")
            print(f"迭代代数: {self.generations}")
            print(f"变异率: {self.mutation_rate}")
            print(f"交叉率: {self.crossover_rate}")
            print(f"优化目标: {self.scoring}")
            print()

        # 初始化种群
        self._initialize_population()

        # 评估初始种群
        self._evaluate_population()

        if verbose:
            best = max(self.population, key=lambda x: x.fitness)
            print(f"第 0 代 - 最佳适应度: {best.fitness:.4f}, 参数: {best.genes}")
            print()

        # 迭代进化
        for generation in range(1, self.generations + 1):
            # 选择
            parents = self._selection()

            # 交叉
            offspring = self._crossover(parents)

            # 变异
            self._mutation(offspring)

            # 评估新个体
            self._evaluate_individuals(offspring)

            # 替换
            self.population = self._replacement(offspring)

            # 记录历史
            best = max(self.population, key=lambda x: x.fitness)
            avg_fitness = sum(ind.fitness for ind in self.population) / len(self.population)
            self.history.append({"generation": generation, "best_fitness": best.fitness, "avg_fitness": avg_fitness, "best_params": best.genes.copy()})

            if verbose:
                print(f"第 {generation} 代 - 最佳: {best.fitness:.4f}, 平均: {avg_fitness:.4f}")

        # 选出最优个体
        self.best_individual = max(self.population, key=lambda x: x.fitness)

        if verbose:
            print()
            print("=" * 80)
            print("优化完成")
            print("=" * 80)
            print(f"最优适应度: {self.best_individual.fitness:.4f}")
            print(f"最优参数: {self.best_individual.genes}")
            print("=" * 80)
            print()

        return self.best_individual.genes

    def _initialize_population(self):
        """初始化种群"""
        self.population = []
        for _ in range(self.population_size):
            genes = {}
            for param, (min_val, max_val, param_type) in self.param_ranges.items():
                if param_type is int:
                    genes[param] = random.randint(min_val, max_val)
                else:
                    genes[param] = random.uniform(min_val, max_val)
            self.population.append(Individual(genes))

    def _evaluate_population(self):
        """评估整个种群"""
        self._evaluate_individuals(self.population)

    def _evaluate_individuals(self, individuals: list[Individual]):
        """评估个体适应度"""
        for individual in individuals:
            try:
                # 创建策略并回测
                strategy = self.strategy_class(**individual.genes, data_source=self.data_source)
                engine = Engine(strategy, self.data_source, self.backtest_config)
                result = engine.run()
                result.compute_metrics()

                # 计算适应度
                individual.fitness = result.metrics.get(self.scoring, 0.0)
            except Exception:
                # 无效参数，适应度为 0
                individual.fitness = 0.0

    def _selection(self) -> list[Individual]:
        """选择（锦标赛选择）"""
        parents = []
        tournament_size = 3

        for _ in range(self.population_size):
            tournament = random.sample(self.population, tournament_size)
            winner = max(tournament, key=lambda x: x.fitness)
            parents.append(winner)

        return parents

    def _crossover(self, parents: list[Individual]) -> list[Individual]:
        """交叉"""
        offspring = []

        for i in range(0, len(parents) - 1, 2):
            parent1 = parents[i]
            parent2 = parents[i + 1]

            if random.random() < self.crossover_rate:
                # 单点交叉
                genes1 = parent1.genes.copy()
                genes2 = parent2.genes.copy()

                # 随机选择交叉点
                keys = list(genes1.keys())
                crossover_point = random.randint(1, len(keys) - 1)

                # 交换后半部分基因
                for key in keys[crossover_point:]:
                    genes1[key], genes2[key] = genes2[key], genes1[key]

                offspring.append(Individual(genes1))
                offspring.append(Individual(genes2))
            else:
                # 不交叉，直接复制
                offspring.append(Individual(parent1.genes.copy()))
                offspring.append(Individual(parent2.genes.copy()))

        return offspring

    def _mutation(self, offspring: list[Individual]):
        """变异"""
        for individual in offspring:
            for param, (min_val, max_val, param_type) in self.param_ranges.items():
                if random.random() < self.mutation_rate:
                    if param_type is int:
                        individual.genes[param] = random.randint(min_val, max_val)
                    else:
                        individual.genes[param] = random.uniform(min_val, max_val)

    def _replacement(self, offspring: list[Individual]) -> list[Individual]:
        """替换（精英保留）"""
        # 保留最优个体
        combined = self.population + offspring
        combined.sort(key=lambda x: x.fitness, reverse=True)
        return combined[: self.population_size]


def example_genetic_algorithm():
    """遗传算法示例"""
    from aquant import Signal
    from aquant.core.context import Context
    from aquant.data.alds import ALDSDataSource

    # 定义可参数化的策略
    class ParameterizedStrategy(Strategy):
        """可参数化的双均线策略"""

        rebalance_mode = "replace"

        def __init__(self, fast_period: int, slow_period: int, data_source: DataSource):
            self.fast_period = fast_period
            self.slow_period = slow_period
            self.data_source = data_source
            self.warmup_period = slow_period
            self.symbol = "000001.SZ"

        def on_bar(self, context: Context) -> list[Signal]:
            bars = context.query.get_bars(symbol=self.symbol, count=self.slow_period)

            if len(bars) < self.slow_period:
                return []

            closes = [b.close for b in bars]
            fast_ma = sum(closes[-self.fast_period :]) / self.fast_period
            slow_ma = sum(closes) / self.slow_period

            if fast_ma > slow_ma:
                return [Signal(symbol=self.symbol, weight=1.0)]
            return []

    # 定义参数范围
    param_ranges = {"fast_period": (5, 20, int), "slow_period": (20, 60, int)}

    # 回测配置
    data_source = ALDSDataSource()
    backtest_config = BacktestConfig(start=date(2023, 1, 1), end=date(2023, 12, 31), initial_capital=1_000_000.0, show_progress=False)

    # 执行遗传算法
    ga = GeneticAlgorithm(strategy_class=ParameterizedStrategy, param_ranges=param_ranges, data_source=data_source, backtest_config=backtest_config, population_size=20, generations=10, mutation_rate=0.1, crossover_rate=0.7, scoring="sharpe")

    best_params = ga.run(verbose=True)
    print(f"最优参数: {best_params}")


def main():
    """运行遗传算法示例"""
    example_genetic_algorithm()


if __name__ == "__main__":
    main()
