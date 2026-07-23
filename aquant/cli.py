"""Aquant 命令行工具。

提供便捷的命令行接口：
- aquant run: 运行策略回测
- aquant benchmark: 性能基准测试
- aquant validate: 验证策略代码
"""

import argparse
import importlib.util
import sys
from pathlib import Path


def load_strategy_module(strategy_path: str):
    """动态加载策略模块。"""
    path = Path(strategy_path)
    if not path.exists():
        raise FileNotFoundError(f"策略文件不存在: {strategy_path}")

    spec = importlib.util.spec_from_file_location("strategy_module", path)
    if spec is None or spec.loader is None:
        raise ImportError(f"无法加载策略文件: {strategy_path}")

    module = importlib.util.module_from_spec(spec)
    sys.modules["strategy_module"] = module
    spec.loader.exec_module(module)
    return module


def cmd_run(args):
    """运行策略回测。"""
    print(f"运行策略: {args.strategy}")

    try:
        module = load_strategy_module(args.strategy)

        # 查找并调用 main 函数
        if not hasattr(module, "main"):
            print("错误: 策略文件必须包含 main() 函数")
            return 1

        module.main()
        return 0
    except Exception as e:
        print(f"错误: {e}")
        import traceback

        traceback.print_exc()
        return 1


def cmd_benchmark(args):
    """运行性能基准测试。"""
    print("运行性能基准测试...")

    try:
        from examples import benchmark

        benchmark.main()
        return 0
    except Exception as e:
        print(f"错误: {e}")
        import traceback

        traceback.print_exc()
        return 1


def cmd_validate(args):
    """验证策略代码。"""
    print(f"验证策略: {args.strategy}")

    try:
        module = load_strategy_module(args.strategy)

        # 检查必需的组件
        checks = {"Strategy class": False, "main() function": False}

        # 查找 Strategy 子类
        from aquant.strategy.base import Strategy

        for name in dir(module):
            obj = getattr(module, name)
            if isinstance(obj, type) and issubclass(obj, Strategy) and obj != Strategy:
                checks["Strategy class"] = True
                print(f"  ✓ 找到策略类: {name}")

        # 检查 main 函数
        if hasattr(module, "main"):
            checks["main() function"] = True
            print("  ✓ 找到 main() 函数")

        # 输出结果
        print()
        all_passed = all(checks.values())
        if all_passed:
            print("✓ 验证通过")
            return 0
        else:
            print("✗ 验证失败:")
            for check, passed in checks.items():
                if not passed:
                    print(f"  - 缺少 {check}")
            return 1

    except Exception as e:
        print(f"错误: {e}")
        import traceback

        traceback.print_exc()
        return 1


def cmd_optimize(args):
    """运行策略参数优化。"""
    print(f"优化策略: {args.strategy}")
    print(f"优化方法: {args.method}")

    try:
        module = load_strategy_module(args.strategy)

        # 查找优化配置
        if not hasattr(module, "PARAM_SPACE"):
            print("错误: 策略文件必须定义 PARAM_SPACE 参数空间")
            return 1

        param_space = module.PARAM_SPACE

        if args.method == "grid":
            from aquant.optimization.grid_search import GridSearchOptimizer

            optimizer = GridSearchOptimizer(param_space)
            print(f"网格搜索将测试 {optimizer.total_combinations()} 组参数")

        elif args.method == "genetic":
            from aquant.optimization.genetic_algorithm import GeneticAlgorithm

            optimizer = GeneticAlgorithm(param_space, population_size=args.population, generations=args.generations)
            print(f"遗传算法将运行 {args.generations} 代，种群大小 {args.population}")

        else:
            print(f"错误: 不支持的优化方法 {args.method}")
            return 1

        # 运行优化
        if hasattr(module, "optimize"):
            results = module.optimize(optimizer)
            print("\n优化完成，最佳参数:")
            for key, value in results["best_params"].items():
                print(f"  {key}: {value}")
            print(f"最佳收益: {results['best_score']:.2%}")
        else:
            print("错误: 策略文件必须包含 optimize() 函数")
            return 1

        return 0

    except Exception as e:
        print(f"错误: {e}")
        import traceback

        traceback.print_exc()
        return 1


def cmd_report(args):
    """生成回测报告。"""
    print(f"生成报告: {args.result}")

    try:
        import pickle
        from pathlib import Path

        # 加载回测结果
        result_path = Path(args.result)
        with result_path.open("rb") as f:
            result = pickle.load(f)

        # 生成报告
        from aquant.reporting.report_generator import ReportGenerator

        generator = ReportGenerator()
        output_path = args.output or "report.html"
        generator.generate(result, output_path)

        print(f"✓ 报告已生成: {output_path}")
        return 0

    except Exception as e:
        print(f"错误: {e}")
        import traceback

        traceback.print_exc()
        return 1


