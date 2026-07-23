# 实盘交易

实盘交易接口抽象层。

## BrokerAdapter

::: aquant.broker.adapter.BrokerAdapter
    options:
      show_root_heading: true
      show_source: true
      members:
        - submit_order
        - cancel_order
        - get_order
        - get_positions
        - get_cash
        - get_total_value
        - update_market_prices

## SimulatedBroker

::: aquant.broker.simulated.SimulatedBroker
    options:
      show_root_heading: true
      show_source: true

## Order

::: aquant.broker.adapter.Order
    options:
      show_root_heading: true
      show_source: true

## Position

::: aquant.broker.adapter.Position
    options:
      show_root_heading: true
      show_source: true

## OrderSide

::: aquant.broker.adapter.OrderSide
    options:
      show_root_heading: true
      show_source: true

## OrderType

::: aquant.broker.adapter.OrderType
    options:
      show_root_heading: true
      show_source: true

## OrderStatus

::: aquant.broker.adapter.OrderStatus
    options:
      show_root_heading: true
      show_source: true

## 自定义券商适配器示例

```python
from aquant.broker.adapter import BrokerAdapter, Order, OrderSide, OrderType

class MyBrokerAdapter(BrokerAdapter):
    """自定义券商适配器"""
    
    def submit_order(self, symbol: str, side: OrderSide, quantity: int, 
                     price: float | None, order_type: OrderType) -> Order:
        """提交订单"""
        # 调用真实券商 API
        order_id = broker_api.submit(...)
        
        return Order(
            order_id=order_id,
            symbol=symbol,
            side=side,
            quantity=quantity,
            price=price,
            order_type=order_type,
            status=OrderStatus.PENDING,
            filled_quantity=0,
            avg_filled_price=0.0,
            timestamp=datetime.now(),
        )
    
    def get_positions(self) -> dict[str, Position]:
        """查询持仓"""
        # 调用真实券商 API
        positions = broker_api.get_positions()
        return positions
    
    # 实现其他抽象方法...
```

参考 [examples/live_trading.py](https://github.com/yourusername/aquant/blob/main/examples/live_trading.py) 获取完整示例。
