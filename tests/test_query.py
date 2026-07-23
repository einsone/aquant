"""Query Service 单元测试"""

from datetime import date, timedelta

import pytest

from aquant.portfolio.portfolio import Trade
from aquant.portfolio.position import NavRecord
from aquant.portfolio.query import PortfolioQueryService


class TestPortfolioQueryService:
    """测试 PortfolioQueryService 的各项查询功能"""

    @pytest.fixture
    def sample_nav_records(self):
        """创建示例净值记录"""
        base_date = date(2024, 1, 1)
        records = []
        for i in range(10):
            records.append(
                NavRecord(
                    date=base_date + timedelta(days=i),
                    total=1000000 + i * 10000,  # 每日增长 10000
                    cash=500000 - i * 5000,
                    position_count=5 + i % 3,
                )
            )
        return records

    @pytest.fixture
    def sample_trades(self):
        """创建示例成交记录"""
        base_date = date(2024, 1, 1)
        trades = [
            Trade(date=base_date, symbol="000001.SZ", side="buy", shares=1000, price=10.0, commission=30.0, stamp_duty=0.0, pnl=0.0),
            Trade(
                date=base_date + timedelta(days=1),
                symbol="000001.SZ",
                side="sell",
                shares=1000,
                price=11.0,
                commission=33.0,
                stamp_duty=11.0,
                pnl=956.0,  # 盈利
            ),
            Trade(date=base_date + timedelta(days=2), symbol="600000.SH", side="buy", shares=500, price=20.0, commission=30.0, stamp_duty=0.0, pnl=0.0),
            Trade(
                date=base_date + timedelta(days=3),
                symbol="600000.SH",
                side="sell",
                shares=500,
                price=19.0,
                commission=28.5,
                stamp_duty=9.5,
                pnl=-538.0,  # 亏损
            ),
        ]
        return trades

    @pytest.fixture
    def query_service(self, sample_nav_records, sample_trades):
        """创建 QueryService 实例"""
        return PortfolioQueryService(daily_nav=sample_nav_records, trade_log=sample_trades)

    def test_get_nav_curve_all(self, query_service):
        """测试查询全部净值曲线"""
        df = query_service.get_nav_curve()
        assert len(df) == 10
        assert list(df.columns) == ["date", "nav", "cash", "position_count"]
        assert df["nav"][0] == 1000000
        assert df["nav"][-1] == 1090000

    def test_get_nav_curve_with_range(self, query_service):
        """测试查询指定日期区间的净值曲线"""
        start = date(2024, 1, 3)
        end = date(2024, 1, 6)
        df = query_service.get_nav_curve(start=start, end=end)
        assert len(df) == 4
        assert df["date"][0] == start
        assert df["date"][-1] == end

    def test_get_nav_curve_empty(self):
        """测试空净值记录"""
        service = PortfolioQueryService(daily_nav=[], trade_log=[])
        df = service.get_nav_curve()
        assert len(df) == 0

    def test_get_recent_trades_all_symbols(self, query_service):
        """测试查询最近成交（所有标的）"""
        trades = query_service.get_recent_trades(n=10)
        assert len(trades) == 4
        # 按日期倒序
        assert trades[0].date == date(2024, 1, 4)
        assert trades[-1].date == date(2024, 1, 1)

    def test_get_recent_trades_specific_symbol(self, query_service):
        """测试查询指定标的的最近成交"""
        trades = query_service.get_recent_trades(symbol="000001.SZ", n=10)
        assert len(trades) == 2
        assert all(t.symbol == "000001.SZ" for t in trades)

    def test_get_recent_trades_limit(self, query_service):
        """测试查询数量限制"""
        trades = query_service.get_recent_trades(n=2)
        assert len(trades) == 2

    def test_get_trades_by_date_range(self, query_service):
        """测试查询指定日期区间的成交"""
        start = date(2024, 1, 2)
        end = date(2024, 1, 3)
        trades = query_service.get_trades_by_date_range(start, end)
        assert len(trades) == 2
        # 按日期升序
        assert trades[0].date == date(2024, 1, 2)
        assert trades[1].date == date(2024, 1, 3)

    def test_get_trades_by_date_range_with_symbol(self, query_service):
        """测试查询指定标的和日期区间的成交"""
        start = date(2024, 1, 1)
        end = date(2024, 1, 10)
        trades = query_service.get_trades_by_date_range(start, end, symbol="000001.SZ")
        assert len(trades) == 2
        assert all(t.symbol == "000001.SZ" for t in trades)

    def test_get_peak_nav(self, query_service):
        """测试获取历史最高净值"""
        peak = query_service.get_peak_nav()
        assert peak == 1090000  # 最后一天的净值

    def test_get_peak_nav_empty(self):
        """测试空记录的最高净值"""
        service = PortfolioQueryService(daily_nav=[], trade_log=[])
        assert service.get_peak_nav() == 0.0

    def test_get_current_drawdown(self, query_service):
        """测试获取当前回撤"""
        dd = query_service.get_current_drawdown()
        # 最高净值 1090000，当前净值也是 1090000
        assert dd == 0.0

    def test_get_current_drawdown_with_loss(self):
        """测试有回撤的情况"""
        records = [
            NavRecord(date=date(2024, 1, 1), total=1000000, cash=500000, position_count=5),
            NavRecord(date=date(2024, 1, 2), total=1100000, cash=500000, position_count=5),  # 峰值
            NavRecord(date=date(2024, 1, 3), total=1000000, cash=500000, position_count=5),  # 回撤
        ]
        service = PortfolioQueryService(daily_nav=records, trade_log=[])
        dd = service.get_current_drawdown()
        assert dd == pytest.approx((1100000 - 1000000) / 1100000)  # 约 9.09%

    def test_get_win_rate(self, query_service):
        """测试计算胜率"""
        win_rate = query_service.get_win_rate()
        # 2 笔卖出：1 盈利，1 亏损
        assert win_rate == 0.5

    def test_get_win_rate_specific_symbol(self, query_service):
        """测试计算指定标的的胜率"""
        win_rate = query_service.get_win_rate(symbol="000001.SZ")
        # 000001.SZ 只有 1 笔卖出，盈利
        assert win_rate == 1.0

    def test_get_win_rate_no_trades(self):
        """测试无交易记录的胜率"""
        service = PortfolioQueryService(daily_nav=[], trade_log=[])
        assert service.get_win_rate() == 0.0

    def test_get_total_pnl(self, query_service):
        """测试计算累计盈亏"""
        pnl = query_service.get_total_pnl()
        # 956 - 538 = 418
        assert pnl == pytest.approx(418.0)

    def test_get_total_pnl_specific_symbol(self, query_service):
        """测试计算指定标的的累计盈亏"""
        pnl = query_service.get_total_pnl(symbol="600000.SH")
        assert pnl == pytest.approx(-538.0)

    def test_get_total_pnl_no_trades(self):
        """测试无交易记录的盈亏"""
        service = PortfolioQueryService(daily_nav=[], trade_log=[])
        assert service.get_total_pnl() == 0.0
