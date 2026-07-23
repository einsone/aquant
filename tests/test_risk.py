"""RiskManager 和 RiskRule 单元测试"""

from datetime import date

import pytest

from aquant.core.context import Context
from aquant.portfolio.portfolio import Portfolio
from aquant.portfolio.position import PositionView
from aquant.portfolio.query import PortfolioQueryService
from aquant.risk import ConcentrationRule, MaxDrawdownRule, MaxLeverageRule, MaxPositionSizeRule, RiskManager, RiskRule
from aquant.strategy.signal import Signal


class TestMaxPositionSizeRule:
    """测试单仓位最大市值规则"""

    @pytest.fixture
    def context(self):
        """创建测试上下文"""
        query = PortfolioQueryService(daily_nav=[], trade_log=[])
        return Context(current_date=date(2024, 1, 1), positions={}, cash=1000000.0, total_value=1000000.0, query=query)

    @pytest.fixture
    def portfolio(self):
        """创建测试组合"""
        return Portfolio(initial_capital=1000000.0)

    def test_accept_within_limit(self, context, portfolio):
        """测试市值在限制内的信号通过"""
        rule = MaxPositionSizeRule(max_ratio=0.1)
        signal = Signal(symbol="000001.SZ", weight=0.05)  # 5% 权重
        assert rule.check(signal, portfolio, context) is True

    def test_reject_over_limit(self, context, portfolio):
        """测试市值超过限制的信号被拒绝"""
        rule = MaxPositionSizeRule(max_ratio=0.1)
        signal = Signal(symbol="000001.SZ", weight=0.15)  # 15% 权重
        assert rule.check(signal, portfolio, context) is False

    def test_accept_zero_weight(self, context, portfolio):
        """测试零权重信号通过（平仓）"""
        rule = MaxPositionSizeRule(max_ratio=0.1)
        signal = Signal(symbol="000001.SZ", weight=0.0)
        assert rule.check(signal, portfolio, context) is True


class TestMaxDrawdownRule:
    """测试最大回撤规则"""

    @pytest.fixture
    def portfolio(self):
        """创建测试组合"""
        return Portfolio(initial_capital=1000000.0)

    def test_accept_below_drawdown_limit(self, portfolio):
        """测试回撤低于限制时开仓信号通过"""
        from aquant.portfolio.position import NavRecord

        query = PortfolioQueryService(
            daily_nav=[
                NavRecord(date=date(2024, 1, 1), total=1100000, cash=0, position_count=1),  # 峰值
                NavRecord(date=date(2024, 1, 2), total=1050000, cash=0, position_count=1),  # 回撤约 4.5%
            ],
            trade_log=[],
        )
        context = Context(current_date=date(2024, 1, 2), positions={}, cash=1050000.0, total_value=1050000.0, query=query)

        rule = MaxDrawdownRule(max_dd=0.1)  # 10% 限制
        signal = Signal(symbol="000001.SZ", weight=0.1)
        assert rule.check(signal, portfolio, context) is True

    def test_reject_over_drawdown_limit(self, portfolio):
        """测试回撤超过限制时开仓信号被拒绝"""
        from aquant.portfolio.position import NavRecord

        query = PortfolioQueryService(
            daily_nav=[
                NavRecord(date=date(2024, 1, 1), total=1100000, cash=0, position_count=1),
                NavRecord(date=date(2024, 1, 2), total=950000, cash=0, position_count=1),  # 回撤约 13.6%
            ],
            trade_log=[],
        )
        context = Context(current_date=date(2024, 1, 2), positions={}, cash=950000.0, total_value=950000.0, query=query)

        rule = MaxDrawdownRule(max_dd=0.1)
        signal = Signal(symbol="000001.SZ", weight=0.1)
        assert rule.check(signal, portfolio, context) is False

    def test_accept_close_position(self, portfolio):
        """测试回撤超限时平仓信号仍然通过"""
        from aquant.portfolio.position import NavRecord

        query = PortfolioQueryService(daily_nav=[NavRecord(date=date(2024, 1, 1), total=1100000, cash=0, position_count=1), NavRecord(date=date(2024, 1, 2), total=950000, cash=0, position_count=1)], trade_log=[])
        context = Context(current_date=date(2024, 1, 2), positions={}, cash=950000.0, total_value=950000.0, query=query)

        rule = MaxDrawdownRule(max_dd=0.1)
        signal = Signal(symbol="000001.SZ", weight=0.0)  # 平仓
        assert rule.check(signal, portfolio, context) is True


class TestMaxLeverageRule:
    """测试最大杠杆规则"""

    @pytest.fixture
    def portfolio(self):
        """创建测试组合"""
        return Portfolio(initial_capital=1000000.0)

    def test_accept_within_leverage(self, portfolio):
        """测试持仓总市值在杠杆限制内"""
        query = PortfolioQueryService(daily_nav=[], trade_log=[])
        context = Context(current_date=date(2024, 1, 1), positions={"000001.SZ": PositionView(symbol="000001.SZ", shares=10000, tradeable_shares=10000, cost_basis=10.0, market_value=120000.0, last_close=12.0)}, cash=900000.0, total_value=1020000.0, query=query)

        rule = MaxLeverageRule(max_leverage=2.0)
        signal = Signal(symbol="600000.SH", weight=0.5)  # 新增 50 万持仓
        # MaxLeverageRule 只累计权重，不拦截单个信号
        assert rule.check(signal, portfolio, context) is True

    def test_cumulative_weight_tracking(self, portfolio):
        """测试累计权重跟踪"""
        query = PortfolioQueryService(daily_nav=[], trade_log=[])
        context = Context(current_date=date(2024, 1, 1), positions={}, cash=1000000.0, total_value=1000000.0, query=query)

        rule = MaxLeverageRule(max_leverage=1.5)

        # 处理多个信号，累计权重
        signal1 = Signal(symbol="000001.SZ", weight=0.5)
        signal2 = Signal(symbol="600000.SH", weight=0.5)
        signal3 = Signal(symbol="000002.SZ", weight=0.5)

        assert rule.check(signal1, portfolio, context) is True
        assert rule._total_weight == 0.5

        assert rule.check(signal2, portfolio, context) is True
        assert rule._total_weight == 1.0

        assert rule.check(signal3, portfolio, context) is True
        assert rule._total_weight == 1.5

        # 重置后权重归零
        rule.reset()
        assert rule._total_weight == 0.0


