"""测试订单管理器"""

from unittest.mock import Mock

import pytest

from aquant.live.order_manager import Order, OrderManager, OrderStatus


@pytest.fixture
def mock_broker():
    """模拟券商适配器"""
    broker = Mock()

    # 为每次调用返回不同的订单 ID
    order_counter = {"buy": 0, "sell": 0}

    def buy_side_effect(symbol, shares, price=None):
        order_counter["buy"] += 1
        return f"buy_order_{order_counter['buy']}"

    def sell_side_effect(symbol, shares, price=None):
        order_counter["sell"] += 1
        return f"sell_order_{order_counter['sell']}"

    broker.buy.side_effect = buy_side_effect
    broker.sell.side_effect = sell_side_effect
    broker.cancel_order.return_value = True
    broker.get_order_status.return_value = {"status": "filled", "filled_shares": 100, "avg_price": 10.5}
    return broker


def test_order_init():
    """测试订单初始化"""
    order = Order(symbol="000001.SZ", side="buy", shares=100, price=10.0)

    assert order.symbol == "000001.SZ"
    assert order.side == "buy"
    assert order.shares == 100
    assert order.price == 10.0
    assert order.status == OrderStatus.PENDING
    assert order.filled_shares == 0
    assert order.order_id is None


def test_order_repr():
    """测试订单字符串表示"""
    order = Order(symbol="000001.SZ", side="buy", shares=100)
    repr_str = repr(order)

    assert "000001.SZ" in repr_str
    assert "buy" in repr_str
    assert "100" in repr_str


def test_order_manager_init(mock_broker):
    """测试订单管理器初始化"""
    manager = OrderManager(mock_broker)

    assert manager.broker == mock_broker
    assert len(manager.orders) == 0


def test_submit_buy_order(mock_broker):
    """测试提交买单"""
    manager = OrderManager(mock_broker)

    order = manager.submit_order(symbol="000001.SZ", side="buy", shares=100, price=10.0)

    # 验证订单状态
    assert order.order_id == "buy_order_1"
    assert order.status == OrderStatus.SUBMITTED
    assert order.symbol == "000001.SZ"

    # 验证调用券商接口
    mock_broker.buy.assert_called_once_with("000001.SZ", 100, 10.0)

    # 验证订单已保存
    assert "buy_order_1" in manager.orders


def test_submit_sell_order(mock_broker):
    """测试提交卖单"""
    manager = OrderManager(mock_broker)

    order = manager.submit_order(symbol="000001.SZ", side="sell", shares=100, price=10.0)

    assert order.order_id == "sell_order_1"
    assert order.status == OrderStatus.SUBMITTED
    mock_broker.sell.assert_called_once_with("000001.SZ", 100, 10.0)


def test_submit_market_order(mock_broker):
    """测试提交市价单"""
    manager = OrderManager(mock_broker)

    order = manager.submit_order(symbol="000001.SZ", side="buy", shares=100)

    # 价格为 None 表示市价单
    assert order.price is None
    mock_broker.buy.assert_called_once_with("000001.SZ", 100, None)


def test_submit_order_failed(mock_broker):
    """测试订单提交失败"""
    mock_broker.buy.side_effect = Exception("提交失败")

    manager = OrderManager(mock_broker)
    order = manager.submit_order(symbol="000001.SZ", side="buy", shares=100)

    # 订单状态应为失败
    assert order.status == OrderStatus.FAILED
    assert order.order_id is None


def test_check_orders(mock_broker):
    """测试检查订单状态"""
    manager = OrderManager(mock_broker)

    # 提交订单
    order = manager.submit_order(symbol="000001.SZ", side="buy", shares=100)
    order_id = order.order_id

    # 检查状态
    statuses = manager.check_orders()

    # 验证状态已更新
    assert order_id in statuses
    assert statuses[order_id] == OrderStatus.FILLED
    assert order.status == OrderStatus.FILLED
    assert order.filled_shares == 100
    assert order.avg_fill_price == 10.5


def test_check_partial_filled_order(mock_broker):
    """测试部分成交订单"""
    mock_broker.get_order_status.return_value = {"status": "partial_filled", "filled_shares": 50, "avg_price": 10.3}

    manager = OrderManager(mock_broker)
    order = manager.submit_order(symbol="000001.SZ", side="buy", shares=100)

    manager.check_orders()

    assert order.status == OrderStatus.PARTIAL_FILLED
    assert order.filled_shares == 50
    assert order.avg_fill_price == 10.3


def test_check_cancelled_order(mock_broker):
    """测试已撤销订单"""
    mock_broker.get_order_status.return_value = {"status": "cancelled"}

    manager = OrderManager(mock_broker)
    order = manager.submit_order(symbol="000001.SZ", side="buy", shares=100)

    manager.check_orders()

    assert order.status == OrderStatus.CANCELLED


