"""测试 Walk-Forward 分析"""

from datetime import date, timedelta

from aquant.core.engine import BacktestConfig
from aquant.data.source import DataSource
from aquant.market.bar import DayBar
from aquant.optimization.walk_forward import walk_forward
from aquant.strategy.base import Strategy
from aquant.strategy.signal import Signal


class MockDataSource(DataSource):
    """简单的模拟数据源"""

    def __init__(self):
        # 创建 365 天的日历
        self.calendar = [date(2023, 1, 1) + timedelta(days=i) for i in range(365)]

    def load_calendar(self, start: date, end: date) -> list[date]:
        return [d for d in self.calendar if start <= d <= end]

    def load_bars(self, dt: date, symbols: set[str]) -> dict[str, DayBar]:
        if dt not in self.calendar:
            return {}

        idx = self.calendar.index(dt)
        bars = {}

        for symbol in symbols:
            # 生成简单的价格序列
            price = 10.0 + idx * 0.01
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
        bars = self.data_source.load_bars(context.current_date, self.universe)  # type: ignore[union-attr]

        for symbol, bar in bars.items():
            if symbol not in self.prices:
                self.prices[symbol] = []
            self.prices[symbol].append(bar.close)
            self.prices[symbol] = self.prices[symbol][-self.period :]

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


def test_walk_forward_basic():
    """测试基本 Walk-Forward 分析"""
    data_source = MockDataSource()

    config = BacktestConfig(start=date(2023, 1, 1), end=date(2023, 12, 31), initial_capital=100000, show_progress=False)

    param_grid = {"period": [10, 20], "threshold": [0.01, 0.02]}

    results = walk_forward(strategy_cls=ParameterizedStrategy, param_grid=param_grid, config=config, data_source=data_source, train_window=60, test_window=30)

    # 应该生成多个折
    assert len(results) > 0
    assert "fold_train_start" in results.columns
    assert "fold_test_start" in results.columns
    assert "period" in results.columns
    assert "threshold" in results.columns


def test_walk_forward_empty_params():
    """测试空参数网格"""
    data_source = MockDataSource()

    config = BacktestConfig(start=date(2023, 1, 1), end=date(2023, 3, 31), initial_capital=100000, show_progress=False)

    results = walk_forward(strategy_cls=ParameterizedStrategy, param_grid={}, config=config, data_source=data_source)

    assert len(results) == 0


def test_walk_forward_fold_splitting():
    """测试折叠分割"""
    data_source = MockDataSource()

    config = BacktestConfig(start=date(2023, 1, 1), end=date(2023, 6, 30), initial_capital=100000, show_progress=False)

    param_grid = {"period": [10, 20]}

    results = walk_forward(strategy_cls=ParameterizedStrategy, param_grid=param_grid, config=config, data_source=data_source, train_window=30, test_window=15)

    # 验证折数
    # 180 天 = 30(训练) + 15(测试) + 30(训练) + 15(测试) + ...
    # 应该有多个完整的折
    assert len(results) >= 2

    # 验证每折的日期范围
    for i in range(len(results)):
        train_start = results["fold_train_start"][i]
        train_end = results["fold_train_end"][i]
        test_start = results["fold_test_start"][i]
        test_end = results["fold_test_end"][i]

        assert train_start < train_end
        assert train_end < test_start
        assert test_start <= test_end


def test_walk_forward_single_fold():
    """测试单折场景"""
    data_source = MockDataSource()

    config = BacktestConfig(start=date(2023, 1, 1), end=date(2023, 3, 31), initial_capital=100000, show_progress=False)

    param_grid = {"period": [10, 20]}

    results = walk_forward(strategy_cls=ParameterizedStrategy, param_grid=param_grid, config=config, data_source=data_source, train_window=60, test_window=20)

    # 90 天只能生成 1 折
    assert len(results) == 1


def test_walk_forward_metrics():
    """测试返回的指标"""
    data_source = MockDataSource()

    config = BacktestConfig(start=date(2023, 1, 1), end=date(2023, 6, 30), initial_capital=100000, show_progress=False)

    param_grid = {"period": [10]}

    results = walk_forward(strategy_cls=ParameterizedStrategy, param_grid=param_grid, config=config, data_source=data_source, train_window=50, test_window=25, metric="sharpe")

    # 验证返回的指标
    assert len(results) > 0
    assert "sharpe" in results.columns
    assert "total_return" in results.columns
    assert "max_drawdown" in results.columns


def test_walk_forward_insufficient_data():
    """测试数据不足场景"""
    data_source = MockDataSource()

    config = BacktestConfig(start=date(2023, 1, 1), end=date(2023, 1, 31), initial_capital=100000, show_progress=False)

    param_grid = {"period": [10]}

    results = walk_forward(strategy_cls=ParameterizedStrategy, param_grid=param_grid, config=config, data_source=data_source, train_window=60, test_window=30)

    # 数据不足无法生成折
    assert len(results) == 0


def test_walk_forward_different_metrics():
    """测试不同优化指标"""
    data_source = MockDataSource()

    config = BacktestConfig(start=date(2023, 1, 1), end=date(2023, 6, 30), initial_capital=100000, show_progress=False)

    param_grid = {"period": [10, 20]}

    # 测试不同指标
    for metric in ["sharpe", "total_return", "calmar"]:
        results = walk_forward(strategy_cls=ParameterizedStrategy, param_grid=param_grid, config=config, data_source=data_source, train_window=50, test_window=25, metric=metric)

        assert len(results) > 0
        assert metric in results.columns
