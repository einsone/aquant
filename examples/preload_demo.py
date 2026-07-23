"""使用数据预加载器的回测示例。

展示如何使用 DataPreloader 提升固定股票池策略的回测性能。
"""

from datetime import date

from aquant.core.context import Context
from aquant.core.engine import BacktestConfig, Engine
from aquant.data.alds import ALDSDataSource
from aquant.data.preloader import DataPreloader
from aquant.strategy.base import Strategy
from aquant.strategy.signal import Signal


# 固定股票池
UNIVERSE = ["000001.SZ", "000002.SZ", "600000.SH", "600519.SH", "600036.SH"]


class SimpleMovingAverageStrategy(Strategy):
    """简单移动平均策略（使用预加载数据）。"""

    warmup_period: int = 20
    rebalance_mode: str = "replace"

    def __init__(self, window: int = 20, preloader: DataPreloader | None = None):
        self.window = window
        self.preloader = preloader
        self.price_history: dict[str, list[float]] = {}

    def on_bar(self, context: Context) -> list[Signal]:
        if self.preloader is None:
            return []

        # 从预加载器获取数据（零 I/O 开销）
        bars = self.preloader.get_bars(context.current_date)

        # 更新价格历史
        for symbol, bar in bars.items():
            if symbol not in self.price_history:
                self.price_history[symbol] = []
            self.price_history[symbol].append(bar.close)
            self.price_history[symbol] = self.price_history[symbol][-self.window :]

        # 计算移动平均并生成信号
        signals = []
        for symbol in UNIVERSE:
            prices = self.price_history.get(symbol, [])
            if len(prices) >= self.window:
                avg = sum(prices) / self.window
                current = prices[-1]

                # 价格高于均线则持有
                if current > avg:
                    signals.append(Signal(symbol=symbol, weight=1.0 / len(UNIVERSE)))

        return signals


def main():
    """运行带预加载的回测。"""
    # 配置回测
    config = BacktestConfig(
        start=date(2023, 1, 1),
        end=date(2023, 12, 31),
        initial_capital=1_000_000.0,
    )

    # 创建数据源
    data_source = ALDSDataSource()

    # 加载交易日历
    trading_days = data_source.load_calendar(config.start, config.end)

    # 创建预加载器（一次性加载所有数据）
    print("预加载数据中...")
    preloader = DataPreloader(
        data_source=data_source,
        trading_days=trading_days,
        symbols=set(UNIVERSE),
        batch_size=50,
    )
    print(f"预加载完成，缓存大小: {preloader._estimate_cache_size():.2f} MB")

    # 创建策略（传入预加载器）
    strategy = SimpleMovingAverageStrategy(window=20, preloader=preloader)

    # 运行回测
    engine = Engine(strategy=strategy, data_source=data_source, config=config)
    result = engine.run()

    # 输出结果
    print("\n" + "=" * 50)
    print("回测结果")
    print("=" * 50)
    print(f"总收益率:   {result.metrics['total_return']:>8.2%}")
    print(f"年化收益率: {result.metrics['annualized_return']:>8.2%}")
    print(f"夏普比率:   {result.metrics['sharpe']:>8.2f}")
    print(f"最大回撤:   {result.metrics['max_drawdown']:>8.2%}")
    print(f"总成交次数: {len(result.portfolio.trade_log)} 笔")


if __name__ == "__main__":
    main()
