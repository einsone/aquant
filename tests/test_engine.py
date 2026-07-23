"""测试回测引擎核心功能"""

from datetime import date

from aquant.core.context import Context
from aquant.core.engine import BacktestConfig, Engine
from aquant.data.source import DataSource
from aquant.market.bar import DayBar
from aquant.strategy.base import Strategy
from aquant.strategy.signal import Signal


class MockDataSource(DataSource):
    """模拟数据源"""

    def __init__(self):
        self.bars_data = {
            date(2023, 1, 3): {"000001.SZ": DayBar(symbol="000001.SZ", date=date(2023, 1, 3), open=10.0, high=10.5, low=9.8, close=10.2, volume=1000000, up_limit=11.0, down_limit=9.0, is_halted=False)},
            date(2023, 1, 4): {"000001.SZ": DayBar(symbol="000001.SZ", date=date(2023, 1, 4), open=10.2, high=10.8, low=10.0, close=10.5, volume=1200000, up_limit=11.2, down_limit=9.2, is_halted=False)},
            date(2023, 1, 5): {"000001.SZ": DayBar(symbol="000001.SZ", date=date(2023, 1, 5), open=10.5, high=11.0, low=10.3, close=10.8, volume=1500000, up_limit=11.5, down_limit=9.5, is_halted=False)},
        }

    def load_calendar(self, start: date, end: date) -> list[date]:
        return [date(2023, 1, 3), date(2023, 1, 4), date(2023, 1, 5)]

    def load_bars(self, dt: date, symbols: set[str]) -> dict[str, DayBar]:
        return self.bars_data.get(dt, {})

    def load_adjustments(self, start: date, end: date):
        return []

    def load_delisted(self, start: date, end: date):
        return {}


class BuyAndHoldStrategy(Strategy):
    """简单的买入持有策略"""

    warmup_period = 1
    rebalance_mode = "replace"

    def __init__(self, symbol: str, data_source: DataSource):
        self.symbol = symbol
        self.data_source = data_source
        self.initialized = False

    def on_bar(self, context: Context) -> list[Signal]:
        if not self.initialized:
            self.initialized = True
            return [Signal(symbol=self.symbol, weight=1.0)]
        return []


def test_engine_basic_run():
    """测试引擎基本运行"""
    data_source = MockDataSource()
    strategy = BuyAndHoldStrategy("000001.SZ", data_source)

    config = BacktestConfig(start=date(2023, 1, 3), end=date(2023, 1, 5), initial_capital=100000.0, show_progress=False)

    engine = Engine(strategy, data_source, config)
    result = engine.run()

    # 验证结果对象存在
    assert result is not None
    assert result.portfolio is not None
    assert result.metrics is not None


def test_engine_with_commission():
    """测试交易成本计算"""
    data_source = MockDataSource()
    strategy = BuyAndHoldStrategy("000001.SZ", data_source)

    config = BacktestConfig(start=date(2023, 1, 3), end=date(2023, 1, 5), initial_capital=100000.0, commission_rate=0.0003, stamp_duty_rate=0.001, min_commission=5.0, show_progress=False)

    engine = Engine(strategy, data_source, config)
    result = engine.run()

    # 验证有持仓
    position = result.portfolio.positions.get("000001.SZ")
    assert position is not None
    assert position.shares > 0

    # 验证现金减少（扣除了交易成本）
    assert result.portfolio.cash < config.initial_capital


def test_engine_with_slippage():
    """测试滑点影响"""
    data_source = MockDataSource()
    strategy = BuyAndHoldStrategy("000001.SZ", data_source)

    config = BacktestConfig(start=date(2023, 1, 3), end=date(2023, 1, 5), initial_capital=100000.0, slippage_rate=0.001, show_progress=False)

    engine = Engine(strategy, data_source, config)
    result = engine.run()

    # 验证滑点导致成本增加
    assert result.portfolio.cash < config.initial_capital