def test_check_rejected_order(mock_broker):
    """测试被拒绝订单"""
    mock_broker.get_order_status.return_value = {"status": "rejected", "reject_reason": "资金不足"}

    manager = OrderManager(mock_broker)
    order = manager.submit_order(symbol="000001.SZ", side="buy", shares=100)

    manager.check_orders()

    assert order.status == OrderStatus.REJECTED


def test_cancel_order(mock_broker):
    """测试撤销订单"""
    manager = OrderManager(mock_broker)
    order = manager.submit_order(symbol="000001.SZ", side="buy", shares=100)

    assert order.order_id is not None
    success = manager.cancel_order(order.order_id)

    assert success
    assert order.status == OrderStatus.CANCELLED
    mock_broker.cancel_order.assert_called_once_with(order.order_id)


def test_cancel_nonexistent_order(mock_broker):
    """测试撤销不存在的订单"""
    manager = OrderManager(mock_broker)

    success = manager.cancel_order("nonexistent_id")

    assert not success


def test_cancel_completed_order(mock_broker):
    """测试撤销已完成的订单"""
    manager = OrderManager(mock_broker)
    order = manager.submit_order(symbol="000001.SZ", side="buy", shares=100)

    # 模拟订单已成交
    order.status = OrderStatus.FILLED

    assert order.order_id is not None
    success = manager.cancel_order(order.order_id)

    assert not success
    # 不应调用券商接口
    mock_broker.cancel_order.assert_not_called()


def test_cancel_all_pending(mock_broker):
    """测试批量撤销"""
    manager = OrderManager(mock_broker)

    # 提交多个订单
    order1 = manager.submit_order(symbol="000001.SZ", side="buy", shares=100)
    order2 = manager.submit_order(symbol="000002.SZ", side="buy", shares=200)
    order3 = manager.submit_order(symbol="000003.SZ", side="buy", shares=300)

    # 模拟一个已成交
    order3.status = OrderStatus.FILLED

    count = manager.cancel_all_pending()

    # 应该撤销 2 个订单
    assert count == 2
    assert order1.status == OrderStatus.CANCELLED
    assert order2.status == OrderStatus.CANCELLED
    assert order3.status == OrderStatus.FILLED


def test_get_order(mock_broker):
    """测试获取订单"""
    manager = OrderManager(mock_broker)
    order = manager.submit_order(symbol="000001.SZ", side="buy", shares=100)

    assert order.order_id is not None
    retrieved = manager.get_order(order.order_id)

    assert retrieved == order


def test_get_nonexistent_order(mock_broker):
    """测试获取不存在的订单"""
    manager = OrderManager(mock_broker)

    retrieved = manager.get_order("nonexistent_id")

    assert retrieved is None


def test_get_pending_orders(mock_broker):
    """测试获取未完成订单"""
    manager = OrderManager(mock_broker)

    # 提交多个订单
    order1 = manager.submit_order(symbol="000001.SZ", side="buy", shares=100)
    order2 = manager.submit_order(symbol="000002.SZ", side="buy", shares=200)

    # 模拟一个已成交
    order2.status = OrderStatus.FILLED

    pending = manager.get_pending_orders()

    assert len(pending) == 1
    assert pending[0] == order1


def test_get_filled_orders(mock_broker):
    """测试获取已成交订单"""
    manager = OrderManager(mock_broker)

    order1 = manager.submit_order(symbol="000001.SZ", side="buy", shares=100)
    manager.submit_order(symbol="000002.SZ", side="buy", shares=200)

    # 模拟一个已成交
    order1.status = OrderStatus.FILLED

    filled = manager.get_filled_orders()

    assert len(filled) == 1
    assert filled[0] == order1


def test_summary(mock_broker):
    """测试订单统计摘要"""
    manager = OrderManager(mock_broker)

    # 提交不同状态的订单
    order1 = manager.submit_order(symbol="000001.SZ", side="buy", shares=100)
    order2 = manager.submit_order(symbol="000002.SZ", side="buy", shares=200)
    order3 = manager.submit_order(symbol="000003.SZ", side="buy", shares=300)

    # 设置不同状态
    order1.status = OrderStatus.FILLED
    order2.status = OrderStatus.SUBMITTED
    order3.status = OrderStatus.CANCELLED

    summary = manager.summary()

    assert summary["total"] == 3
    assert summary["filled"] == 1
    assert summary["pending"] == 1
    assert summary["cancelled"] == 1
    assert summary["fill_rate"] == 1 / 3


def test_summary_empty(mock_broker):
    """测试空订单管理器的摘要"""
    manager = OrderManager(mock_broker)

    summary = manager.summary()

    assert summary["total"] == 0
    assert summary["fill_rate"] == 0.0
