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
        self._sealed: bool = False

    def push(self, event: Event) -> None:
        if self._sealed:
            raise RuntimeError("EventQueue 已封闭，seal() 后不允许再调用 push()。")
        self._events.append(event)

    def seal(self) -> None:
        """对所有事件排序并封闭队列。所有事件写入完毕后调用一次。"""
        self._events.sort()
        self._sealed = True

    def __iter__(self) -> EventQueue:
        # BUG-3 修复：每次迭代重置索引，支持重复迭代（如测试场景多次遍历同一队列）
        # 注意：seal() 未调用时迭代会访问未排序的数据，调用方应在 seal() 后再迭代
        self._index = 0
        return self

    def __next__(self) -> Event:
        if self._index >= len(self._events):
            raise StopIteration
        event = self._events[self._index]
        self._index += 1
        return event

    def __len__(self) -> int:
        return len(self._events) - self._index
