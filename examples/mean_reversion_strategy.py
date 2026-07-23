"""均值回归策略示例

基于布林带的均值回归策略：
- 价格突破上轨时做空
- 价格突破下轨时做多
- 回归中轨时平仓
"""

from datetime import date

from aquant import BacktestConfig, Engine, Signal, Strategy
from aquant.data.alds import ALDSDataSource


class MeanReversionStrategy(Strategy):
    """均值回归策略（布林带）"""

    warmup_period = 60
    rebalance_mode = "replace"

    def __init__(self, data_source):
        self.data_source = data_source
        self.universe = ["000001.SZ", "600000.SH", "000002.SZ"]
        # 布林带参数
        self.bb_period = 20  # 均线周期
        self.bb_std = 2.0  # 标准差倍数
        # 持仓状态
        self.positions = {}  # symbol -> 'long' | 'short' | None

    def on_bar(self, context):
        """计算布林带并生成信号"""
        signals = []

        for symbol in self.universe:
            bars = context.query.get_bars(symbol=symbol, count=self.warmup_period)

            if len(bars) < self.bb_period:
                continue

            # 计算布林带
            closes = [b.close for b in bars[-self.bb_period :]]
            middle = sum(closes) / len(closes)
            variance = sum((c - middle) ** 2 for c in closes) / len(closes)
            std = variance**0.5

            upper = middle + self.bb_std * std
            lower = middle - self.bb_std * std
            current_price = bars[-1].close

            # 获取当前持仓状态
            current_pos = self.positions.get(symbol)

            # 交易逻辑
            if current_pos is None:
                # 无持仓：寻找开仓机会
                if current_price > upper:
                    # 突破上轨：做空（预期回归）
                    signals.append(Signal(symbol=symbol, weight=-0.3))
                    self.positions[symbol] = "short"
                elif current_price < lower:
                    # 突破下轨：做多（预期回归）
                    signals.append(Signal(symbol=symbol, weight=0.3))
                    self.positions[symbol] = "long"
            else:
                # 有持仓：判断平仓
                if current_pos == "short" and current_price <= middle:
                    # 空头平仓：价格回归中轨
                    self.positions[symbol] = None
                elif current_pos == "long" and current_price >= middle:
                    # 多头平仓：价格回归中轨
                    self.positions[symbol] = None

        # 清理已平仓的股票信号（weight=0）
        active_symbols = {s.symbol for s in signals}
        for symbol in list(self.positions.keys()):
            if self.positions[symbol] is None and symbol not in active_symbols:
                signals.append(Signal(symbol=symbol, weight=0.0))
                del self.positions[symbol]

        return signals


def main():
    # 配置回测
    config = BacktestConfig(
        start=date(2023, 1, 1),
        end=date(2023, 12, 31),
        initial_capital=1_000_000.0,
        commission_rate=0.0003,
        stamp_duty_rate=0.001,
        min_commission=5.0,
        show_progress=True,
    )

    # 运行回测
    data_source = ALDSDataSource()
    strategy = MeanReversionStrategy(data_source)
    engine = Engine(strategy, data_source, config)
    result = engine.run()

    # 输出结果
    print("\n" + "=" * 70)
    print("均值回归策略回测结果")
    print("=" * 70)
    print(f"总收益率: {result.metrics['total_return'] * 100:.2f}%")
    print(f"年化收益率: {result.metrics['annual_return'] * 100:.2f}%")
    print(f"夏普比率: {result.metrics['sharpe']:.2f}")
    print(f"最大回撤: {result.metrics['max_drawdown'] * 100:.2f}%")
    print(f"胜率: {result.metrics['win_rate'] * 100:.2f}%")
    print(f"交易次数: {len(result.portfolio.trade_log)}")
    print("=" * 70)

    # 生成报告
    result.render_html(path="mean_reversion_report.html", open_browser=False)
    print("\n报告已生成：mean_reversion_report.html")


if __name__ == "__main__":
    main()
