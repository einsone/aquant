"""带风控的动量策略示例。

展示：
- RiskManager 的使用
- QueryService 查询历史数据
- 多重风控规则组合

这是更接近实战的完整策略示例。
"""

from datetime import date

from aquant.core.context import Context
from aquant.core.engine import BacktestConfig, Engine
from aquant.data.csv import CSVDataSource, create_sample_csv
from aquant.risk import ConcentrationRule, MaxDrawdownRule, MaxPositionSizeRule, RiskManager
from aquant.strategy.base import Strategy
from aquant.strategy.signal import Signal


class RiskControlledMomentumStrategy(Strategy):
    """带风控的动量策略。

    参数
    ----
    lookback : int
        动量计算回看期，默认 20 天
    top_n : int
        选取涨幅前 N 名，默认 5
    max_drawdown_threshold : float
        最大回撤阈值，超过则清仓，默认 0.10（10%）
    symbols : list[str]
        股票池
    """

    warmup_period: int = 60
    rebalance_mode: str = "replace"

    def __init__(self, lookback: int = 20, top_n: int = 5, max_drawdown_threshold: float = 0.10, symbols: list[str] | None = None, data_source: CSVDataSource | None = None):
        self.lookback = lookback
        self.top_n = top_n
        self.max_drawdown_threshold = max_drawdown_threshold
        self.symbols = symbols or []
        self.data_source = data_source

        # 存储价格历史
        self.price_history: dict[str, list[float]] = {}

    def on_bar(self, context: Context) -> list[Signal]:
        """每日调用，生成交易信号。"""
        if self.data_source is None:
            return []

        # 风控检查：回撤超过阈值时清仓
        current_dd = context.query.get_current_drawdown()
        if current_dd > self.max_drawdown_threshold:
            return []  # 返回空信号，清空所有持仓

        # 从数据源加载当日行情
        bars = self.data_source.load_bars(context.current_date, set(self.symbols))

        # 更新价格历史
        for symbol, bar in bars.items():
            if symbol not in self.price_history:
                self.price_history[symbol] = []

            self.price_history[symbol].append(bar.close)

            # 只保留需要的历史数据
            if len(self.price_history[symbol]) > self.lookback:
                self.price_history[symbol] = self.price_history[symbol][-self.lookback :]

        # 计算动量并排序
        momentum_scores = []
        for symbol in self.symbols:
            prices = self.price_history.get(symbol, [])
            if len(prices) < self.lookback:
                continue

            # 计算动量（当前价格 / 过去价格 - 1）
            momentum = (prices[-1] / prices[0]) - 1.0
            momentum_scores.append((symbol, momentum))

        # 按动量降序排列
        momentum_scores.sort(key=lambda x: x[1], reverse=True)

        # 选取前 N 名
        top_stocks = momentum_scores[: self.top_n]

        if not top_stocks:
            return []

        # 等权重配置
        weight = 1.0 / len(top_stocks)
        signals = [Signal(symbol=symbol, weight=weight) for symbol, _ in top_stocks]

        return signals


def main():
    """运行带风控的动量策略回测。"""
    # 定义股票池
    symbols = ["AAPL", "GOOGL", "MSFT", "AMZN", "TSLA", "NVDA", "META", "NFLX"]

    # 生成模拟数据
    print("生成模拟数据...")
    data_dir = "data/risk_momentum"
    create_sample_csv(data_dir=data_dir, symbols=symbols, start=date(2022, 1, 1), end=date(2023, 12, 31))
    print(f"  数据已生成: {data_dir}")

    # 创建数据源
    data_source = CSVDataSource(data_dir)

    # 创建策略
    strategy = RiskControlledMomentumStrategy(lookback=20, top_n=5, max_drawdown_threshold=0.10, symbols=symbols, data_source=data_source)

    # 配置回测
    config = BacktestConfig(start=date(2022, 1, 1), end=date(2023, 12, 31), initial_capital=1_000_000.0)

    # 配置风控规则
    risk_manager = RiskManager(
        rules=[
            MaxPositionSizeRule(max_ratio=0.25),  # 单仓位不超过 25%
            MaxDrawdownRule(max_dd=0.15),  # 最大回撤不超过 15%
            ConcentrationRule(top_n=3, max_concentration=0.6),  # 前 3 大持仓不超过 60%
        ]
    )

    # 创建引擎并运行
    engine = Engine(strategy=strategy, data_source=data_source, config=config, risk_manager=risk_manager)
    result = engine.run()

    # 输出结果
    print("=" * 50)
    print("带风控的动量策略回测结果")
    print("=" * 50)
    print(f"策略参数: 回看期={strategy.lookback}, 选股数={strategy.top_n}")
    print(f"风控阈值: 最大回撤={strategy.max_drawdown_threshold:.1%}")
    print(f"回测区间: {config.start} 至 {config.end}")
    print(f"初始资金: {config.initial_capital:,.0f} 元")
    print()
    print("绩效指标:")
    print(f"  总收益率:   {result.metrics['total_return']:>8.2%}")
    print(f"  年化收益率: {result.metrics['annualized_return']:>8.2%}")
    print(f"  夏普比率:   {result.metrics['sharpe']:>8.2f}")
    print(f"  最大回撤:   {result.metrics['max_drawdown']:>8.2%}")
    print(f"  卡玛比率:   {result.metrics['calmar']:>8.2f}")
    print(f"  胜率:       {result.metrics['win_rate']:>8.2%}")
    print(f"  盈亏比:     {result.metrics['profit_loss_ratio']:>8.2f}")
    print()
    print(f"总成交次数: {len(result.portfolio.trade_log)} 笔")

    # 生成报告
    from aquant.analytics.report import render_html

    render_html(result, path="risk_controlled_momentum_report.html")
    print()
    print("HTML 报告已生成: risk_controlled_momentum_report.html")


if __name__ == "__main__":
    main()
