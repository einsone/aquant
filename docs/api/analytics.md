# 分析工具

绩效分析和报告生成工具。

## 指标计算

::: aquant.analytics.metrics.compute_all
    options:
      show_root_heading: true
      show_source: false

## 支持的指标

### 收益指标

- `total_return`: 总收益率
- `annual_return`: 年化收益率
- `cumulative_returns`: 累计收益曲线

### 风险指标

- `volatility`: 波动率（年化）
- `max_drawdown`: 最大回撤
- `sharpe`: 夏普比率
- `sortino`: 索提诺比率
- `calmar`: 卡玛比率

### 交易指标

- `win_rate`: 胜率
- `profit_loss_ratio`: 盈亏比
- `avg_holding_days`: 平均持仓天数
- `turnover_rate`: 换手率

### 相对指标（需要基准）

- `alpha`: Alpha
- `beta`: Beta
- `information_ratio`: 信息比率
- `tracking_error`: 跟踪误差

## HTML 报告

生成可交互的 HTML 回测报告：

```python
result = engine.run()

# 生成报告
result.render_html(
    path="backtest_report.html",
    open_browser=True  # 自动在浏览器打开
)
```

报告包含：

- 净值曲线图表
- 回撤曲线
- 收益分布
- 持仓明细
- 交易记录
- 绩效指标

## Markdown 报告

生成简洁的 Markdown 报告：

```python
result = engine.run()

# 生成报告
report = result.report(path="backtest_report.md")
print(report)
```
