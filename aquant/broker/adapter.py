from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import TYPE_CHECKING


if TYPE_CHECKING:
    pass


class OrderSide(str, Enum):
    """订单方向。"""

    BUY = "BUY"  # 买入
    SELL = "SELL"  # 卖出


class OrderType(str, Enum):
    """订单类型。"""

    MARKET = "MARKET"  # 市价单
    LIMIT = "LIMIT"  # 限价单


class OrderStatus(str, Enum):
    """订单状态。"""

    PENDING = "PENDING"  # 待提交
    SUBMITTED = "SUBMITTED"  # 已提交
    PARTIAL_FILLED = "PARTIAL_FILLED"  # 部分成交
    FILLED = "FILLED"  # 完全成交
    CANCELLED = "CANCELLED"  # 已撤单
    REJECTED = "REJECTED"  # 已拒绝


@dataclass
class Order:
    """订单数据结构。

    属性：
        order_id: 订单编号（券商返回）
        symbol: 标的代码
        side: 买卖方向
        order_type: 订单类型
        quantity: 委托数量
        price: 委托价格（市价单为 None）
        status: 订单状态
        filled_quantity: 已成交数量
        avg_filled_price: 成交均价
        submit_time: 提交时间
        update_time: 更新时间
    """

    order_id: str
    symbol: str
    side: OrderSide
    order_type: OrderType
    quantity: int
    price: float | None
    status: OrderStatus
    filled_quantity: int = 0
    avg_filled_price: float = 0.0
    submit_time: datetime | None = None
    update_time: datetime | None = None


@dataclass
class Position:
    """持仓数据结构。

    属性：
        symbol: 标的代码
        quantity: 持仓数量
        available_quantity: 可用数量（T+1 限制）
        avg_cost: 持仓均价
        market_value: 当前市值
        unrealized_pnl: 浮动盈亏
    """

    symbol: str
    quantity: int
    available_quantity: int
    avg_cost: float
    market_value: float
    unrealized_pnl: float


class BrokerAdapter(ABC):
    """券商适配器抽象基类。

    继承此类并实现全部方法，即可对接特定券商的交易接口。
    框架通过这个接口执行实盘交易操作。

    使用示例::

        class MyBrokerAdapter(BrokerAdapter):
            def __init__(self, account: str, password: str):
                self._client = SomeBrokerClient(account, password)

            def submit_order(self, symbol, side, quantity, price, order_type):
                # 调用券商 API 下单
                ...

            def cancel_order(self, order_id):
                # 调用券商 API 撤单
                ...

            def get_order(self, order_id):
                # 查询订单状态
                ...

            def get_positions(self):
                # 查询当前持仓
                ...

            def get_cash(self):
                # 查询可用资金
                ...

            def get_total_value(self):
                # 查询总资产
                ...
    """

    @abstractmethod
    def submit_order(
        self,
        symbol: str,
        side: OrderSide,
        quantity: int,
        price: float | None = None,
        order_type: OrderType = OrderType.MARKET,
    ) -> Order:
        """提交订单。

        参数：
            symbol: 标的代码
            side: 买卖方向
            quantity: 委托数量
            price: 委托价格（市价单可为 None）
            order_type: 订单类型

        返回：
            Order 对象，包含订单编号和初始状态
        """

    @abstractmethod
    def cancel_order(self, order_id: str) -> bool:
        """撤销订单。

        参数：
            order_id: 订单编号

        返回：
            是否撤单成功
        """

    @abstractmethod
    def get_order(self, order_id: str) -> Order | None:
        """查询订单状态。

        参数：
            order_id: 订单编号

        返回：
            Order 对象，若订单不存在则返回 None
        """

    @abstractmethod
    def get_positions(self) -> dict[str, Position]:
        """查询当前持仓。

        返回：
            标的代码到 Position 对象的映射
        """

    @abstractmethod
    def get_cash(self) -> float:
        """查询可用资金。

        返回：
            可用现金余额
        """

    @abstractmethod
    def get_total_value(self) -> float:
        """查询总资产。

        返回：
            现金 + 持仓市值
        """
