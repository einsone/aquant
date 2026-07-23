"""多因子选股策略示例

结合多个因子进行股票选择：
- 动量因子：过去 20 日收益率
- 反转因子：过去 5 日收益率
- 成交量因子：相对平均成交量
"""

from datetime import date

from aquant import BacktestConfig, Engine, Signal, Strategy
from aquant.data.alds import ALDSDataSource


class MultiFactorStrategy(Strategy):
    """多因子选股策略"""

    warmup_period = 60
    rebalance_mode = "replace"

    def __init__(self, data_source):
        self.data_source = data_source
        # 股票池：沪深 300 成分股示例
        self.universe = ["000001.SZ", "000002.SZ", "000333.SZ", "600000.SH", "600036.SH", "600519.SH"]
        # 因子权重
        self.momentum_weight = 0.4
        self.reversal_weight = 0.3
        self.volume_weight = 0.3
        # 持仓股票数
        self.top_n = 3

    def on_bar(self, context):
        """计算因子得分并选股"""
        scores = {}

        for symbol in self.universe:
            bars = context.query.get_bars(symbol=symbol, count=self.warmup_period)

            if len(bars) < self.warmup_period:
                continue

            # 计算各因子
            momentum = self._calc_momentum(bars)
            reversal = self._calc_reversal(bars)
            volume = self._calc_volume(bars)

            # 加权合成总得分
            total_score = self.momentum_weight * momentum + self.reversal_weight * reversal + self.volume_weight * volume

            scores[symbol] = total_score

        # 选出得分最高的 top_n 只股票
        sorted_stocks = sorted(scores.items(), key=lambda x: x[1], reverse=True)
        top_stocks = sorted_stocks[: self.top_n]

        # 生成等权重信号
        signals = []
        weight = 1.0 / len(top_stocks) if top_stocks else 0.0
        for symbol, _score in top_stocks:
            signals.append(Signal(symbol=symbol, weight=weight))

        return signals

    def _calc_momentum(self, bars: list) -> float:
        """动量因子：过去 20 日收益率"""
        if len(bars) < 20:
            return 0.0
        return (bars[-1].close - bars[-20].close) / bars[-20].close

    def _calc_reversal(self, bars: list) -> float:
        """反转因子：过去 5 日收益率的负值"""
        if len(bars) < 5:
            return 0.0
        return -(bars[-1].close - bars[-5].close) / bars[-5].close

    def _calc_volume(self, bars: list) -> float:
        """成交量因子：当前成交量相对 20 日均量"""
        if len(bars) < 20:
            return 0.0
        avg_volume = sum(b.volume for b in bars[-20:]) / 20
        if avg_volume == 0:
            return 0.0
        return bars[-1].volume / avg_volume - 1.0


def main():
    # 配置回测
    config = BacktestConfig(start=date(2023, 1, 1), end=date(2023, 12, 31), initial_capital=1_000_000.0, commission_rate=0.0003, stamp_duty_rate=0.001, min_commission=5.0, show_progress=True)

    # 运行回测
    data_source = ALDSDataSource()
    strategy = MultiFactorStrategy(data_source)
    engine = Engine(strategy, data_source, config)
    result = engine.run()

    # 输出结果
    print("\n" + "=" * 70)
    print("多因子选股策略回测结果")
    print("=" * 70)
    print(f"总收益率: {result.metrics['total_return'] * 100:.2f}%")
    print(f"年化收益率: {result.metrics['annual_return'] * 100:.2f}%")
    print(f"夏普比率: {result.metrics['sharpe']:.2f}")
    print(f"最大回撤: {result.metrics['max_drawdown'] * 100:.2f}%")
    print(f"胜率: {result.metrics['win_rate'] * 100:.2f}%")
    print(f"交易次数: {len(result.portfolio.trade_log)}")
    print("=" * 70)

    # 生成报告
    result.render_html(path="multi_factor_report.html", open_browser=False)
    print("\n报告已生成：multi_factor_report.html")


if __name__ == "__main__":
    main()
