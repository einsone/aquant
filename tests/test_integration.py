"""端到端集成测试"""

from datetime import date

from aquant.core.context import Context
from aquant.core.engine import BacktestConfig, Engine
from aquant.data.source import DataSource
from aquant.market.bar import DayBar
from aquant.strategy.base import Strategy
from aquant.strategy.signal import Signal


class MockDataSource(DataSource):
    """模拟数据源 - 提供完整的市场数据"""

    def __init__(self):
        # 模拟 3 只股票的 5 天数据
        self.calendar = [date(2023, 1, 3), date(2023, 1, 4), date(2023, 1, 5), date(2023, 1, 6), date(2023, 1, 9)]

        # 股票 A：稳定上涨
        self.stock_a_prices = [10.0, 10.2, 10.5, 10.8, 11.0]

        # 股票 B：震荡
        self.stock_b_prices = [20.0, 19.5, 20.5, 20.0, 20.2]

        # 股票 C：下跌
        self.stock_c_prices = [30.0, 29.0, 28.0, 27.5, 27.0]

    def load_calendar(self, start: date, end: date) -> list[date]:
        return [d for d in self.calendar if start <= d <= end]

    def load_bars(self, dt: date, symbols: set[str]) -> dict[str, DayBar]:
        if dt not in self.calendar:
            return {}

        idx = self.calendar.index(dt)
        bars = {}

        if "000001.SZ" in symbols:
            price = self.stock_a_prices[idx]
            bars["000001.SZ"] = DayBar(symbol="000001.SZ", date=dt, open=price * 0.99, high=price * 1.02, low=price * 0.98, close=price, volume=1000000, up_limit=price * 1.1, down_limit=price * 0.9, is_halted=False)

        if "000002.SZ" in symbols:
            price = self.stock_b_prices[idx]
            bars["000002.SZ"] = DayBar(symbol="000002.SZ", date=dt, open=price * 0.99, high=price * 1.02, low=price * 0.98, close=price, volume=1200000, up_limit=price * 1.1, down_limit=price * 0.9, is_halted=False)

        if "600000.SH" in symbols:
            price = self.stock_c_prices[idx]
            bars["600000.SH"] = DayBar(symbol="600000.SH", date=dt, open=price * 0.99, high=price * 1.02, low=price * 0.98, close=price, volume=800000, up_limit=price * 1.1, down_limit=price * 0.9, is_halted=False)

        return bars

    def load_adjustments(self, start: date, end: date):
        return []

    def load_delisted(self, start: date, end: date):
        return {}


class MomentumStrategy(Strategy):
    """动量策略 - 买入涨幅最大的股票"""

    warmup_period = 1
    rebalance_mode = "replace"

    def __init__(self, data_source: DataSource):
        self.data_source = data_source
        self.universe = ["000001.SZ", "000002.SZ", "600000.SH"]
        self.prev_prices = {}

    def on_bar(self, context: Context) -> list[Signal]:
        if context.current_date == date(2023, 1, 3):
            # 第一天记录价格
            bars = self.data_source.load_bars(context.current_date, set(self.universe))
            for symbol, bar in bars.items():
                self.prev_prices[symbol] = bar.close
            # 第一天平均分配
            return [Signal(symbol="000001.SZ", weight=0.33), Signal(symbol="000002.SZ", weight=0.33), Signal(symbol="600000.SH", weight=0.34)]

        # 计算动量并选择最强的股票
        bars = self.data_source.load_bars(context.current_date, set(self.universe))
        momentum = {}
        for symbol, bar in bars.items():
            if symbol in self.prev_prices:
                ret = (bar.close - self.prev_prices[symbol]) / self.prev_prices[symbol]
                momentum[symbol] = ret
            self.prev_prices[symbol] = bar.close

        if momentum:
            best_symbol = max(momentum.items(), key=lambda x: x[1])[0]
            return [Signal(symbol=best_symbol, weight=1.0)]

        return []


