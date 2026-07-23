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

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return 1

    # 路由到对应的命令处理函数
    commands = {"run": cmd_run, "benchmark": cmd_benchmark, "validate": cmd_validate}

    handler = commands.get(args.command)
    if handler:
        return handler(args)
    else:
        parser.print_help()
        return 1


if __name__ == "__main__":
    sys.exit(main())
