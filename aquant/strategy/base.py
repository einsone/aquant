from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING


if TYPE_CHECKING:
    from aquant.core.context import Context
    from aquant.events.bus import MessageBus
    from aquant.strategy.signal import Signal


class Strategy(ABC):
    """策略基类。

    子类必须实现 ``on_bar``，其余钩子均有默认空实现，按需覆盖即可。

    类属性：
        warmup_period: 预热期长度（交易日数）。预热期内 ``on_bar`` 正常调用，
            但返回的信号全部丢弃，不产生任何委托。默认为 0（不预热）。
        rebalance_mode: 调仓模式。
            ``"replace"``：每次 ``on_bar`` 的返回值视为完整目标持仓，
                未出现在信号中的现有持仓自动以 weight=0 清仓。适合选股策略：
                策略只需关心"今天选谁"，不再看好的票无需显式发出卖出信号。默认值。
            ``"incremental"``：只对信号中出现的标的调仓，未出现的持仓保持不动。
                适合需要长期持仓、偶尔调整的策略。
    """

    warmup_period: int = 0
    rebalance_mode: str = "replace"

    def on_start(self, context: Context) -> None:  # noqa: B027
        """回测开始前调用一次。

        适合在此处建立数据库连接、加载静态数据或初始化跨 bar 的状态。

        ``context.current_date`` 等于回测区间内第一个实际交易日。

        使用多进程参数优化（``n_jobs != 1``）时，每个 worker 进程都会
        独立调用此方法。因此数据库连接应在此处创建，而不是在 ``__init__``
        中，以避免 DuckDB 等单写者数据库的跨进程文件锁冲突。
        """

    def setup_subscriptions(self, bus: MessageBus) -> None:  # noqa: B027
        """可选钩子：策略可订阅事件。

        在 Engine.__init__() 后、run() 前调用。策略可通过消息总线订阅
        订单成交、持仓变动、组合估值等事件，实现事件驱动的交易逻辑。

        使用示例::

            def setup_subscriptions(self, bus: MessageBus) -> None:
                bus.subscribe("order.filled", self._on_order_filled)
                bus.subscribe("portfolio.valuation", self._on_valuation)


            def _on_order_filled(self, event: OrderFilledEvent) -> None:
                logger.info("订单成交", symbol=event.symbol, price=event.fill_price)
        """

    @abstractmethod
    def on_bar(self, context: Context) -> list[Signal]:
        """每个交易日结束后调用，唯一必须实现的方法。

        策略可访问 T 日完整行情（含收盘价），产生的信号于 T+1 开盘时成交。
        最后一个交易日的信号无对应 T+1，直接丢弃。
        在此处查询数据、计算信号，并返回目标权重列表。

        使用规则：
        - 只能查询 ``date <= context.current_date`` 的数据。
          框架不拦截未来数据，防止前视偏差由策略自行负责。
        - ``weight`` 相对于组合总净值的比例，``weight=0.1``
          表示目标持仓占组合 10%。
        - 各信号的权重无需相加为 1，框架对每个信号独立计算目标股数。
          权重之和超过 1.0 时，后排买入信号可能因现金不足被截断。

        返回值语义取决于 ``rebalance_mode``：
        - ``"replace"`` 模式：返回值视为完整目标持仓。
          未出现在返回列表中的现有持仓会被自动清仓。
          返回 ``[]`` 等同于"本日不操作"，持仓保持不变。
          要主动清仓，需显式返回 ``Signal(symbol=s, weight=0)``。
        - ``"incremental"`` 模式：只对返回列表中出现的标的调仓。
          返回 ``[]`` 维持现状，不触发任何交易。
          显式返回 ``Signal(symbol=s, weight=0)`` 可清仓指定标的。

        预热期内此方法仍会被调用（便于初始化指标），但返回值被丢弃。
        """
        ...

    def on_end(self, context: Context) -> None:  # noqa: B027
        """回测结束后调用一次。

        适合在此处关闭数据库连接、文件句柄，或输出最终汇总信息。
        ``context.current_date`` 等于回测区间内最后一个实际交易日。
        """
