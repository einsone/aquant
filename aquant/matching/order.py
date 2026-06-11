from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING


if TYPE_CHECKING:
    from typing import Literal


@dataclass
class Order:
    symbol: str
    side: Literal["buy", "sell"]
    shares: int
    locked: bool = field(default=False)
    liquidate: bool = field(default=False)  # True 表示清仓指令（target_shares == 0）
