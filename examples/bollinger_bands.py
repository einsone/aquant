"""布林带策略示例。

布林带策略利用价格的统计特性：
- 当价格触及下轨时买入（超卖）
- 当价格触及上轨时卖出（超买）
- 中轨为移动平均线，上下轨为±2倍标准差

这是经典的均值回归策略。
"""

from datetime import date

from aquant.core.context import Context
from aquant.core.engine import BacktestConfig, Engine
from aquant.data.csv import CSVDataSource, create_sample_csv
from aquant.strategy.base import Strategy
from aquant.strategy.signal import Signal


class BollingerBandsStrategy(Strategy):
    """布林带策略。

    参数
    ----
    window : int
        均线窗口，默认 20
    num_std : float
        标准差倍数，默认 2.0
    symbols : list[str]
        股票池
    """

    warmup_period: int = 40
    rebalance_mode: str = "replace"

    def __init__(self, window: int = 20, num_std: float = 2.0, symbols: list[str] | None = None, data_source: CSVDataSource | None = None):
        self.window = window
        self.num_std = num_std
        self.symbols = symbols or []
        self.data_source = data_source

        # 存储价格历史
        self.price_history: dict[str, list[float]] = {}

    def on_bar(self, context: Context) -> list[Signal]:
        """每日调用，生成交易信号。"""
        if self.data_source is None:
            return []

        signals = []

        # 从数据源加载当日行情
        bars = self.data_source.load_bars(context.current_date, set(self.symbols))

        # 更新价格历史
        for symbol, bar in bars.items():
            if symbol not in self.price_history:
                self.price_history[symbol] = []

            self.price_history[symbol].append(bar.close)

            # 只保留需要的历史数据
            if len(self.price_history[symbol]) > self.window:
                self.price_history[symbol] = self.price_history[symbol][-self.window :]

        # 计算布林带并生成信号
        buy_candidates = []

        for symbol in self.symbols:
            prices = self.price_history.get(symbol, [])
            if len(prices) < self.window:
                continue

            # 计算布林带
            mean = sum(prices) / self.window
            variance = sum((p - mean) ** 2 for p in prices) / self.window
            std = variance**0.5

            upper_band = mean + self.num_std * std
            lower_band = mean - self.num_std * std

            current_price = prices[-1]

            # 生成信号
            if current_price <= lower_band:
                # 触及下轨，超卖，买入信号
                buy_candidates.append(symbol)
            elif current_price >= upper_band:
                # 触及上轨，超买，卖出信号（不持仓）
                pass

        # 等权重配置买入标的
        if buy_candidates:
            weight = 1.0 / len(buy_candidates)
            for symbol in buy_candidates:
                signals.append(Signal(symbol=symbol, weight=weight))

        return signals


def main():
    """运行布林带策略回测。"""
    # 定义股票池
    symbols = ["AAPL", "GOOGL", "MSFT", "AMZN", "TSLA"]

    # 生成模拟数据
    print("生成模拟数据...")
    data_dir = "data/bollinger"
    create_sample_csv(data_dir=data_dir, symbols=symbols, start=date(2022, 1, 1), end=date(2023, 12, 31))
    print(f"  数据已生成: {data_dir}")

    # 创建数据源
    data_source = CSVDataSource(data_dir)

    # 创建策略
    strategy = BollingerBandsStrategy(window=20, num_std=2.0, symbols=symbols, data_source=data_source)

    # 配置回测
    config = BacktestConfig(start=date(2022, 1, 1), end=date(2023, 12, 31), initial_capital=1_000_000.0)

    # 创建引擎并运行
    engine = Engine(strategy=strategy, data_source=data_source, config=config)
    result = engine.run()

    # 输出结果
    print("=" * 50)
    print("布林带策略回测结果")
    print("=" * 50)
    print(f"策略参数: 窗口={strategy.window}, 标准差={strategy.num_std}")
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

    render_html(result, path="bollinger_bands_report.html")
    print()
    print("HTML 报告已生成: bollinger_bands_report.html")


if __name__ == "__main__":
    main()
