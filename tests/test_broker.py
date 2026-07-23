"""测试 broker 模块。

测试 SimulatedBroker 的各种场景：
- 买入订单
- 卖出订单
- 资金不足拒单
- 持仓不足拒单
- 订单状态流转
- T+1 限制
- 价格更新
"""

from __future__ import annotations

import pytest

from aquant.broker.adapter import OrderSide, OrderStatus, OrderType
from aquant.broker.simulated import SimulatedBroker


class TestSimulatedBroker:
    """测试模拟券商。"""

    def test_initial_state(self):
        """测试初始状态。"""
        broker = SimulatedBroker(initial_cash=100000.0)

        assert broker.get_cash() == 100000.0
        assert broker.get_total_value() == 100000.0
        assert len(broker.get_positions()) == 0

    def test_buy_order_success(self):
        """测试买入成功。"""
        broker = SimulatedBroker(initial_cash=100000.0)

        order = broker.submit_order(
            symbol="AAPL",
            side=OrderSide.BUY,
            quantity=100,
            price=150.0,
            order_type=OrderType.LIMIT,
        )

        # 验证订单状态
        assert order.status == OrderStatus.FILLED
        assert order.filled_quantity == 100
        assert order.avg_filled_price == 150.0

        # 验证持仓
        positions = broker.get_positions()
        assert "AAPL" in positions
        pos = positions["AAPL"]
        assert pos.quantity == 100
        assert pos.available_quantity == 0  # T+1 限制
        assert pos.avg_cost == 150.0
        assert pos.market_value == 15000.0

        # 验证资金
        assert broker.get_cash() == 85000.0
        assert broker.get_total_value() == 100000.0

    def test_buy_order_insufficient_cash(self):
        """测试资金不足拒单。"""
        broker = SimulatedBroker(initial_cash=10000.0)

        order = broker.submit_order(
            symbol="AAPL",
            side=OrderSide.BUY,
            quantity=100,
            price=150.0,
            order_type=OrderType.LIMIT,
        )

        # 验证订单被拒绝
        assert order.status == OrderStatus.REJECTED
        assert order.filled_quantity == 0

        # 验证持仓和资金未变化
        assert len(broker.get_positions()) == 0
        assert broker.get_cash() == 10000.0

    def test_sell_order_success(self):
        """测试卖出成功。"""
        broker = SimulatedBroker(initial_cash=100000.0)

        # 先买入
        broker.submit_order("AAPL", OrderSide.BUY, 100, 150.0, OrderType.LIMIT)
        broker.set_available_quantity("AAPL", 100)  # 解锁 T+1

        # 再卖出
        order = broker.submit_order("AAPL", OrderSide.SELL, 100, 155.0, OrderType.LIMIT)

        # 验证订单状态
        assert order.status == OrderStatus.FILLED
        assert order.filled_quantity == 100
        assert order.avg_filled_price == 155.0

        # 验证持仓清空
        assert len(broker.get_positions()) == 0

        # 验证资金
        assert broker.get_cash() == 100500.0  # 85000 + 15500
        assert broker.get_total_value() == 100500.0

    def test_sell_order_no_position(self):
        """测试无持仓拒单。"""
        broker = SimulatedBroker(initial_cash=100000.0)

        order = broker.submit_order("AAPL", OrderSide.SELL, 100, 150.0, OrderType.LIMIT)

        # 验证订单被拒绝
        assert order.status == OrderStatus.REJECTED
        assert order.filled_quantity == 0

    def test_sell_order_insufficient_available(self):
        """测试 T+1 限制拒单。"""
        broker = SimulatedBroker(initial_cash=100000.0)

        # 买入但不解锁
        broker.submit_order("AAPL", OrderSide.BUY, 100, 150.0, OrderType.LIMIT)

        # 尝试卖出（可用数量为 0）
        order = broker.submit_order("AAPL", OrderSide.SELL, 100, 155.0, OrderType.LIMIT)

        # 验证订单被拒绝
        assert order.status == OrderStatus.REJECTED

        # 持仓仍在
        positions = broker.get_positions()
        assert "AAPL" in positions
        assert positions["AAPL"].quantity == 100

    def test_multiple_buys_avg_cost(self):
        """测试多次买入计算均价。"""
        broker = SimulatedBroker(initial_cash=100000.0)

        # 第一次买入
        broker.submit_order("AAPL", OrderSide.BUY, 100, 150.0, OrderType.LIMIT)

        # 第二次买入
        broker.submit_order("AAPL", OrderSide.BUY, 100, 160.0, OrderType.LIMIT)

        # 验证持仓
        positions = broker.get_positions()
        pos = positions["AAPL"]
        assert pos.quantity == 200
        assert pos.avg_cost == 155.0  # (100*150 + 100*160) / 200

    def test_partial_sell(self):
        """测试部分卖出。"""
        broker = SimulatedBroker(initial_cash=100000.0)

        # 买入
        broker.submit_order("AAPL", OrderSide.BUY, 100, 150.0, OrderType.LIMIT)
        broker.set_available_quantity("AAPL", 100)

        # 卖出一半
        broker.submit_order("AAPL", OrderSide.SELL, 50, 155.0, OrderType.LIMIT)

        # 验证持仓
        positions = broker.get_positions()
        pos = positions["AAPL"]
        assert pos.quantity == 50
        assert pos.available_quantity == 50
        assert pos.avg_cost == 150.0  # 成本不变

    def test_update_market_prices(self):
        """测试价格更新。"""
        broker = SimulatedBroker(initial_cash=100000.0)

        # 买入
        broker.submit_order("AAPL", OrderSide.BUY, 100, 150.0, OrderType.LIMIT)

        # 更新价格
        broker.update_market_prices({"AAPL": 160.0})

        # 验证持仓
        positions = broker.get_positions()
        pos = positions["AAPL"]
        assert pos.market_value == 16000.0
        assert pos.unrealized_pnl == 1000.0  # (160-150) * 100

        # 验证总资产
        assert broker.get_total_value() == 101000.0

    def test_get_order(self):
        """测试查询订单。"""
        broker = SimulatedBroker(initial_cash=100000.0)

        order = broker.submit_order("AAPL", OrderSide.BUY, 100, 150.0, OrderType.LIMIT)
        order_id = order.order_id

        # 查询订单
        queried_order = broker.get_order(order_id)
        assert queried_order is not None
        assert queried_order.order_id == order_id
        assert queried_order.symbol == "AAPL"
        assert queried_order.status == OrderStatus.FILLED

        # 查询不存在的订单
        assert broker.get_order("INVALID") is None

    def test_cancel_filled_order(self):
        """测试撤销已成交订单。"""
        broker = SimulatedBroker(initial_cash=100000.0)

        order = broker.submit_order("AAPL", OrderSide.BUY, 100, 150.0, OrderType.LIMIT)

        # 尝试撤单（已成交）
        result = broker.cancel_order(order.order_id)

        # 撤单失败
        assert result is False

    def test_market_order_requires_price(self):
        """测试市价单必须提供价格。"""
        broker = SimulatedBroker(initial_cash=100000.0)

        with pytest.raises(ValueError, match="市价单必须提供 price 参数"):
            broker.submit_order("AAPL", OrderSide.BUY, 100, None, OrderType.MARKET)

    def test_order_id_increment(self):
        """测试订单编号递增。"""
        broker = SimulatedBroker(initial_cash=100000.0)

        order1 = broker.submit_order("AAPL", OrderSide.BUY, 100, 150.0, OrderType.LIMIT)
        order2 = broker.submit_order("GOOGL", OrderSide.BUY, 50, 2800.0, OrderType.LIMIT)

        assert order1.order_id == "SIM000001"
        assert order2.order_id == "SIM000002"

    def test_multiple_symbols(self):
        """测试多标的持仓。"""
        broker = SimulatedBroker(initial_cash=200000.0)

        # 买入多个标的
        broker.submit_order("AAPL", OrderSide.BUY, 100, 150.0, OrderType.LIMIT)
        broker.submit_order("GOOGL", OrderSide.BUY, 50, 2800.0, OrderType.LIMIT)

        # 验证持仓
        positions = broker.get_positions()
        assert len(positions) == 2
        assert "AAPL" in positions
        assert "GOOGL" in positions

        # 验证资金
        assert broker.get_cash() == 45000.0  # 200000 - 15000 - 140000
        assert broker.get_total_value() == 200000.0