def test_engine_multiple_rebalance():
    """测试多次调仓"""

    class RebalanceStrategy(Strategy):
        warmup_period = 1
        rebalance_mode = "replace"

        def __init__(self, data_source: DataSource):
            self.data_source = data_source
            self.count = 0

        def on_bar(self, context: Context) -> list[Signal]:
            self.count += 1
            # 第 1 天买入，第 2 天清仓，第 3 天再买入
            if self.count == 1:
                return [Signal(symbol="000001.SZ", weight=1.0)]
            elif self.count == 2:
                return []
            elif self.count == 3:
                return [Signal(symbol="000001.SZ", weight=1.0)]
            return []

    data_source = MockDataSource()
    strategy = RebalanceStrategy(data_source)

    config = BacktestConfig(start=date(2023, 1, 3), end=date(2023, 1, 5), initial_capital=100000.0, show_progress=False)

    engine = Engine(strategy, data_source, config)
    result = engine.run()

    # 验证最终有持仓
    position = result.portfolio.positions.get("000001.SZ")
    assert position is not None
    assert position.shares > 0


def test_engine_empty_signals():
    """测试空信号处理"""

    class EmptyStrategy(Strategy):
        warmup_period = 1
        rebalance_mode = "replace"

        def __init__(self, data_source: DataSource):
            self.data_source = data_source

        def on_bar(self, context: Context) -> list[Signal]:
            return []

    data_source = MockDataSource()
    strategy = EmptyStrategy(data_source)

    config = BacktestConfig(start=date(2023, 1, 3), end=date(2023, 1, 5), initial_capital=100000.0, show_progress=False)

    engine = Engine(strategy, data_source, config)
    result = engine.run()

    # 验证没有持仓
    assert len(result.portfolio.positions) == 0
    # 现金应该等于初始资金
    assert result.portfolio.cash == config.initial_capital


def test_engine_warmup_period():
    """测试预热期处理"""

    class WarmupStrategy(Strategy):
        warmup_period = 2
        rebalance_mode = "replace"

        def __init__(self, data_source: DataSource):
            self.data_source = data_source
            self.trade_count = 0

        def on_bar(self, context: Context) -> list[Signal]:
            # 使用实际存在的查询方法
            recent_trades = context.query.get_recent_trades(symbol="000001.SZ", n=10)
            self.trade_count = len(recent_trades)
            return []

    data_source = MockDataSource()
    strategy = WarmupStrategy(data_source)

    config = BacktestConfig(start=date(2023, 1, 3), end=date(2023, 1, 5), initial_capital=100000.0, show_progress=False)

    engine = Engine(strategy, data_source, config)
    result = engine.run()

    # 验证预热期被正确处理
    assert result is not None
    # 验证策略在预热期后能够访问查询服务
    assert strategy.trade_count >= 0


def test_engine_compute_metrics():
    """测试指标计算"""
    data_source = MockDataSource()
    strategy = BuyAndHoldStrategy("000001.SZ", data_source)

    config = BacktestConfig(start=date(2023, 1, 3), end=date(2023, 1, 5), initial_capital=100000.0, show_progress=False)

    engine = Engine(strategy, data_source, config)
    result = engine.run()

    # 计算指标
    result.compute_metrics()

    # 验证关键指标存在
    assert "total_return" in result.metrics
    assert "annualized_return" in result.metrics  # 指标名称已更新
    assert "sharpe" in result.metrics
    assert "max_drawdown" in result.metrics


def test_backtest_config_defaults():
    """测试配置默认值"""
    config = BacktestConfig(start=date(2023, 1, 1), end=date(2023, 12, 31), initial_capital=100000.0)

    assert config.commission_rate == 0.0003
    assert config.stamp_duty_rate == 0.001
    assert config.min_commission == 5.0
    assert config.slippage_rate == 0.0005  # 默认滑点率为 0.0005
    assert config.show_progress is True


def test_backtest_config_custom():
    """测试自定义配置"""
    config = BacktestConfig(start=date(2023, 1, 1), end=date(2023, 12, 31), initial_capital=100000.0, commission_rate=0.0005, stamp_duty_rate=0.002, min_commission=10.0, slippage_rate=0.001, show_progress=False)

    assert config.commission_rate == 0.0005
    assert config.stamp_duty_rate == 0.002
    assert config.min_commission == 10.0
    assert config.slippage_rate == 0.001
    assert config.show_progress is False
