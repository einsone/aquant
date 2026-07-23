"""TradingRules 单元测试"""

from datetime import date, timedelta

import pytest

from aquant.matching.rules import FuturesRules, StockRules
from aquant.portfolio.position import Position


class TestStockRules:
    """测试 A 股交易规则（T+1）"""

    @pytest.fixture
    def rules(self):
        """创建股票交易规则实例"""
        return StockRules()

    def test_cannot_trade_bought_today(self, rules):
        """测试当日买入的持仓无法卖出"""
        date(2024, 1, 15)
        position = Position(
            symbol="000001.SZ",
            shares=1000,
            tradeable_shares=0,  # T+1，当日不可卖
            cost_basis=10.0,
            market_value=10000.0,
            last_close=10.0,
        )
        assert rules.can_trade_today("000001.SZ", position) is False

    def test_can_trade_bought_yesterday(self, rules):
        """测试前一日买入的持仓可以卖出"""
        today = date(2024, 1, 15)
        today - timedelta(days=1)
        position = Position(
            symbol="000001.SZ",
            shares=1000,
            tradeable_shares=1000,  # 前一日买入，今日可卖
            cost_basis=10.0,
            market_value=10000.0,
            last_close=10.0,
        )
        assert rules.can_trade_today("000001.SZ", position) is True

    def test_can_trade_no_position(self, rules):
        """测试无持仓时可以买入"""
        assert rules.can_trade_today("000001.SZ", None) is True

    def test_buy_commission_and_stamp_duty(self, rules):
        """测试买入佣金和印花税"""
        commission, stamp_duty = rules.compute_cost("buy", 100000.0)
        # 佣金：100000 * 0.0003 = 30，最低 5 元取 30
        # 印花税：买入为 0
        assert commission == pytest.approx(30.0)
        assert stamp_duty == 0.0

    def test_buy_commission_minimum(self, rules):
        """测试买入佣金最低限制"""
        commission, stamp_duty = rules.compute_cost("buy", 1000.0)
        # 佣金：1000 * 0.0003 = 0.3，最低 5 元取 5
        assert commission == 5.0
        assert stamp_duty == 0.0

    def test_sell_commission_and_stamp_duty(self, rules):
        """测试卖出佣金和印花税"""
        commission, stamp_duty = rules.compute_cost("sell", 100000.0)
        # 佣金：100000 * 0.0003 = 30
        # 印花税：100000 * 0.001 = 100
        assert commission == pytest.approx(30.0)
        assert stamp_duty == pytest.approx(100.0)

    def test_sell_commission_minimum(self, rules):
        """测试卖出佣金最低限制"""
        commission, stamp_duty = rules.compute_cost("sell", 1000.0)
        # 佣金：1000 * 0.0003 = 0.3，最低 5 元取 5
        # 印花税：1000 * 0.001 = 1
        assert commission == 5.0
        assert stamp_duty == 1.0

    def test_lot_size(self, rules):
        """测试股票最小交易单位"""
        assert rules.get_lot_size("000001.SZ") == 100


class TestFuturesRules:
    """测试期货交易规则（T+0）"""

    @pytest.fixture
    def rules(self):
        """创建期货交易规则实例"""
        return FuturesRules()

    def test_can_trade_anytime(self, rules):
        """测试期货可以随时交易（T+0）"""
        date(2024, 1, 15)
        position = Position(
            symbol="IF2401",
            shares=10,
            tradeable_shares=10,  # T+0，当日可卖
            cost_basis=5000.0,
            market_value=50000.0,
            last_close=5000.0,
        )
        # 即使当日买入也可以卖出
        assert rules.can_trade_today("IF2401", position) is True

    def test_can_trade_no_position(self, rules):
        """测试无持仓时可以开仓"""
        assert rules.can_trade_today("IF2401", None) is True

    def test_open_commission(self, rules):
        """测试开仓手续费"""
        commission, _ = rules.compute_cost("buy", 1000000.0)
        # 手续费：1000000 * 0.00005 = 50
        assert commission == pytest.approx(50.0)
        # 期货无印花税

    def test_close_commission(self, rules):
        """测试平仓手续费"""
        commission, _ = rules.compute_cost("sell", 1000000.0)
        # 手续费：1000000 * 0.00005 = 50
        assert commission == pytest.approx(50.0)

    def test_no_stamp_duty(self, rules):
        """测试期货无印花税"""
        _, stamp_duty = rules.compute_cost("buy", 1000000.0)
        assert stamp_duty == 0.0
        _, stamp_duty = rules.compute_cost("sell", 1000000.0)
        assert stamp_duty == 0.0

    def test_lot_size(self, rules):
        """测试期货最小交易单位为 1 手"""
        assert rules.get_lot_size("IF2401") == 1


class TestTradingRulesComparison:
    """对比不同交易规则的差异"""

    def test_t_plus_one_vs_t_plus_zero(self):
        """对比 T+1 和 T+0 的交易限制差异"""
        stock_rules = StockRules()
        futures_rules = FuturesRules()

        date(2024, 1, 15)
        stock_position = Position(
            symbol="000001.SZ",
            shares=1000,
            tradeable_shares=0,  # T+1
            cost_basis=10.0,
            market_value=10000.0,
            last_close=10.0,
        )
        futures_position = Position(
            symbol="IF2401",
            shares=10,
            tradeable_shares=10,  # T+0
            cost_basis=5000.0,
            market_value=50000.0,
            last_close=5000.0,
        )

        # 股票 T+1：当日买入无法卖出
        assert stock_rules.can_trade_today("000001.SZ", stock_position) is False

        # 期货 T+0：当日买入可以卖出
        assert futures_rules.can_trade_today("IF2401", futures_position) is True

    def test_commission_difference(self):
        """对比手续费差异"""
        stock_rules = StockRules()
        futures_rules = FuturesRules()

        value = 100000.0

        stock_comm, stock_stamp = stock_rules.compute_cost("sell", value)
        futures_comm, futures_stamp = futures_rules.compute_cost("sell", value)

        # 股票：佣金 + 印花税
        assert stock_comm == pytest.approx(30.0)
        assert stock_stamp == pytest.approx(100.0)

        # 期货：仅手续费，无印花税
        assert futures_comm == pytest.approx(5.0)
        assert futures_stamp == 0.0
