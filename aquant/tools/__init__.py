"""Aquant 工具包

提供策略分析、数据处理等实用工具。
"""

from typing import TYPE_CHECKING


if TYPE_CHECKING:
    from aquant.tools.data_tools import DataCleaner, DataConverter, DataDownloader
    from aquant.tools.profiler import PerformanceProfiler, Timer, profile_function, time_function
    from aquant.tools.strategy_analyzer import StrategyAnalyzer
    from aquant.tools.strategy_compare import StrategyComparison


def __getattr__(name: str):
    """延迟导入避免循环依赖和缺失依赖问题"""
    if name in ("DataCleaner", "DataConverter", "DataDownloader"):
        from aquant.tools.data_tools import DataCleaner, DataConverter, DataDownloader

        return {"DataCleaner": DataCleaner, "DataConverter": DataConverter, "DataDownloader": DataDownloader}[name]

    if name == "StrategyAnalyzer":
        from aquant.tools.strategy_analyzer import StrategyAnalyzer

        return StrategyAnalyzer

    if name == "StrategyComparison":
        from aquant.tools.strategy_compare import StrategyComparison

        return StrategyComparison

    if name in ("PerformanceProfiler", "Timer", "profile_function", "time_function"):
        from aquant.tools.profiler import PerformanceProfiler, Timer, profile_function, time_function

        return {"PerformanceProfiler": PerformanceProfiler, "Timer": Timer, "profile_function": profile_function, "time_function": time_function}[name]

    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = ["DataCleaner", "DataConverter", "DataDownloader", "PerformanceProfiler", "StrategyAnalyzer", "StrategyComparison", "Timer", "profile_function", "time_function"]
