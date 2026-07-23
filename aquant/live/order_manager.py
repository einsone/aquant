"""订单管理器

管理实盘交易中的订单生命周期。
"""

import time
from enum import StrEnum
from typing import Any

import structlog

from aquant.broker.adapter import BrokerAdapter


logger = structlog.get_logger()


class OrderStatus(StrEnum):
    """订单状态"""

    PENDING = "pending"  # 待提交
    SUBMITTED = "submitted"  # 已提交
    PARTIAL_FILLED = "partial_filled"  # 部分成交
    FILLED = "filled"  # 完全成交
    CANCELLED = "cancelled"  # 已撤销
    REJECTED = "rejected"  # 被拒绝
    FAILED = "failed"  # 失败


class Order:
    """订单"""

    def __init__(self, symbol: str, side: str, shares: int, price: float | None = None, order_id: str | None = None):
        self.symbol = symbol
        self.side = side
        self.shares = shares
        self.price = price
        self.order_id = order_id
        self.status = OrderStatus.PENDING
        self.filled_shares = 0
        self.avg_fill_price = 0.0
        self.create_time = time.time()
        self.update_time = time.time()

    def __repr__(self) -> str:
        return f"Order(symbol={self.symbol}, side={self.side}, shares={self.shares}, status={self.status.value})"


class OrderManager:
    """订单管理器"""

    def __init__(self, broker: BrokerAdapter):
        self.broker = broker
        self.orders: dict[str, Order] = {}

    def submit_order(self, symbol: str, side: str, shares: int, price: float | None = None) -> Order:
        """提交订单

        Args:
            symbol: 股票代码
            side: 方向（buy/sell）
            shares: 股数
            price: 限价（None 表示市价）

        Returns:
            订单对象
        """
        order = Order(symbol=symbol, side=side, shares=shares, price=price)

        try:
            # 提交到券商
            order_id = self.broker.buy(symbol, shares, price) if side == "buy" else self.broker.sell(symbol, shares, price)

            order.order_id = order_id
            order.status = OrderStatus.SUBMITTED
            order.update_time = time.time()

            # 保存订单
            self.orders[order_id] = order

            logger.info("订单已提交", order_id=order_id, symbol=symbol, side=side, shares=shares, price=price)

        except Exception as e:
            order.status = OrderStatus.FAILED
            logger.error("订单提交失败", symbol=symbol, error=str(e))

        return order

    def check_orders(self) -> dict[str, OrderStatus]:
        """检查所有订单状态

        Returns:
            订单 ID -> 状态的字典
        """
        statuses = {}

        for order_id, order in list(self.orders.items()):
            if order.status in [OrderStatus.FILLED, OrderStatus.CANCELLED, OrderStatus.REJECTED, OrderStatus.FAILED]:
                # 已完成的订单不再检查
                continue

            try:
                # 查询券商订单状态
                broker_status = self.broker.get_order_status(order_id)

                # 更新订单状态
                self._update_order_from_broker(order, broker_status)

                statuses[order_id] = order.status

            except Exception as e:
                logger.error("查询订单状态失败", order_id=order_id, error=str(e))

        return statuses

    def cancel_order(self, order_id: str) -> bool:
        """撤销订单

        Args:
            order_id: 订单 ID

        Returns:
            是否成功
        """
        if order_id not in self.orders:
            logger.warning("订单不存在", order_id=order_id)
            return False

        order = self.orders[order_id]

        if order.status in [OrderStatus.FILLED, OrderStatus.CANCELLED, OrderStatus.REJECTED]:
            logger.warning("订单无法撤销", order_id=order_id, status=order.status.value)
            return False

        try:
            success = self.broker.cancel_order(order_id)

            if success:
                order.status = OrderStatus.CANCELLED
                order.update_time = time.time()
                logger.info("订单已撤销", order_id=order_id)
            else:
                logger.warning("订单撤销失败", order_id=order_id)

            return success

        except Exception as e:
            logger.error("订单撤销异常", order_id=order_id, error=str(e))
            return False

    def cancel_all_pending(self) -> int:
        """撤销所有未成交订单

        Returns:
            撤销的订单数量
        """
        count = 0

        for order_id, order in list(self.orders.items()):
            if order.status in [OrderStatus.SUBMITTED, OrderStatus.PARTIAL_FILLED] and self.cancel_order(order_id):
                count += 1

        logger.info("批量撤销订单完成", count=count)
        return count

    def get_order(self, order_id: str) -> Order | None:
        """获取订单

        Args:
            order_id: 订单 ID

        Returns:
            订单对象，不存在则返回 None
        """
        return self.orders.get(order_id)

    def get_pending_orders(self) -> list[Order]:
        """获取所有未完成订单

        Returns:
            未完成订单列表
        """
        return [order for order in self.orders.values() if order.status in [OrderStatus.PENDING, OrderStatus.SUBMITTED, OrderStatus.PARTIAL_FILLED]]

    def get_filled_orders(self) -> list[Order]:
        """获取所有已成交订单

        Returns:
            已成交订单列表
        """
        return [order for order in self.orders.values() if order.status == OrderStatus.FILLED]

    def _update_order_from_broker(self, order: Order, broker_status: dict[str, Any]):
        """根据券商返回的状态更新订单

        Args:
            order: 订单对象
            broker_status: 券商返回的状态字典
        """
        status = broker_status.get("status", "")

        if status == "filled":
            order.status = OrderStatus.FILLED
            order.filled_shares = order.shares
            order.avg_fill_price = broker_status.get("avg_price", 0.0)
            logger.info("订单已成交", order_id=order.order_id, symbol=order.symbol, shares=order.shares, avg_price=order.avg_fill_price)

        elif status == "partial_filled":
            order.status = OrderStatus.PARTIAL_FILLED
            order.filled_shares = broker_status.get("filled_shares", 0)
            order.avg_fill_price = broker_status.get("avg_price", 0.0)
            logger.info("订单部分成交", order_id=order.order_id, symbol=order.symbol, filled=order.filled_shares, total=order.shares)

        elif status == "cancelled":
            order.status = OrderStatus.CANCELLED
            logger.info("订单已撤销", order_id=order.order_id)

        elif status == "rejected":
            order.status = OrderStatus.REJECTED
            logger.warning("订单被拒绝", order_id=order.order_id, reason=broker_status.get("reject_reason", ""))

        order.update_time = time.time()

    def summary(self) -> dict[str, Any]:
        """获取订单统计摘要

        Returns:
            统计摘要字典
        """
        total = len(self.orders)
        filled = sum(1 for o in self.orders.values() if o.status == OrderStatus.FILLED)
        pending = sum(1 for o in self.orders.values() if o.status in [OrderStatus.SUBMITTED, OrderStatus.PARTIAL_FILLED])
        cancelled = sum(1 for o in self.orders.values() if o.status == OrderStatus.CANCELLED)
        rejected = sum(1 for o in self.orders.values() if o.status == OrderStatus.REJECTED)

        return {"total": total, "filled": filled, "pending": pending, "cancelled": cancelled, "rejected": rejected, "fill_rate": filled / total if total > 0 else 0.0}
