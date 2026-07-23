"""配对交易策略示例

基于两只相关股票的价差进行交易：
- 当价差偏离均值时开仓
- 当价差回归均值时平仓
"""

from datetime import date

from aquant import BacktestConfig, Engine, Signal, Strategy
from aquant.data.alds import ALDSDataSource


class PairsTradingStrategy(Strategy):
    """配对交易策略"""

    warmup_period = 60
    rebalance_mode = "replace"

    def __init__(self, data_source, pair_a: str, pair_b: str):
        self.data_source = data_source
        self.pair_a = pair_a  # 股票 A
        self.pair_b = pair_b  # 股票 B
        # 策略参数
        self.lookback = 30  # 计算均值的回溯期
        self.entry_threshold = 2.0  # 开仓阈值（标准差倍数）
        self.exit_threshold = 0.5  # 平仓阈值（标准差倍数）
        # 持仓状态
        self.position = None  # None, 'long_spread', 'short_spread'

    def on_bar(self, context):
        """计算价差并生成交易信号"""
        # 获取两只股票的历史数据
        bars_a = context.query.get_bars(symbol=self.pair_a, count=self.warmup_period)
        bars_b = context.query.get_bars(symbol=self.pair_b, count=self.warmup_period)

        if len(bars_a) < self.warmup_period or len(bars_b) < self.warmup_period:
            return []

        # 计算价差序列
        spreads = []
        for bar_a, bar_b in zip(bars_a, bars_b):
            spread = bar_a.close - bar_b.close
            spreads.append(spread)

        # 计算价差统计量
        recent_spreads = spreads[-self.lookback :]
        mean_spread = sum(recent_spreads) / len(recent_spreads)
        variance = sum((s - mean_spread) ** 2 for s in recent_spreads) / len(recent_spreads)
        std_spread = variance**0.5

        if std_spread == 0:
            return []

        # 当前价差的 Z-score
        current_spread = spreads[-1]
        z_score = (current_spread - mean_spread) / std_spread

        signals = []

        # 交易逻辑
        if self.position is None:
            # 无持仓时判断开仓
            if z_score > self.entry_threshold:
                # 价差过高：做空价差（卖 A 买 B）
                signals.append(Signal(symbol=self.pair_a, weight=-0.5))
                signals.append(Signal(symbol=self.pair_b, weight=0.5))
                self.position = "short_spread"
            elif z_score < -self.entry_threshold:
                # 价差过低：做多价差（买 A 卖 B）
                signals.append(Signal(symbol=self.pair_a, weight=0.5))
                signals.append(Signal(symbol=self.pair_b, weight=-0.5))
                self.position = "long_spread"
        else:
            # 有持仓时判断平仓
            should_exit = False
            if (self.position == "short_spread" and z_score < self.exit_threshold) or (self.position == "long_spread" and z_score > -self.exit_threshold):
                should_exit = True

            if should_exit:
                # 平仓：清空持仓
                signals = []
                self.position = None

        return signals


def main():
    # 配置回测
    config = BacktestConfig(start=date(2023, 1, 1), end=date(2023, 12, 31), initial_capital=1_000_000.0, commission_rate=0.0003, stamp_duty_rate=0.001, min_commission=5.0, show_progress=True)

    # 选择一对相关股票（示例：两只银行股）
    pair_a = "600036.SH"  # 招商银行
    pair_b = "601398.SH"  # 工商银行

    # 运行回测
    data_source = ALDSDataSource()
    strategy = PairsTradingStrategy(data_source, pair_a, pair_b)
    engine = Engine(strategy, data_source, config)
    result = engine.run()

    # 输出结果
    print("\n" + "=" * 70)
    print(f"配对交易策略回测结果（{pair_a} vs {pair_b}）")
    print("=" * 70)
    print(f"总收益率: {result.metrics['total_return'] * 100:.2f}%")
    print(f"年化收益率: {result.metrics['annual_return'] * 100:.2f}%")
    print(f"夏普比率: {result.metrics['sharpe']:.2f}")
    print(f"最大回撤: {result.metrics['max_drawdown'] * 100:.2f}%")
    print(f"胜率: {result.metrics['win_rate'] * 100:.2f}%")
    print(f"交易次数: {len(result.portfolio.trade_log)}")
    print("=" * 70)

    # 生成报告
    result.render_html(path="pairs_trading_report.html", open_browser=False)
    print("\n报告已生成：pairs_trading_report.html")


if __name__ == "__main__":
    main()
