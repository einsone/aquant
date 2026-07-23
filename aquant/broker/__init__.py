"""实盘交易接口模块。

提供券商适配器抽象层，支持将策略从回测切换到实盘交易。
"""

from aquant.broker.adapter import BrokerAdapter, Order, OrderSide, OrderStatus, OrderType, Position

__all__ = [
    "BrokerAdapter",
    "Order",
    "OrderSide",
    "OrderStatus",
    "OrderType",
    "Position",
]
