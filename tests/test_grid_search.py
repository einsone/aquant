"""测试网格搜索优化器"""

from datetime import date, timedelta

from aquant.core.engine import BacktestConfig
from aquant.data.source import DataSource
from aquant.market.bar import DayBar
from aquant.optimization.grid_search import grid_search
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


class ParameterizedStrategy(Strategy):
    """可参数化的测试策略"""

    warmup_period = 1
    rebalance_mode = "replace"

    def __init__(self, period: int = 20, threshold: float = 0.02):
        self.period = period
        self.threshold = threshold
        self.prices = {}
        self.universe = {"000001.SZ", "000002.SZ"}  # 默认 universe
        self.data_source = None  # 类型提示：将在运行时注入

    def on_bar(self, context):
        # 简单动量策略
        bars = self.data_source.load_bars(context.current_date, self.universe)  # type: ignore[union-attr]

        for symbol, bar in bars.items():
            if symbol not in self.prices:
                self.prices[symbol] = []
            self.prices[symbol].append(bar.close)
            self.prices[symbol] = self.prices[symbol][-self.period :]

        # 选择动量最强的股票
        momentum = {}
        for symbol, prices in self.prices.items():
            if len(prices) >= self.period:
                ret = (prices[-1] - prices[0]) / prices[0]
                if ret > self.threshold:
                    momentum[symbol] = ret

        if momentum:
            best = max(momentum.items(), key=lambda x: x[1])[0]
            return [Signal(symbol=best, weight=1.0)]

        return []


def test_grid_search_basic():
    """测试基本网格搜索"""
    data_source = MockDataSource()

    config = BacktestConfig(start=date(2023, 1, 1), end=date(2023, 2, 28), initial_capital=100000, show_progress=False)

    param_grid = {"period": [10, 20], "threshold": [0.01, 0.02]}

    results = grid_search(strategy_cls=ParameterizedStrategy, param_grid=param_grid, config=config, data_source=data_source)

    # 应该有 2 * 2 = 4 种组合
    assert len(results) == 4
    assert "period" in results.columns
    assert "threshold" in results.columns
    assert "sharpe" in results.columns


def test_grid_search_empty_params():
    """测试空参数网格"""
    data_source = MockDataSource()

    config = BacktestConfig(start=date(2023, 1, 1), end=date(2023, 1, 31), initial_capital=100000, show_progress=False)

    results = grid_search(strategy_cls=ParameterizedStrategy, param_grid={}, config=config, data_source=data_source)

    assert len(results) == 0


def test_grid_search_single_param():
    """测试单参数优化"""
    data_source = MockDataSource()

    config = BacktestConfig(start=date(2023, 1, 1), end=date(2023, 1, 31), initial_capital=100000, show_progress=False)

    param_grid = {"period": [5, 10, 15, 20]}

    results = grid_search(strategy_cls=ParameterizedStrategy, param_grid=param_grid, config=config, data_source=data_source, metric="total_return")

    assert len(results) == 4
    assert "period" in results.columns
    assert "total_return" in results.columns


def test_grid_search_find_best():
    """测试找到最佳参数"""
    data_source = MockDataSource()

    config = BacktestConfig(start=date(2023, 1, 1), end=date(2023, 2, 28), initial_capital=100000, show_progress=False)

    param_grid = {"period": [10, 20], "threshold": [0.01, 0.02]}

    results = grid_search(strategy_cls=ParameterizedStrategy, param_grid=param_grid, config=config, data_source=data_source, metric="sharpe")

    # 找出最佳参数
    best_row = results.sort("sharpe", descending=True)[0]
    assert "period" in best_row.columns
    assert "threshold" in best_row.columns


def test_grid_search_multiple_metrics():
    """测试多个指标同时记录"""
    data_source = MockDataSource()

    config = BacktestConfig(start=date(2023, 1, 1), end=date(2023, 1, 31), initial_capital=100000, show_progress=False)

    param_grid = {"period": [10, 20]}

    results = grid_search(strategy_cls=ParameterizedStrategy, param_grid=param_grid, config=config, data_source=data_source)

    # 所有常见指标都应该在结果中
    assert "total_return" in results.columns
    assert "sharpe" in results.columns
    assert "max_drawdown" in results.columns