def cmd_init(args):
    """创建新策略模板。"""
    from pathlib import Path

    strategy_name = args.name
    output_file = args.output or f"{strategy_name.lower()}.py"

    template = f'''"""
{strategy_name} 策略

描述: [在此填写策略说明]
"""

from datetime import date

from aquant.context import Context
from aquant.strategy.base import Strategy


class {strategy_name}(Strategy):
    """自定义策略"""

    def __init__(self):
        super().__init__()
        # 在此初始化策略参数

    def on_data(self, context: Context, date: date) -> dict[str, float]:
        """生成交易信号

        Args:
            context: 上下文对象
            date: 当前日期

        Returns:
            股票代码 -> 目标权重的字典
        """
        # 在此实现策略逻辑
        return {{}}


def main():
    """运行回测"""
    from aquant.backtest.engine import BacktestConfig, BacktestEngine
    from aquant.data.synthetic import SyntheticDataSource

    # 配置回测
    config = BacktestConfig(
        start_date=date(2023, 1, 1),
        end_date=date(2023, 12, 31),
        initial_capital=1_000_000,
    )

    # 准备数据
    symbols = ["000001.SZ", "000002.SZ"]
    data_source = SyntheticDataSource()
    bars = data_source.get_bars(symbols, config.start_date, config.end_date)

    # 运行回测
    engine = BacktestEngine(config)
    strategy = {strategy_name}()
    result = engine.run(strategy, bars)

    # 输出结果
    print(f"总收益率: {{result.total_return:.2%}}")
    print(f"年化收益率: {{result.annualized_return:.2%}}")
    print(f"夏普比率: {{result.sharpe_ratio:.2f}}")
    print(f"最大回撤: {{result.max_drawdown:.2%}}")


if __name__ == "__main__":
    main()
'''

    try:
        output_path = Path(output_file)
        output_path.write_text(template, encoding="utf-8")

        print(f"✓ 策略模板已创建: {output_file}")
        print("\n下一步:")
        print(f"  1. 编辑 {output_file} 实现策略逻辑")
        print(f"  2. 运行 aquant validate {output_file} 验证代码")
        print(f"  3. 运行 aquant run {output_file} 执行回测")
        return 0

    except Exception as e:
        print(f"错误: {e}")
        return 1


def main():
    """CLI 入口函数。"""
    parser = argparse.ArgumentParser(prog="aquant", description="Aquant 量化回测框架命令行工具")

    subparsers = parser.add_subparsers(dest="command", help="可用命令")

    # run 命令
    run_parser = subparsers.add_parser("run", help="运行策略回测")
    run_parser.add_argument("strategy", help="策略文件路径 (例如: my_strategy.py)")

    # benchmark 命令
    subparsers.add_parser("benchmark", help="运行性能基准测试")

    # validate 命令
    validate_parser = subparsers.add_parser("validate", help="验证策略代码")
    validate_parser.add_argument("strategy", help="策略文件路径")

    # optimize 命令
    optimize_parser = subparsers.add_parser("optimize", help="优化策略参数")
    optimize_parser.add_argument("strategy", help="策略文件路径")
    optimize_parser.add_argument("--method", choices=["grid", "genetic"], default="grid", help="优化方法 (默认: grid)")
    optimize_parser.add_argument("--population", type=int, default=50, help="遗传算法种群大小 (默认: 50)")
    optimize_parser.add_argument("--generations", type=int, default=20, help="遗传算法代数 (默认: 20)")

    # report 命令
    report_parser = subparsers.add_parser("report", help="生成回测报告")
    report_parser.add_argument("result", help="回测结果文件路径 (.pkl)")
    report_parser.add_argument("--output", "-o", help="输出 HTML 文件路径 (默认: report.html)")

    # init 命令
    init_parser = subparsers.add_parser("init", help="创建新策略模板")
    init_parser.add_argument("name", help="策略名称 (例如: MyStrategy)")
    init_parser.add_argument("--output", "-o", help="输出文件路径 (默认: <name>.py)")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return 1

    # 路由到对应的命令处理函数
    commands = {"run": cmd_run, "benchmark": cmd_benchmark, "validate": cmd_validate, "optimize": cmd_optimize, "report": cmd_report, "init": cmd_init}

    handler = commands.get(args.command)
    if handler:
        return handler(args)
    else:
        parser.print_help()
        return 1


if __name__ == "__main__":
    sys.exit(main())
