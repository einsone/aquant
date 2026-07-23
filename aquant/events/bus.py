"""消息总线模块，实现发布-订阅模式。

借鉴 NautilusTrader 的消息总线设计，所有组件通过总线通信，实现松耦合。
"""

from __future__ import annotations

from collections import defaultdict
from typing import TYPE_CHECKING


if TYPE_CHECKING:
    from collections.abc import Callable

    from aquant.events.event import Event


class MessageBus:
    """轻量级消息总线，实现发布-订阅模式。

    所有组件通过总线通信，避免直接方法调用的紧耦合。
    支持通配符订阅（例如 "order.*" 匹配所有订单事件）。

    使用示例::

        bus = MessageBus()

        # 订阅特定主题
        bus.subscribe("order.filled", lambda e: print(f"订单成交: {e.symbol}"))

        # 订阅通配符主题
        bus.subscribe("order.*", lambda e: print(f"订单事件: {e}"))

        # 发布事件
        bus.publish("order.filled", OrderFilledEvent(...))
    """

    def __init__(self) -> None:
        # topic -> [handlers]
        self._handlers: dict[str, list[Callable[[Event], None]]] = defaultdict(list)
        # 通配符订阅前缀 -> [handlers]
        self._wildcard_handlers: dict[str, list[Callable[[Event], None]]] = defaultdict(list)

    def subscribe(self, topic: str, handler: Callable[[Event], None]) -> None:
        """订阅指定主题。

        参数
        ----
        topic:
            主题名称，支持通配符：
            - "order.*" 匹配所有以 "order." 开头的主题
            - "*" 匹配所有主题
        handler:
            事件处理函数，签名为 (event: Event) -> None
        """
        if topic.endswith(".*"):
            prefix = topic[:-2]
            self._wildcard_handlers[prefix].append(handler)
        elif topic == "*":
            self._wildcard_handlers[""].append(handler)
        else:
            self._handlers[topic].append(handler)

    def publish(self, topic: str, event: Event) -> None:
        """发布事件到指定主题。

        所有订阅该主题（包括通配符匹配）的处理器都会被调用。

        参数
        ----
        topic:
            主题名称，例如 "order.filled"
        event:
            事件对象
        """
        # 精确匹配
        for handler in self._handlers.get(topic, []):
            handler(event)

        # 通配符匹配
        for prefix, handlers in self._wildcard_handlers.items():
            if not prefix or topic.startswith(prefix + "."):
                for handler in handlers:
                    handler(event)

    def unsubscribe(self, topic: str, handler: Callable[[Event], None]) -> None:
        """取消订阅。

        参数
        ----
        topic:
            主题名称（必须与订阅时完全一致，包括通配符）
        handler:
            要移除的处理器函数
        """
        if topic.endswith(".*"):
            prefix = topic[:-2]
            if handler in self._wildcard_handlers.get(prefix, []):
                self._wildcard_handlers[prefix].remove(handler)
        elif topic == "*":
            if handler in self._wildcard_handlers.get("", []):
                self._wildcard_handlers[""].remove(handler)
        else:
            if handler in self._handlers.get(topic, []):
                self._handlers[topic].remove(handler)

    def clear(self) -> None:
        """清空所有订阅。"""
        self._handlers.clear()
        self._wildcard_handlers.clear()
