"""性能分析工具

提供性能分析、瓶颈识别和优化建议。
"""

import cProfile
import pstats
import time
from collections.abc import Callable
from functools import wraps
from io import StringIO
from pathlib import Path
from typing import Any

import structlog


logger = structlog.get_logger()


def profile_function(func: Callable | None = None, output_file: str | None = None) -> Callable:
    """函数性能分析装饰器

    Args:
        func: 被装饰的函数
        output_file: 输出文件路径，None 则打印到控制台

    示例：
        @profile_function
        def my_func():
            # 你的代码
            pass

        # 或指定输出文件
        @profile_function(output_file="my_func.prof")
        def my_func():
            pass
    """

    def decorator(f: Callable) -> Callable:
        @wraps(f)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            profiler = cProfile.Profile()
            profiler.enable()

            try:
                result = f(*args, **kwargs)
                return result
            finally:
                profiler.disable()

                # 生成统计报告
                s = StringIO()
                ps = pstats.Stats(profiler, stream=s).sort_stats("cumulative")
                ps.print_stats(50)  # 打印前 50 项

                if output_file:
                    Path(output_file).write_text(s.getvalue())
                    logger.info("性能分析报告已保存", file=output_file)
                else:
                    print(s.getvalue())

        return wrapper

    # 支持 @profile_function 和 @profile_function(output_file="...")
    if func is None:
        return decorator
    return decorator(func)


def time_function(func: Callable) -> Callable:
    """函数计时装饰器

    示例：
        @time_function
        def slow_func():
            time.sleep(1)
    """

    @wraps(func)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        start = time.perf_counter()
        result = func(*args, **kwargs)
        elapsed = time.perf_counter() - start

        func_name = getattr(func, "__name__", repr(func))
        logger.info("函数执行时间", function=func_name, elapsed=f"{elapsed:.4f}s")
        return result

    return wrapper


class PerformanceProfiler:
    """性能分析器

    用于分析回测引擎的性能瓶颈。

    示例：
        profiler = PerformanceProfiler()

        with profiler:
            result = engine.run()

        profiler.save_report("performance.txt")
        profiler.print_top(20)
    """

    def __init__(self):
        self.profiler = cProfile.Profile()
        self.stats = None

    def __enter__(self):
        self.profiler.enable()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.profiler.disable()
        self.stats = pstats.Stats(self.profiler)
        return False

    def print_top(self, n: int = 20, sort_by: str = "cumulative"):
        """打印前 N 项耗时统计

        Args:
            n: 显示项数
            sort_by: 排序方式（cumulative, time, calls）
        """
        if not self.stats:
            logger.warning("未采集性能数据")
            return

        self.stats.sort_stats(sort_by)
        self.stats.print_stats(n)

    def save_report(self, output_file: str, sort_by: str = "cumulative"):
        """保存性能报告

        Args:
            output_file: 输出文件路径
            sort_by: 排序方式
        """
        if not self.stats:
            logger.warning("未采集性能数据")
            return

        self.stats.sort_stats(sort_by)

        s = StringIO()
        old_stream = self.stats.stream
        self.stats.stream = s  # type: ignore[assignment]
        self.stats.print_stats()
        self.stats.stream = old_stream

        Path(output_file).write_text(s.getvalue())
        logger.info("性能报告已保存", file=output_file)

    def get_top_functions(self, n: int = 10, sort_by: str = "cumulative") -> list[tuple]:
        """获取最耗时的函数列表

        Args:
            n: 返回数量
            sort_by: 排序方式

        Returns:
            函数列表，每项为 (function_name, cumulative_time, call_count)
        """
        if not self.stats:
            return []

        self.stats.sort_stats(sort_by)

        # 提取统计数据
        func_list = []
        stats_dict = self.stats.stats  # type: ignore[attr-defined]
        for func, stat in list(stats_dict.items())[:n]:
            filename, line, func_name = func
            cc, nc, tt, ct, callers = stat
            func_list.append((f"{filename}:{line}({func_name})", ct, cc))

        return func_list


class Timer:
    """简单的计时器

    示例：
        timer = Timer()
        timer.start("data_loading")
        # 加载数据
        timer.stop("data_loading")

        timer.start("computation")
        # 计算
        timer.stop("computation")

        timer.print_summary()
    """

    def __init__(self):
        self.timings: dict[str, list[float]] = {}
        self.active: dict[str, float] = {}

    def start(self, name: str):
        """开始计时"""
        self.active[name] = time.perf_counter()

    def stop(self, name: str) -> float:
        """停止计时并返回耗时"""
        if name not in self.active:
            logger.warning("计时器未启动", name=name)
            return 0.0

        elapsed = time.perf_counter() - self.active[name]
        del self.active[name]

        if name not in self.timings:
            self.timings[name] = []
        self.timings[name].append(elapsed)

        return elapsed

    def get_average(self, name: str) -> float:
        """获取平均耗时"""
        if name not in self.timings or not self.timings[name]:
            return 0.0
        return sum(self.timings[name]) / len(self.timings[name])

    def get_total(self, name: str) -> float:
        """获取总耗时"""
        if name not in self.timings:
            return 0.0
        return sum(self.timings[name])

    def print_summary(self):
        """打印统计摘要"""
        print("\n性能统计摘要:")
        print(f"{'名称':<20} {'调用次数':<10} {'总耗时':<15} {'平均耗时':<15}")
        print("-" * 60)

        for name, times in sorted(self.timings.items(), key=lambda x: sum(x[1]), reverse=True):
            count = len(times)
            total = sum(times)
            avg = total / count
            print(f"{name:<20} {count:<10} {total:<15.4f}s {avg:<15.6f}s")
