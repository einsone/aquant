from __future__ import annotations

import itertools
from typing import TYPE_CHECKING

from aquant.core.engine import BacktestConfig, Engine


if TYPE_CHECKING:
    from datetime import date

    from aquant.data.source import DataSource
    from aquant.strategy.base import Strategy


def _run_single(strategy_cls: type[Strategy], params: dict, fold_config: BacktestConfig, data_source: DataSource) -> dict:
    strategy = strategy_cls(**params)
    engine = Engine(strategy=strategy, data_source=data_source, config=fold_config)
    result = engine.run()
    return {**params, **result.metrics}


def _run_fold(args: tuple) -> dict:
    """模块顶层函数，确保 multiprocessing 可以 pickle。"""
    strategy_cls, keys, combinations, fold, config, data_source, metric = args

    train_start, train_end, test_start, test_end = fold
    train_cfg = config.model_copy(update={"start": train_start, "end": train_end})

    best_params: dict = dict(zip(keys, combinations[0], strict=True))
    best_score: float = float("-inf")

    for combo in combinations:
        params = dict(zip(keys, combo, strict=True))
        row = _run_single(strategy_cls, params, train_cfg, data_source)
        score = row.get(metric, float("-inf"))
        if isinstance(score, (int, float)) and score > best_score:
            best_score = float(score)
            best_params = params

    test_cfg = config.model_copy(update={"start": test_start, "end": test_end})
    test_row = _run_single(strategy_cls, best_params, test_cfg, data_source)
    return {"fold_train_start": train_start, "fold_train_end": train_end, "fold_test_start": test_start, "fold_test_end": test_end, **test_row}


def walk_forward(strategy_cls: type[Strategy], param_grid: dict[str, list], config: BacktestConfig, data_source: DataSource, train_window: int = 252, test_window: int = 63, metric: str = "sharpe", n_jobs: int = 1):
    """Walk-forward 滚动验证。

    每折在训练集上选出最优参数组合（按指定绩效指标），
    再在测试集上评估该组合的实际表现。

    返回 polars DataFrame，每行对应一个测试折，
    列 = 最优参数 + 测试绩效指标 + fold_train_start/end + fold_test_start/end。

    注意：
    - n_jobs != 1 时使用多进程，策略须在 on_start 中建立数据库连接，
      而不是在 __init__ 中，否则 pickle 序列化会导致跨进程文件锁冲突。
    - n_jobs != 1 时 data_source 也会被 pickle 传给各 worker 进程，
      若其 __init__ 中持有数据库连接（如 DuckDB），需实现 __getstate__/__setstate__
      或采用懒连接，否则 pickle 会失败。
    """
    import polars as pl

    if not param_grid:
        return pl.DataFrame()

    trading_days = sorted(d for d in data_source.load_calendar(config.start, config.end) if config.start <= d <= config.end)

    keys = list(param_grid.keys())
    combinations = list(itertools.product(*[param_grid[k] for k in keys]))

    folds: list[tuple[date, date, date, date]] = []
    idx = 0
    while idx + train_window + test_window <= len(trading_days):
        train_start = trading_days[idx]
        train_end = trading_days[idx + train_window - 1]
        test_start = trading_days[idx + train_window]
        test_end = trading_days[idx + train_window + test_window - 1]
        folds.append((train_start, train_end, test_start, test_end))
        idx += test_window

    if not folds:
        return pl.DataFrame()

    fold_args = [(strategy_cls, keys, combinations, fold, config, data_source, metric) for fold in folds]

    if n_jobs == 1:
        rows = [_run_fold(args) for args in fold_args]
    else:
        import multiprocessing

        workers = n_jobs if n_jobs > 0 else multiprocessing.cpu_count()
        with multiprocessing.Pool(processes=workers) as pool:
            rows = pool.map(_run_fold, fold_args)

    return pl.DataFrame(rows)
