from __future__ import annotations

from typing import TYPE_CHECKING


if TYPE_CHECKING:
    from aquant.events.event import Event


class EventQueue:
    """按 (date, phase) 排序的事件队列，基于列表实现。

    所有事件在初始化阶段一次性写入，迭代时按排序顺序弹出。
    不支持运行时动态插入——仿真是封闭循环。
    """

    def __init__(self) -> None:
        self._events: list[Event] = []
        self._index: int = 0

    def push(self, event: Event) -> None:
        self._events.append(event)

    def seal(self) -> None:
        """对所有事件排序。所有事件写入完毕后调用一次。"""
        self._events.sort()

    def __iter__(self) -> EventQueue:
        return self

    def __next__(self) -> Event:
        if self._index >= len(self._events):
            raise StopIteration
        event = self._events[self._index]
        self._index += 1
        return event

    def __len__(self) -> int:
        return len(self._events) - self._index
