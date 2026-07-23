from __future__ import annotations

import itertools
from typing import TYPE_CHECKING

from aquant.core.engine import BacktestConfig, Engine


if TYPE_CHECKING:
    from aquant.data.source import DataSource
    from aquant.strategy.base import Strategy


def grid_search(strategy_cls: type[Strategy], param_grid: dict[str, list], config: BacktestConfig, data_source: DataSource, metric: str = "sharpe"):
    """对 param_grid 中所有参数组合分别运行回测。

    返回 polars DataFrame，每行对应一组参数，
    列 = 参数名 + BacktestResult.metrics 中的所有绩效指标。
    """
    import polars as pl

    if not param_grid:
        return pl.DataFrame()

    keys = list(param_grid.keys())
    combinations = list(itertools.product(*[param_grid[k] for k in keys]))

    rows: list[dict] = []
    for combo in combinations:
        params = dict(zip(keys, combo, strict=True))
        strategy = strategy_cls(**params)
        # 注入 data_source 和 universe，策略可能需要访问
        if not hasattr(strategy, "data_source"):
            strategy.data_source = data_source  # type: ignore[attr-defined]
        if not hasattr(strategy, "universe") and hasattr(config, "universe"):
            strategy.universe = config.universe  # type: ignore[attr-defined]
        engine = Engine(strategy=strategy, data_source=data_source, config=config)
        result = engine.run()
        row = {**params, **result.metrics}
        rows.append(row)

    if not rows:
        return pl.DataFrame()

    return pl.DataFrame(rows)
