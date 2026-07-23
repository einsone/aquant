from __future__ import annotations

from typing import TYPE_CHECKING


if TYPE_CHECKING:
    from datetime import date

    from aquant.core.context import Context
    from aquant.portfolio.position import PositionView
    from aquant.portfolio.query import PortfolioQueryService


class ContextPool:
    """Context 对象池，用于减少频繁创建销毁带来的开销。

    策略回测时每个交易日都会创建新的 Context 对象传递给策略，
    在高频场景下会产生大量的对象分配和 GC 压力。使用对象池可以
    复用字典对象，降低内存分配开销。

    实现说明：
        - Context 本身是 frozen dataclass，无法修改属性，因此每次都创建新 Context
        - 但 positions 字典可以复用：从池中获取字典，清空后重新填充
        - 这样可以避免每次创建新字典时的内存分配和哈希表初始化开销

    使用示例::

        pool = ContextPool(max_size=10)

        # 获取 Context 对象
        ctx = pool.get(
            current_date=date.today(),
            positions=positions_dict,
            cash=100000.0,
            total_value=150000.0,
            query=query_service
        )

        # 使用完毕后归还（目前自动回收，无需显式调用）

    注意：
        - max_size 应根据策略数量和并发度调整，默认 10 适合单策略顺序回测
        - 当前实现主要优化字典创建开销，Context 对象本身仍每次创建
    """

    def __init__(self, max_size: int = 10):
        """初始化对象池。

        参数：
            max_size: 池中最多保留的字典数量。
        """
        self._pool: list[dict[str, PositionView]] = []
        self._max_size = max_size

    def get(
        self,
        current_date: date,
        positions: dict[str, PositionView],
        cash: float,
        total_value: float,
        query: PortfolioQueryService,
    ) -> Context:
        """从池中获取一个 Context 对象。

        会尝试从池中复用字典对象以减少内存分配。

        参数：
            current_date: 当前仿真日期。
            positions: 当前持仓字典。
            cash: 当前可用现金。
            total_value: 组合总市值。
            query: 组合查询服务。

        返回：
            配置好的 Context 对象。
        """
        from aquant.core.context import Context

        # 尝试从池中复用字典
        if self._pool:
            positions_dict = self._pool.pop()
            positions_dict.clear()
            positions_dict.update(positions)
        else:
            positions_dict = positions.copy()

        # Context 是 frozen dataclass，每次都要创建新对象
        # 但复用了字典可以减少一些内存分配开销
        ctx = Context(
            current_date=current_date,
            positions=positions_dict,
            cash=cash,
            total_value=total_value,
            query=query,
        )

        # 回测结束后字典会被回收到池中（由 Engine 管理）
        return ctx

    def recycle(self, positions_dict: dict[str, PositionView]) -> None:
        """回收 positions 字典到池中。

        参数：
            positions_dict: 要回收的字典对象。
        """
        if len(self._pool) < self._max_size:
            self._pool.append(positions_dict)
