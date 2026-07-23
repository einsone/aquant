"""双均线策略示例。

经典的双均线交叉策略：
- 短期均线上穿长期均线时买入
- 短期均线下穿长期均线时卖出

这是最简单的趋势跟踪策略，适合入门学习。
"""

from datetime import date

from aquant.core.context import Context
from aquant.core.engine import BacktestConfig, Engine
from aquant.data.alds import ALDSDataSource
from aquant.strategy.base import Strategy
from aquant.strategy.signal import Signal


# 股票池定义
UNIVERSE = ["000001.SZ", "000002.SZ", "600000.SH", "600519.SH"]


class DualMovingAverageStrategy(Strategy):
    """双均线策略。

    参数
    ----
    short_window : int
        短期均线窗口，默认 5
    long_window : int
        长期均线窗口，默认 20
    """

    warmup_period: int = 60
    rebalance_mode: str = "replace"

    def __init__(self, short_window: int = 5, long_window: int = 20, data_source: ALDSDataSource | None = None):
        self.short_window = short_window
        self.long_window = long_window
        self.data_source = data_source

        # 存储每个标的的价格历史
        self.price_history: dict[str, list[float]] = {}

    def on_bar(self, context: Context) -> list[Signal]:
        """每日调用，生成交易信号。"""
        if self.data_source is None:
            return []

        signals = []

        # 从数据源加载当日行情
        bars = self.data_source.load_bars(context.current_date, set(UNIVERSE))

        # 更新价格历史
        for symbol, bar in bars.items():
            if symbol not in self.price_history:
                self.price_history[symbol] = []

            self.price_history[symbol].append(bar.close)

            # 只保留需要的历史数据
            if len(self.price_history[symbol]) > self.long_window:
                self.price_history[symbol] = self.price_history[symbol][-self.long_window :]

        # 计算均线并生成信号
        for symbol in UNIVERSE:
            prices = self.price_history.get(symbol, [])
            if len(prices) < self.long_window:
                # 数据不足，跳过
                continue

            # 计算短期和长期均线
            short_ma = sum(prices[-self.short_window :]) / self.short_window
            long_ma = sum(prices[-self.long_window :]) / self.long_window

            # 判断交叉
            if short_ma > long_ma:
                # 金叉：短期均线在长期均线之上，买入信号
                # 等权重配置
                signals.append(Signal(symbol=symbol, weight=1.0 / len(UNIVERSE)))
            # else: 死叉或无信号，不持仓（自动平仓）

        return signals


def main():
    """运行双均线策略回测。"""
    # 创建数据源
    data_source = ALDSDataSource()

    # 创建策略
    strategy = DualMovingAverageStrategy(short_window=5, long_window=20, data_source=data_source)

    # 配置回测
    config = BacktestConfig(start=date(2023, 1, 1), end=date(2023, 12, 31), initial_capital=1_000_000.0)

    # 创建引擎并运行
    engine = Engine(strategy=strategy, data_source=data_source, config=config)
    result = engine.run()

    # 输出结果
    print("=" * 50)
    print("双均线策略回测结果")
    print("=" * 50)
    print(f"策略参数: 短期={strategy.short_window}, 长期={strategy.long_window}")
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

    render_html(result, path="dual_ma_report.html")
    print()
    print("HTML 报告已生成: dual_ma_report.html")


if __name__ == "__main__":
    main()
