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
    import json
    import pickle

    if not args.quiet:
        print(f"运行策略: {args.strategy}")

    try:
        module = load_strategy_module(args.strategy)

        # 如果提供了配置文件，从配置文件加载参数
        config_override = {}
        if args.config:
            config_path = Path(args.config)
            if not config_path.exists():
                print(f"错误: 配置文件不存在: {args.config}")
                return 1

            with config_path.open() as f:
                if args.config.endswith(".json"):
                    config_override = json.load(f)
                else:
                    print("错误: 仅支持 JSON 配置文件")
                    return 1

            if not args.quiet:
                print(f"加载配置: {args.config}")

        # 查找并调用 main 函数
        if not hasattr(module, "main"):
            print("错误: 策略文件必须包含 main() 函数")
            return 1

        # 传递配置覆盖
        if config_override:
            if hasattr(module, "apply_config"):
                module.apply_config(config_override)
            elif not args.quiet:
                print("警告: 策略未实现 apply_config()，忽略配置文件")

        # 运行回测
        result = module.main()

        # 保存结果
        if args.output:
            output_path = Path(args.output)
            output_path.parent.mkdir(parents=True, exist_ok=True)

            if args.format == "pickle":
                with output_path.open("wb") as f:
                    pickle.dump(result, f)
                if not args.quiet:
                    print(f"✓ 结果已保存: {output_path} (pickle)")

            elif args.format == "json":
                # 提取可序列化的指标
                metrics = result.metrics if hasattr(result, "metrics") else {}
                with output_path.open("w") as f:
                    json.dump(metrics, f, indent=2, default=str)
                if not args.quiet:
                    print(f"✓ 指标已保存: {output_path} (JSON)")

        if not args.quiet:
            print("\n✓ 回测完成")

        return 0

    except Exception as e:
        print(f"错误: {e}")
        if args.verbose:
            import traceback

            traceback.print_exc()
        return 1


def cmd_analyze(args):
    """分析回测结果。"""
    import pickle

    result_path = Path(args.result)
    if not result_path.exists():
        print(f"错误: 结果文件不存在: {args.result}")
        return 1

    try:
        with result_path.open("rb") as f:
            result = pickle.load(f)

        if not hasattr(result, "metrics"):
            print("错误: 结果对象没有 metrics 属性")
            return 1

        metrics = result.metrics

        print("=" * 60)
        print("回测结果分析")
        print("=" * 60)

        # 基本信息
        if hasattr(result, "trades") and result.trades:
            print("\n交易统计:")
            print(f"  总交易次数: {len(result.trades)}")

        # 性能指标
        print("\n收益指标:")
        if "total_return" in metrics:
            print(f"  总收益率: {metrics['total_return']:.2%}")
        if "annualized_return" in metrics:
            print(f"  年化收益率: {metrics['annualized_return']:.2%}")
        if "sharpe" in metrics:
            print(f"  夏普比率: {metrics['sharpe']:.4f}")
        if "sortino" in metrics:
            print(f"  索提诺比率: {metrics['sortino']:.4f}")

        print("\n风险指标:")
        if "max_drawdown" in metrics:
            print(f"  最大回撤: {metrics['max_drawdown']:.2%}")
        if "calmar" in metrics:
            print(f"  卡玛比率: {metrics['calmar']:.4f}")
        if "volatility" in metrics:
            print(f"  波动率: {metrics['volatility']:.2%}")

        # 详细分析
        if args.detailed:
            print("\n详细指标:")
            for key, value in sorted(metrics.items()):
                if key not in ["total_return", "annualized_return", "sharpe", "sortino", "max_drawdown", "calmar", "volatility"]:
                    if isinstance(value, float):
                        print(f"  {key}: {value:.4f}")
                    else:
                        print(f"  {key}: {value}")

        # 比较基准
        if args.compare:
            compare_path = Path(args.compare)
            if not compare_path.exists():
                print(f"\n警告: 对比文件不存在: {args.compare}")
            else:
                with compare_path.open("rb") as f:
                    compare_result = pickle.load(f)

                if hasattr(compare_result, "metrics"):
                    compare_metrics = compare_result.metrics
                    print("\n与基准对比:")

                    key_metrics = ["total_return", "sharpe", "max_drawdown", "calmar"]
                    for key in key_metrics:
                        if key in metrics and key in compare_metrics:
                            diff = metrics[key] - compare_metrics[key]
                            symbol = "↑" if diff > 0 else "↓"
                            print(f"  {key}: {metrics[key]:.4f} vs {compare_metrics[key]:.4f} ({symbol} {abs(diff):.4f})")

        print("\n" + "=" * 60)
        return 0

    except Exception as e:
        print(f"错误: {e}")
        if args.verbose:
            import traceback

            traceback.print_exc()
        return 1


