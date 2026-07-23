"""测试性能分析工具"""

import time

from aquant.tools.profiler import PerformanceProfiler, Timer, profile_function, time_function


def test_timer_basic():
    """测试 Timer 基本功能"""
    timer = Timer()

    timer.start("test")
    time.sleep(0.01)
    elapsed = timer.stop("test")

    assert elapsed >= 0.01
    assert "test" in timer.timings
    assert len(timer.timings["test"]) == 1
    assert timer.timings["test"][0] >= 0.01


def test_timer_multiple():
    """测试 Timer 多次计时"""
    timer = Timer()

    # 多次计时同一标签
    for _ in range(3):
        timer.start("loop")
        time.sleep(0.01)
        timer.stop("loop")

    assert len(timer.timings["loop"]) == 3
    assert all(t >= 0.01 for t in timer.timings["loop"])


def test_timer_summary(capsys):
    """测试 Timer 打印汇总"""
    timer = Timer()

    timer.start("task1")
    time.sleep(0.01)
    timer.stop("task1")

    timer.start("task2")
    time.sleep(0.02)
    timer.stop("task2")

    timer.print_summary()

    captured = capsys.readouterr()
    assert "task1" in captured.out
    assert "task2" in captured.out


def test_time_function_decorator():
    """测试函数计时装饰器"""

    @time_function
    def slow_function():
        time.sleep(0.01)
        return 42

    result = slow_function()

    assert result == 42


def test_profile_function_decorator():
    """测试函数性能分析装饰器"""

    @profile_function
    def compute_sum(n: int) -> int:
        return sum(range(n))

    result = compute_sum(1000)

    assert result == sum(range(1000))


def test_performance_profiler_context():
    """测试 PerformanceProfiler 上下文管理器"""
    profiler = PerformanceProfiler()

    with profiler:
        total = sum(range(1000))

    assert total == sum(range(1000))
    assert profiler.stats is not None


def test_performance_profiler_print_top(capsys):
    """测试 PerformanceProfiler 打印热点函数"""
    profiler = PerformanceProfiler()

    with profiler:
        sum(range(10000))

    profiler.print_top(5)

    captured = capsys.readouterr()
    assert "function calls" in captured.out


def test_performance_profiler_save_report(tmp_path):
    """测试 PerformanceProfiler 保存报告"""
    profiler = PerformanceProfiler()

    with profiler:
        sum(range(1000))

    report_path = tmp_path / "profile.txt"
    profiler.save_report(str(report_path))

    assert report_path.exists()
    content = report_path.read_text()
    assert "function calls" in content


def test_performance_profiler_no_stats():
    """测试未运行的 PerformanceProfiler"""
    profiler = PerformanceProfiler()

    # print_top 和 save_report 在没有数据时只会警告，不会抛出异常
    profiler.print_top()  # 应该警告但不报错
    profiler.save_report("output.txt")  # 应该警告但不报错

    # 验证确实没有统计数据
    assert profiler.stats is None