class RotationStrategy(Strategy):
    """轮动策略 - 每天持仓不同股票"""

    warmup_period = 1
    rebalance_mode = "replace"

    def __init__(self, data_source: DataSource):
        self.data_source = data_source
        self.symbols = ["000001.SZ", "000002.SZ", "600000.SH"]
        self.current_idx = 0

    def on_bar(self, context: Context) -> list[Signal]:
        # 轮流持仓
        symbol = self.symbols[self.current_idx % len(self.symbols)]
        self.current_idx += 1
        return [Signal(symbol=symbol, weight=1.0)]


def test_end_to_end_buy_and_hold():
    """测试买入持有策略的完整流程"""

    class BuyAndHoldStrategy(Strategy):
        warmup_period = 1
        rebalance_mode = "replace"

        def __init__(self, data_source: DataSource):
            self.data_source = data_source
            self.initialized = False

        def on_bar(self, context: Context) -> list[Signal]:
            if not self.initialized:
                self.initialized = True
                return [Signal(symbol="000001.SZ", weight=1.0)]
            return []

    data_source = MockDataSource()
    strategy = BuyAndHoldStrategy(data_source)

    config = BacktestConfig(start=date(2023, 1, 3), end=date(2023, 1, 9), initial_capital=100000.0, show_progress=False)

    engine = Engine(strategy, data_source, config)
    result = engine.run()

    # 验证持仓
    position = result.portfolio.positions.get("000001.SZ")
    assert position is not None
    assert position.shares > 0

    # 计算指标
    result.compute_metrics()

    # 股票 A 从 10 涨到 11，应该盈利
    assert result.metrics["total_return"] > 0


def test_end_to_end_momentum_strategy():
    """测试动量策略的完整流程"""
    data_source = MockDataSource()
    strategy = MomentumStrategy(data_source)

    config = BacktestConfig(start=date(2023, 1, 3), end=date(2023, 1, 9), initial_capital=100000.0, show_progress=False)

    engine = Engine(strategy, data_source, config)
    result = engine.run()

    # 验证回测完成
    assert result is not None

    # 计算指标
    result.compute_metrics()

    # 验证指标存在
    assert "total_return" in result.metrics
    assert "sharpe" in result.metrics


def test_end_to_end_rotation_strategy():
    """测试轮动策略的完整流程"""
    data_source = MockDataSource()
    strategy = RotationStrategy(data_source)

    config = BacktestConfig(start=date(2023, 1, 3), end=date(2023, 1, 9), initial_capital=100000.0, show_progress=False)

    engine = Engine(strategy, data_source, config)
    result = engine.run()

    # 验证有交易发生
    assert len(result.portfolio.trade_log) > 0

    # 计算指标
    result.compute_metrics()


def test_end_to_end_with_high_commission():
    """测试高手续费场景"""

    class SimpleStrategy(Strategy):
        warmup_period = 1
        rebalance_mode = "replace"

        def __init__(self, data_source: DataSource):
            self.data_source = data_source

        def on_bar(self, context: Context) -> list[Signal]:
            return [Signal(symbol="000001.SZ", weight=1.0)]

    data_source = MockDataSource()
    strategy = SimpleStrategy(data_source)

    config = BacktestConfig(
        start=date(2023, 1, 3),
        end=date(2023, 1, 9),
        initial_capital=100000.0,
        commission_rate=0.001,  # 高佣金
        stamp_duty_rate=0.002,  # 高印花税
        show_progress=False,
    )

    engine = Engine(strategy, data_source, config)
    result = engine.run()

    # 高手续费会显著影响收益
    result.compute_metrics()
    assert "total_return" in result.metrics


def test_end_to_end_with_slippage():
    """测试滑点场景"""

    class SimpleStrategy(Strategy):
        warmup_period = 1
        rebalance_mode = "replace"

        def __init__(self, data_source: DataSource):
            self.data_source = data_source

        def on_bar(self, context: Context) -> list[Signal]:
            return [Signal(symbol="000001.SZ", weight=1.0)]

    data_source = MockDataSource()
    strategy = SimpleStrategy(data_source)

    config = BacktestConfig(
        start=date(2023, 1, 3),
        end=date(2023, 1, 9),
        initial_capital=100000.0,
        slippage_rate=0.002,  # 千二滑点
        show_progress=False,
    )

    engine = Engine(strategy, data_source, config)
    result = engine.run()

    # 滑点会影响成交价格
    result.compute_metrics()
    assert result is not None