class TestConcentrationRule:
    """测试集中度规则"""

    @pytest.fixture
    def portfolio(self):
        """创建测试组合"""
        return Portfolio(initial_capital=1000000.0)

    def test_accept_within_concentration(self, portfolio):
        """测试单仓位市值占比在限制内"""
        query = PortfolioQueryService(daily_nav=[], trade_log=[])
        context = Context(current_date=date(2024, 1, 1), positions={}, cash=1000000.0, total_value=1000000.0, query=query)

        rule = ConcentrationRule(top_n=5, max_concentration=0.3)
        signal = Signal(symbol="000001.SZ", weight=0.25)
        assert rule.check(signal, portfolio, context) is True

    def test_reject_over_concentration(self, portfolio):
        """测试单仓位市值占比超过限制"""
        query = PortfolioQueryService(daily_nav=[], trade_log=[])
        context = Context(current_date=date(2024, 1, 1), positions={}, cash=1000000.0, total_value=1000000.0, query=query)

        rule = ConcentrationRule(top_n=5, max_concentration=0.3)
        signal = Signal(symbol="000001.SZ", weight=0.4)
        assert rule.check(signal, portfolio, context) is False

    def test_accept_close_position(self, portfolio):
        """测试平仓信号通过"""
        query = PortfolioQueryService(daily_nav=[], trade_log=[])
        context = Context(current_date=date(2024, 1, 1), positions={}, cash=1000000.0, total_value=1000000.0, query=query)

        rule = ConcentrationRule(top_n=5, max_concentration=0.3)
        signal = Signal(symbol="000001.SZ", weight=0.0)
        assert rule.check(signal, portfolio, context) is True


class CustomResetRule(RiskRule):
    """自定义规则，带 reset 方法"""

    def __init__(self):
        self.call_count = 0

    def check(self, signal: Signal, portfolio: Portfolio, context: Context) -> bool:
        self.call_count += 1
        return True

    def reset(self):
        self.call_count = 0


class TestRiskManager:
    """测试 RiskManager 组合规则"""

    @pytest.fixture
    def context(self):
        """创建测试上下文"""
        query = PortfolioQueryService(daily_nav=[], trade_log=[])
        return Context(current_date=date(2024, 1, 1), positions={}, cash=1000000.0, total_value=1000000.0, query=query)

    @pytest.fixture
    def portfolio(self):
        """创建测试组合"""
        return Portfolio(initial_capital=1000000.0)

    def test_default_manager_accepts_all(self, context, portfolio):
        """测试默认 RiskManager 接受所有信号"""
        manager = RiskManager()
        signals = [Signal(symbol="000001.SZ", weight=0.5), Signal(symbol="600000.SH", weight=0.5)]
        filtered = manager.check_signals(signals, portfolio, context)
        assert len(filtered) == 2

    def test_multiple_rules_conjunction(self, context, portfolio):
        """测试多个规则的与逻辑"""
        manager = RiskManager(rules=[MaxPositionSizeRule(max_ratio=0.2), ConcentrationRule(top_n=5, max_concentration=0.15)])

        signals = [
            Signal(symbol="000001.SZ", weight=0.1),  # 通过两个规则
            Signal(symbol="600000.SH", weight=0.25),  # 违反单标的规则
        ]

        filtered = manager.check_signals(signals, portfolio, context)
        assert len(filtered) == 1
        assert filtered[0].symbol == "000001.SZ"

    def test_reset_rules(self):
        """测试规则重置功能"""
        rule = CustomResetRule()
        manager = RiskManager(rules=[rule])

        query = PortfolioQueryService(daily_nav=[], trade_log=[])
        context = Context(current_date=date(2024, 1, 1), positions={}, cash=1000000.0, total_value=1000000.0, query=query)
        portfolio = Portfolio(initial_capital=1000000.0)

        signals = [Signal(symbol="000001.SZ", weight=0.1)]
        manager.check_signals(signals, portfolio, context)
        assert rule.call_count == 1

        # 通过重新调用 check_signals 会自动触发 reset
        manager.check_signals(signals, portfolio, context)
        # 第二次调用会先 reset，所以累计是 1 而不是 2
        assert rule.call_count == 1

    def test_empty_signals(self, context, portfolio):
        """测试空信号列表"""
        manager = RiskManager(rules=[MaxPositionSizeRule(max_ratio=0.1)])
        filtered = manager.check_signals([], portfolio, context)
        assert len(filtered) == 0

    def test_all_rejected(self, context, portfolio):
        """测试所有信号都被拒绝"""
        manager = RiskManager(rules=[MaxPositionSizeRule(max_ratio=0.05)])
        signals = [
            Signal(symbol="000001.SZ", weight=0.1),  # 10% 权重
            Signal(symbol="600000.SH", weight=0.2),  # 20% 权重
        ]
        filtered = manager.check_signals(signals, portfolio, context)
        assert len(filtered) == 0