def cmd_list(args):
    """列出可用的策略、数据源或示例。"""
    if args.type == "strategies":
        # 扫描常见策略目录
        strategy_dirs = [Path("strategies"), Path("examples"), Path()]

        strategies = []
        for dir_path in strategy_dirs:
            if not dir_path.exists():
                continue

            for py_file in dir_path.glob("**/*.py"):
                if py_file.name.startswith("_"):
                    continue

                # 尝试加载检查是否包含策略
                try:
                    spec = importlib.util.spec_from_file_location(py_file.stem, py_file)
                    if spec and spec.loader:
                        module = importlib.util.module_from_spec(spec)
                        spec.loader.exec_module(module)

                        # 检查是否有 Strategy 子类
                        from aquant.strategy import Strategy

                        has_strategy = False
                        for name in dir(module):
                            obj = getattr(module, name)
                            if isinstance(obj, type) and issubclass(obj, Strategy) and obj is not Strategy:
                                has_strategy = True
                                break

                        if has_strategy or hasattr(module, "main"):
                            strategies.append(str(py_file))

                except Exception:
                    pass

        if not strategies:
            print("未找到策略文件")
            return 0

        print(f"找到 {len(strategies)} 个策略文件:\n")
        for s in sorted(strategies):
            print(f"  • {s}")

    elif args.type == "examples":
        examples_dir = Path("examples")
        if not examples_dir.exists():
            print("examples 目录不存在")
            return 1

        examples = [f for f in examples_dir.glob("*.py") if not f.name.startswith("_")]

        if not examples:
            print("未找到示例文件")
            return 0

        print(f"找到 {len(examples)} 个示例:\n")
        for ex in sorted(examples):
            print(f"  • {ex.name}")

            # 尝试读取第一行注释作为描述
            try:
                with ex.open() as f:
                    first_line = f.readline().strip()
                    if first_line.startswith("#"):
                        print(f"    {first_line[1:].strip()}")
            except Exception:
                pass

    elif args.type == "data-sources":
        print("可用数据源:\n")
        print("  • SyntheticDataSource - 合成数据（用于测试）")
        print("  • BigQuantDataSource - BigQuant 平台数据")
        print("\n使用方法:")
        print("  from aquant.data.synthetic import SyntheticDataSource")
        print("  from aquant.data.bigquant import BigQuantDataSource")

    return 0


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

    strategy_path = Path(args.strategy)
    if not strategy_path.exists():
        print(f"✗ 错误: 策略文件不存在: {args.strategy}")
        print("\n提示: 请检查文件路径是否正确")
        return 1

    if not strategy_path.suffix == ".py":
        print("✗ 错误: 策略文件必须是 .py 文件")
        return 1

    try:
        module = load_strategy_module(args.strategy)

        # 检查必需的组件
        issues = []
        warnings = []
        info = []

        # 查找 Strategy 子类
        from aquant.strategy.base import Strategy

        strategy_classes = []
        for name in dir(module):
            obj = getattr(module, name)
            if isinstance(obj, type) and issubclass(obj, Strategy) and obj != Strategy:
                strategy_classes.append(name)
                print(f"  ✓ 找到策略类: {name}")

        if not strategy_classes:
            warnings.append("未找到 Strategy 子类（如果使用函数式策略可忽略）")

        # 检查 main 函数
        if hasattr(module, "main"):
            print("  ✓ 找到 main() 函数")
        else:
            issues.append("缺少 main() 函数")

        # 检查优化相关
        if hasattr(module, "PARAM_GRID"):
            info.append("包含参数网格定义 (PARAM_GRID)")

            # 验证优化辅助函数
            required_funcs = ["get_strategy_class", "get_data_source", "get_backtest_config"]
            missing_funcs = [f for f in required_funcs if not hasattr(module, f)]

            if missing_funcs:
                warnings.append(f"定义了 PARAM_GRID 但缺少: {', '.join(missing_funcs)}")
            else:
                info.append("包含完整的优化支持函数")

        # 输出结果
        print()

        if info:
            for item in info:
                print(f"  ℹ {item}")
            print()

        if warnings:
            print("⚠ 警告:")
            for warning in warnings:
                print(f"  • {warning}")
            print()

        if issues:
            print("✗ 验证失败:")
            for issue in issues:
                print(f"  • {issue}")
            print("\n提示: 策略文件必须包含 main() 函数作为入口点")
            return 1

        print("✓ 验证通过")
        return 0

    except SyntaxError as e:
        print(f"\n✗ 语法错误: {e}")
        print(f"  文件: {e.filename}")
        print(f"  行号: {e.lineno}")
        return 1
    except Exception as e:
        print(f"\n✗ 错误: {e}")
        import traceback

        traceback.print_exc()
        return 1


