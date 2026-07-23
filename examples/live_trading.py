"""实盘交易示例：展示如何将策略从回测切换到实盘模式。

本示例演示：
1. 使用模拟券商进行纸上交易
2. 策略信号生成与订单执行的分离
3. 实盘交易的基本流程

运行：
    uv run python examples/live_trading.py

注意：
    本示例仅展示 BrokerAdapter 接口的使用方法。
    实际使用时需要结合策略引擎和数据源。
"""

from __future__ import annotations

from aquant.broker.adapter import OrderSide, OrderType
from aquant.broker.simulated import SimulatedBroker


def main():
    """实盘交易主函数。"""
    print("=" * 60)
    print("实盘交易示例（使用模拟券商）")
    print("=" * 60)
    print()

    # 1. 初始化模拟券商
    broker = SimulatedBroker(initial_cash=100000.0)
    print(f"初始资金: {broker.get_cash():,.2f} 元")
    print()
    # 2. 模拟实盘交易流程
    print("=" * 60)
    print("模拟交易流程")
    print("=" * 60)
    print()

    # 场景 1: 买入
    print("场景 1: 买入 AAPL")
    print("-" * 60)

    current_price = 150.0
    target_value = broker.get_total_value() * 0.3
    quantity = int(target_value / current_price)

    order = broker.submit_order(
        symbol="AAPL",
        side=OrderSide.BUY,
        quantity=quantity,
        price=current_price,
        order_type=OrderType.LIMIT,
    )

    print(f"提交订单: {order.order_id}")
    print(f"  标的: {order.symbol}")
    print(f"  方向: {order.side.value}")
    print(f"  数量: {order.quantity}")
    print(f"  价格: {order.price:.2f}")
    print(f"  状态: {order.status.value}")
    print()

    # 查询持仓
    positions = broker.get_positions()
    if "AAPL" in positions:
        pos = positions["AAPL"]
        print(f"持仓信息:")
        print(f"  标的: {pos.symbol}")
        print(f"  数量: {pos.quantity}")
        print(f"  可用: {pos.available_quantity}")
        print(f"  成本: {pos.avg_cost:.2f}")
        print(f"  市值: {pos.market_value:,.2f}")
        print(f"  浮盈: {pos.unrealized_pnl:,.2f}")
    print()

    print(f"可用资金: {broker.get_cash():,.2f} 元")
    print(f"总资产: {broker.get_total_value():,.2f} 元")
    print()

    # 场景 2: 模拟价格变动
    print("场景 2: 价格变动")
    print("-" * 60)

    # 解锁 T+1 限制
    broker.set_available_quantity("AAPL", quantity)

    # 更新价格
    new_price = 155.0
    broker.update_market_prices({"AAPL": new_price})

    positions = broker.get_positions()
    if "AAPL" in positions:
        pos = positions["AAPL"]
        print(f"价格上涨: {current_price:.2f} -> {new_price:.2f}")
        print(f"  市值: {pos.market_value:,.2f}")
        print(f"  浮盈: {pos.unrealized_pnl:,.2f}")
    print()

    print(f"总资产: {broker.get_total_value():,.2f} 元")
    print()

    # 场景 3: 卖出
    print("场景 3: 卖出 AAPL")
    print("-" * 60)

    order = broker.submit_order(
        symbol="AAPL",
        side=OrderSide.SELL,
        quantity=quantity,
        price=new_price,
        order_type=OrderType.LIMIT,
    )

    print(f"提交订单: {order.order_id}")
    print(f"  标的: {order.symbol}")
    print(f"  方向: {order.side.value}")
    print(f"  数量: {order.quantity}")
    print(f"  价格: {order.price:.2f}")
    print(f"  状态: {order.status.value}")
    print()

    positions = broker.get_positions()
    print(f"持仓数量: {len(positions)}")
    print(f"可用资金: {broker.get_cash():,.2f} 元")
    print(f"总资产: {broker.get_total_value():,.2f} 元")
    print()

    # 4. 总结
    print("=" * 60)
    print("实盘交易要点")
    print("=" * 60)
    print()
    print("1. 订单管理")
    print("   - 使用 broker.submit_order() 提交订单")
    print("   - 使用 broker.get_order() 查询订单状态")
    print("   - 使用 broker.cancel_order() 撤销订单")
    print()
    print("2. 持仓查询")
    print("   - 使用 broker.get_positions() 获取当前持仓")
    print("   - 注意 T+1 限制（available_quantity）")
    print()
    print("3. 资金管理")
    print("   - 使用 broker.get_cash() 查询可用资金")
    print("   - 使用 broker.get_total_value() 查询总资产")
    print()
    print("4. 对接真实券商")
    print("   - 继承 BrokerAdapter 实现具体券商接口")
    print("   - 实现 submit_order/cancel_order 等方法")
    print("   - 参考 aquant/broker/adapter.py 文档")
    print()
    print("示例运行完成！")


if __name__ == "__main__":
    main()