def test_end_to_end_multiple_rebalances():
    """测试多次调仓"""

    class FrequentRebalanceStrategy(Strategy):
        warmup_period = 1
        rebalance_mode = "replace"

        def __init__(self, data_source: DataSource):
            self.data_source = data_source
            self.count = 0

        def on_bar(self, context: Context) -> list[Signal]:
            # 每天换股
            self.count += 1
            if self.count % 2 == 1:
                return [Signal(symbol="000001.SZ", weight=1.0)]
            else:
                return [Signal(symbol="000002.SZ", weight=1.0)]

    data_source = MockDataSource()
    strategy = FrequentRebalanceStrategy(data_source)

    config = BacktestConfig(start=date(2023, 1, 3), end=date(2023, 1, 9), initial_capital=100000.0, show_progress=False)

    engine = Engine(strategy, data_source, config)
    result = engine.run()

    # 验证多次交易
    assert len(result.portfolio.trade_log) > 2


def test_end_to_end_empty_signals():
    """测试策略不产生信号"""

    class EmptyStrategy(Strategy):
        warmup_period = 1
        rebalance_mode = "replace"

        def __init__(self, data_source: DataSource):
            self.data_source = data_source

        def on_bar(self, context: Context) -> list[Signal]:
            return []

    data_source = MockDataSource()
    strategy = EmptyStrategy(data_source)

    config = BacktestConfig(start=date(2023, 1, 3), end=date(2023, 1, 9), initial_capital=100000.0, show_progress=False)

    engine = Engine(strategy, data_source, config)
    result = engine.run()

    # 无交易，现金不变
    assert result.portfolio.cash == config.initial_capital
    assert len(result.portfolio.positions) == 0


def test_end_to_end_metrics_calculation():
    """测试指标计算的完整流程"""

    class SimpleStrategy(Strategy):
        warmup_period = 1
        rebalance_mode = "replace"

        def __init__(self, data_source: DataSource):
            self.data_source = data_source
            self.initialized = False

        def on_bar(self, context: Context) -> list[Signal]:
            if not self.initialized:
                self.initialized = True
                return [Signal(symbol="000001.SZ", weight=1.0)]
            return []

    data_source = MockDataSource()
    strategy = SimpleStrategy(data_source)

    config = BacktestConfig(start=date(2023, 1, 3), end=date(2023, 1, 9), initial_capital=100000.0, show_progress=False)

    engine = Engine(strategy, data_source, config)
    result = engine.run()

    # 计算所有指标
    result.compute_metrics()

    # 验证关键指标都存在
    required_metrics = ["total_return", "annualized_return", "sharpe", "max_drawdown", "win_rate"]

    for metric in required_metrics:
        assert metric in result.metrics


def test_end_to_end_report_generation():
    """测试报告生成"""

    class SimpleStrategy(Strategy):
        warmup_period = 1
        rebalance_mode = "replace"

        def __init__(self, data_source: DataSource):
            self.data_source = data_source
            self.initialized = False

        def on_bar(self, context: Context) -> list[Signal]:
            if not self.initialized:
                self.initialized = True
                return [Signal(symbol="000001.SZ", weight=1.0)]
            return []

    data_source = MockDataSource()
    strategy = SimpleStrategy(data_source)

    config = BacktestConfig(start=date(2023, 1, 3), end=date(2023, 1, 9), initial_capital=100000.0, show_progress=False)

    engine = Engine(strategy, data_source, config)
    result = engine.run()
    result.compute_metrics()

    # 生成文本报告
    report = result.report()
    assert len(report) > 0
    assert "Backtest Report" in report