def cmd_optimize(args):
    """运行策略参数优化。"""
    print(f"优化策略: {args.strategy}")
    print(f"优化方法: {args.method}\n")

    strategy_path = Path(args.strategy)
    if not strategy_path.exists():
        print(f"✗ 错误: 策略文件不存在: {args.strategy}")
        return 1

    try:
        module = load_strategy_module(args.strategy)

        # 查找优化配置
        if not hasattr(module, "PARAM_GRID"):
            print("✗ 错误: 策略文件必须定义 PARAM_GRID 参数网格")
            print("\n示例:")
            print("  PARAM_GRID = {")
            print("      'period': [10, 20, 30],")
            print("      'threshold': [0.01, 0.02, 0.03]")
            print("  }")
            return 1

        param_grid = module.PARAM_GRID
        print(f"✓ 找到参数网格: {len(param_grid)} 个参数")

        # 计算总组合数
        from itertools import product

        total_combinations = len(list(product(*param_grid.values())))
        print(f"  总组合数: {total_combinations}\n")

        # 需要策略类、数据源和配置
        missing = []
        if not hasattr(module, "get_strategy_class"):
            missing.append("get_strategy_class()")
        if not hasattr(module, "get_data_source"):
            missing.append("get_data_source()")
        if not hasattr(module, "get_backtest_config"):
            missing.append("get_backtest_config()")

        if missing:
            print("✗ 错误: 策略文件缺少必需的函数:")
            for func in missing:
                print(f"  • {func}")
            print("\n提示: 优化需要这些函数来构建回测环境")
            return 1

        strategy_cls = module.get_strategy_class()
        data_source = module.get_data_source()
        config = module.get_backtest_config()

        if args.method == "grid":
            from aquant.optimization.grid_search import grid_search

            print("网格搜索参数组合...")
            results = grid_search(strategy_cls=strategy_cls, param_grid=param_grid, config=config, data_source=data_source, metric=args.metric if hasattr(args, "metric") else "sharpe")

            if len(results) == 0:
                print("错误: 未生成任何结果")
                return 1

            # 找出最佳参数
            best_row = results.sort(args.metric if hasattr(args, "metric") else "sharpe", descending=True)[0]

            print("\n优化完成，最佳参数:")
            for col in results.columns:
                if col not in ["sharpe", "total_return", "max_drawdown", "calmar", "sortino", "annualized_return"]:
                    print(f"  {col}: {best_row[col][0]}")

            metric_name = args.metric if hasattr(args, "metric") else "sharpe"
            print(f"\n最佳 {metric_name}: {best_row[metric_name][0]:.4f}")

        elif args.method == "genetic":
            from aquant.optimization.genetic_algorithm import GeneticAlgorithm

            # 转换 param_grid 到 param_ranges 格式
            param_ranges = {}
            for key, values in param_grid.items():
                if all(isinstance(v, int) for v in values):
                    param_ranges[key] = (min(values), max(values), int)
                else:
                    param_ranges[key] = (min(values), max(values), float)

            ga = GeneticAlgorithm(
                strategy_class=strategy_cls,
                param_ranges=param_ranges,
                data_source=data_source,
                backtest_config=config,
                population_size=args.population if hasattr(args, "population") else 20,
                generations=args.generations if hasattr(args, "generations") else 10,
                scoring=args.metric if hasattr(args, "metric") else "sharpe",
            )

            print(f"遗传算法将运行 {ga.generations} 代，种群大小 {ga.population_size}")
            best_params = ga.run(verbose=True)

            print("\n优化完成，最佳参数:")
            for key, value in best_params.items():
                print(f"  {key}: {value}")

        else:
            print(f"错误: 不支持的优化方法 {args.method}")
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
            _result = pickle.load(f)

        # 生成报告 - 模块尚未实现
        print("错误: 报告生成模块尚未实现")
        return 1

        # TODO: 实现报告生成
        # from aquant.reporting.report_generator import ReportGenerator
        # generator = ReportGenerator()
        # output_path = args.output or "report.html"
        # generator.generate(result, output_path)
        # print(f"✓ 报告已生成: {output_path}")
        # return 0

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
    run_parser.add_argument("--config", "-c", help="配置文件路径 (JSON 格式)")
    run_parser.add_argument("--output", "-o", help="保存结果到文件")
    run_parser.add_argument("--format", choices=["pickle", "json"], default="pickle", help="输出格式 (默认: pickle)")
    run_parser.add_argument("--quiet", "-q", action="store_true", help="静默模式，不显示进度信息")
    run_parser.add_argument("--verbose", "-v", action="store_true", help="显示详细错误信息")

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

    # list 命令
    list_parser = subparsers.add_parser("list", help="列出可用资源")
    list_parser.add_argument("type", choices=["strategies", "examples", "data-sources"], help="列出的资源类型")

    # analyze 命令
    analyze_parser = subparsers.add_parser("analyze", help="分析回测结果")
    analyze_parser.add_argument("result", help="回测结果文件路径 (.pkl)")
    analyze_parser.add_argument("--detailed", "-d", action="store_true", help="显示详细指标")
    analyze_parser.add_argument("--compare", "-c", help="对比另一个结果文件")
    analyze_parser.add_argument("--verbose", "-v", action="store_true", help="显示详细错误信息")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return 1

    # 路由到对应的命令处理函数
    commands = {"run": cmd_run, "benchmark": cmd_benchmark, "validate": cmd_validate, "optimize": cmd_optimize, "report": cmd_report, "init": cmd_init, "list": cmd_list, "analyze": cmd_analyze}

    handler = commands.get(args.command)
    if handler:
        return handler(args)
    else:
        parser.print_help()
        return 1


if __name__ == "__main__":
    sys.exit(main())
