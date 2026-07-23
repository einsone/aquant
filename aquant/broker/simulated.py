from __future__ import annotations

from datetime import datetime

from aquant.broker.adapter import BrokerAdapter, Order, OrderSide, OrderStatus, OrderType, Position


class SimulatedBroker(BrokerAdapter):
    """模拟券商适配器，用于测试和演示。

    不依赖真实券商，所有操作在内存中模拟。适用于：
    - 开发调试实盘交易代码
    - 演示如何使用 BrokerAdapter 接口
    - 测试策略的实盘交易逻辑

    特点：
        - 订单立即成交（不考虑市场深度）
        - 市价单以指定的模拟价格成交
        - 限价单直接以委托价成交
        - 不模拟滑点、部分成交等真实场景

    使用示例::

        broker = SimulatedBroker(initial_cash=100000.0)

        # 提交订单
        order = broker.submit_order("AAPL", OrderSide.BUY, 100, price=150.0, order_type=OrderType.LIMIT)

        # 查询订单
        order = broker.get_order(order.order_id)

        # 查询持仓
        positions = broker.get_positions()

        # 查询资金
        cash = broker.get_cash()
    """

    def __init__(self, initial_cash: float = 1000000.0):
        """初始化模拟券商。

        参数：
            initial_cash: 初始资金
        """
        self._cash = initial_cash
        self._positions: dict[str, Position] = {}
        self._orders: dict[str, Order] = {}
        self._order_counter = 0

    def submit_order(self, symbol: str, side: OrderSide, quantity: int, price: float | None = None, order_type: OrderType = OrderType.MARKET) -> Order:
        """提交订单（模拟立即成交）。

        参数：
            symbol: 标的代码
            side: 买卖方向
            quantity: 委托数量
            price: 委托价格（市价单必须提供模拟价格）
            order_type: 订单类型

        返回：
            Order 对象
        """
        if order_type == OrderType.MARKET and price is None:
            msg = "市价单必须提供 price 参数作为模拟成交价"
            raise ValueError(msg)

        if price is None:
            msg = "price 不能为 None"
            raise ValueError(msg)

        self._order_counter += 1
        order_id = f"SIM{self._order_counter:06d}"
        now = datetime.now()

        # 创建订单
        order = Order(order_id=order_id, symbol=symbol, side=side, order_type=order_type, quantity=quantity, price=price, status=OrderStatus.SUBMITTED, filled_quantity=0, avg_filled_price=0.0, submit_time=now, update_time=now)

        # 模拟立即成交
        if side == OrderSide.BUY:
            cost = quantity * price
            if cost > self._cash:
                order.status = OrderStatus.REJECTED
                self._orders[order_id] = order
                return order

            self._cash -= cost
            if symbol in self._positions:
                pos = self._positions[symbol]
                new_quantity = pos.quantity + quantity
                new_cost = (pos.avg_cost * pos.quantity + cost) / new_quantity
                self._positions[symbol] = Position(
                    symbol=symbol,
                    quantity=new_quantity,
                    available_quantity=pos.available_quantity,  # T+1 限制
                    avg_cost=new_cost,
                    market_value=new_quantity * price,
                    unrealized_pnl=new_quantity * (price - new_cost),
                )
            else:
                self._positions[symbol] = Position(
                    symbol=symbol,
                    quantity=quantity,
                    available_quantity=0,  # T+1 限制
                    avg_cost=price,
                    market_value=quantity * price,
                    unrealized_pnl=0.0,
                )

        else:  # SELL
            if symbol not in self._positions:
                order.status = OrderStatus.REJECTED
                self._orders[order_id] = order
                return order

            pos = self._positions[symbol]
            if quantity > pos.available_quantity:
                order.status = OrderStatus.REJECTED
                self._orders[order_id] = order
                return order

            self._cash += quantity * price
            new_quantity = pos.quantity - quantity
            if new_quantity == 0:
                del self._positions[symbol]
            else:
                self._positions[symbol] = Position(symbol=symbol, quantity=new_quantity, available_quantity=pos.available_quantity - quantity, avg_cost=pos.avg_cost, market_value=new_quantity * price, unrealized_pnl=new_quantity * (price - pos.avg_cost))

        # 标记为完全成交
        order.status = OrderStatus.FILLED
        order.filled_quantity = quantity
        order.avg_filled_price = price
        order.update_time = datetime.now()

        self._orders[order_id] = order
        return order

    def cancel_order(self, order_id: str) -> bool:
        """撤销订单（模拟总是失败，因为订单立即成交）。

        参数：
            order_id: 订单编号

        返回：
            False（订单已成交无法撤单）
        """
        if order_id not in self._orders:
            return False

        order = self._orders[order_id]
        if order.status == OrderStatus.FILLED:
            return False

        order.status = OrderStatus.CANCELLED
        order.update_time = datetime.now()
        return True

    def get_order(self, order_id: str) -> Order | None:
        """查询订单状态。

        参数：
            order_id: 订单编号

        返回：
            Order 对象，若不存在则返回 None
        """
        return self._orders.get(order_id)

    def get_positions(self) -> dict[str, Position]:
        """查询当前持仓。

        返回：
            标的代码到 Position 对象的映射
        """
        return self._positions.copy()

    def get_cash(self) -> float:
        """查询可用资金。

        返回：
            可用现金余额
        """
        return self._cash

    def get_total_value(self) -> float:
        """查询总资产。

        返回：
            现金 + 持仓市值
        """
        market_value = sum(pos.market_value for pos in self._positions.values())
        return self._cash + market_value

    def update_market_prices(self, prices: dict[str, float]) -> None:
        """更新市场价格，重新计算持仓市值和浮动盈亏。

        此方法用于模拟行情更新。

        参数：
            prices: 标的代码到最新价格的映射
        """
        for symbol, price in prices.items():
            if symbol in self._positions:
                pos = self._positions[symbol]
                new_market_value = pos.quantity * price
                new_unrealized_pnl = pos.quantity * (price - pos.avg_cost)
                self._positions[symbol] = Position(symbol=symbol, quantity=pos.quantity, available_quantity=pos.available_quantity, avg_cost=pos.avg_cost, market_value=new_market_value, unrealized_pnl=new_unrealized_pnl)

    def set_available_quantity(self, symbol: str, available: int) -> None:
        """设置可用数量（用于模拟 T+1 解锁）。

        参数：
            symbol: 标的代码
            available: 可用数量
        """
        if symbol in self._positions:
            pos = self._positions[symbol]
            self._positions[symbol] = Position(symbol=symbol, quantity=pos.quantity, available_quantity=available, avg_cost=pos.avg_cost, market_value=pos.market_value, unrealized_pnl=pos.unrealized_pnl)
