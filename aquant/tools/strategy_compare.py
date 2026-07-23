"""策略对比分析工具

用于对比多个策略或参数组合的回测结果。
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

import polars as pl
import structlog


if TYPE_CHECKING:
    from aquant.core.engine import BacktestResult


logger = structlog.get_logger()


class StrategyComparison:
    """策略对比分析器

    用于对比多个策略的回测结果，生成对比报告。

    示例：
        comparison = StrategyComparison()
        comparison.add_result("策略A", result_a)
        comparison.add_result("策略B", result_b)
        comparison.print_summary()
        comparison.render_html("comparison.html")
    """

    def __init__(self):
        self.results: dict[str, BacktestResult] = {}

    def add_result(self, name: str, result: BacktestResult) -> None:
        """添加回测结果

        Args:
            name: 策略名称
            result: 回测结果对象
        """
        self.results[name] = result
        logger.info("添加策略结果", strategy=name)

    def get_metrics_table(self) -> pl.DataFrame:
        """获取指标对比表格

        Returns:
            包含所有策略指标的 DataFrame
        """
        if not self.results:
            return pl.DataFrame()

        rows = []
        for name, result in self.results.items():
            row = {"策略名称": name, **result.metrics}
            rows.append(row)

        return pl.DataFrame(rows)

    def print_summary(self) -> None:
        """打印对比摘要"""
        if not self.results:
            logger.warning("没有可对比的结果")
            return

        df = self.get_metrics_table()

        print("\n" + "=" * 80)
        print("策略对比摘要")
        print("=" * 80)

        # 选择关键指标展示
        key_metrics = [
            "策略名称",
            "total_return",
            "annual_return",
            "sharpe",
            "max_drawdown",
            "win_rate",
            "profit_factor",
        ]

        # 过滤存在的列
        display_cols = [col for col in key_metrics if col in df.columns]

        if display_cols:
            print(df.select(display_cols))
        else:
            print(df)

        print("=" * 80 + "\n")

    def get_best_strategy(self, metric: str = "sharpe") -> tuple[str, float] | None:
        """获取最优策略

        Args:
            metric: 优化目标指标

        Returns:
            (策略名称, 指标值) 或 None
        """
        if not self.results:
            return None

        best_name = None
        best_value = float("-inf")

        for name, result in self.results.items():
            value = result.metrics.get(metric)
            if value is not None and value > best_value:
                best_value = value
                best_name = name

        if best_name:
            return (best_name, best_value)
        return None

    def render_html(self, path: str = "strategy_comparison.html", open_browser: bool = False) -> str:
        """生成 HTML 对比报告

        Args:
            path: 输出文件路径
            open_browser: 是否自动打开浏览器

        Returns:
            输出文件的绝对路径
        """
        if not self.results:
            logger.warning("没有可对比的结果")
            return ""

        # 构建 HTML
        html_parts = [
            "<!DOCTYPE html>",
            "<html>",
            "<head>",
            '<meta charset="UTF-8">',
            "<title>策略对比报告</title>",
            "<style>",
            "body { font-family: Arial, sans-serif; margin: 20px; background: #f5f5f5; }",
            "h1 { color: #333; }",
            "h2 { color: #555; margin-top: 30px; }",
            "table { border-collapse: collapse; width: 100%; background: white; margin: 20px 0; }",
            "th, td { border: 1px solid #ddd; padding: 12px; text-align: left; }",
            "th { background-color: #4CAF50; color: white; }",
            "tr:nth-child(even) { background-color: #f2f2f2; }",
            "tr:hover { background-color: #ddd; }",
            ".best { background-color: #90EE90 !important; font-weight: bold; }",
            ".worst { background-color: #FFB6C1 !important; }",
            ".metric-name { font-weight: bold; }",
            "</style>",
            "</head>",
            "<body>",
            "<h1>策略对比报告</h1>",
        ]

        # 添加摘要表格
        html_parts.append("<h2>指标对比</h2>")
        html_parts.append(self._generate_metrics_table_html())

        # 添加最优策略
        best = self.get_best_strategy()
        if best:
            html_parts.append("<h2>推荐策略</h2>")
            html_parts.append(f"<p>基于夏普比率，推荐使用 <strong>{best[0]}</strong>（夏普比率: {best[1]:.4f}）</p>")

        # 添加详细指标
        html_parts.append("<h2>详细指标</h2>")
        html_parts.append(self._generate_detailed_table_html())

        html_parts.extend(["</body>", "</html>"])

        # 写入文件
        html_content = "\n".join(html_parts)
        output_path = Path(path).resolve()
        output_path.write_text(html_content, encoding="utf-8")

        logger.info("对比报告已生成", path=str(output_path))

        # 打开浏览器
        if open_browser:
            import webbrowser

            webbrowser.open(f"file://{output_path}")

        return str(output_path)

    def _generate_metrics_table_html(self) -> str:
        """生成指标对比表格的 HTML"""
        df = self.get_metrics_table()

        # 选择关键指标
        key_metrics = [
            "total_return",
            "annual_return",
            "sharpe",
            "max_drawdown",
            "win_rate",
            "profit_factor",
        ]

        html = ["<table>", "<tr><th>策略名称</th>"]

        # 表头
        metric_names = {
            "total_return": "累计收益率",
            "annual_return": "年化收益率",
            "sharpe": "夏普比率",
            "max_drawdown": "最大回撤",
            "win_rate": "胜率",
            "profit_factor": "盈亏比",
        }

        for metric in key_metrics:
            if metric in df.columns:
                html.append(f"<th>{metric_names.get(metric, metric)}</th>")
        html.append("</tr>")

        # 数据行
        for row in df.iter_rows(named=True):
            html.append("<tr>")
            html.append(f"<td class='metric-name'>{row['策略名称']}</td>")

            for metric in key_metrics:
                if metric in df.columns:
                    value = row.get(metric)
                    if value is not None:
                        if isinstance(value, float):
                            # 百分比格式
                            if metric in ["total_return", "annual_return", "max_drawdown", "win_rate"]:
                                html.append(f"<td>{value * 100:.2f}%</td>")
                            else:
                                html.append(f"<td>{value:.4f}</td>")
                        else:
                            html.append(f"<td>{value}</td>")
                    else:
                        html.append("<td>-</td>")
            html.append("</tr>")

        html.append("</table>")
        return "".join(html)

    def _generate_detailed_table_html(self) -> str:
        """生成详细指标表格的 HTML"""
        df = self.get_metrics_table()

        html = ["<table>", "<tr><th>策略名称</th>"]

        # 表头（所有指标）
        columns = [col for col in df.columns if col != "策略名称"]
        for col in columns:
            html.append(f"<th>{col}</th>")
        html.append("</tr>")

        # 数据行
        for row in df.iter_rows(named=True):
            html.append("<tr>")
            html.append(f"<td class='metric-name'>{row['策略名称']}</td>")

            for col in columns:
                value = row.get(col)
                if value is not None:
                    if isinstance(value, float):
                        html.append(f"<td>{value:.4f}</td>")
                    else:
                        html.append(f"<td>{value}</td>")
                else:
                    html.append("<td>-</td>")
            html.append("</tr>")

        html.append("</table>")
        return "".join(html)
