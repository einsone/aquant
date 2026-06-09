from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING


if TYPE_CHECKING:
    from datetime import date


@dataclass
class Signal:
    """单个标的的目标权重信号。

    属性：
        symbol: 标的代码，须与 ``load_bars`` 返回的键一致。
        weight: 目标权重，相对于组合总市值的比例。
            ``0.1`` 表示该标的占组合 10%，``0`` 表示清仓。
            负值预留用于做空，当前版本不支持。
        signal_date: 信号生成日期，由框架在 SIGNAL 阶段自动填入，
            策略无需手动设置。用于日志、调试和审计。
        meta: 可选的自由格式字典，用于存储策略内部的附加信息
            （如因子值、置信度等），框架不使用此字段。
    """

    symbol: str
    weight: float
    signal_date: date | None = field(default=None)
    meta: dict = field(default_factory=dict)
