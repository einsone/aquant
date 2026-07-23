"""工具使用示例

演示如何使用 aquant 工具包进行策略分析和数据处理。
"""

from datetime import date

from aquant.backtest.engine import BacktestConfig, BacktestEngine
from aquant.data.synthetic import SyntheticDataSource
from aquant.strategy.base import Strategy
from aquant.tools import DataDownloader, StrategyAnalyzer


class SimpleStrategy(Strategy):
    """简单示例策略"""

    def on_data(self, context, date):
        # 等权重持仓
        symbols = list(context.universe)
        if not symbols:
            return {}
        weight = 1.0 / len(symbols)
        return dict.fromkeys(symbols, weight)


def example_strategy_analysis():
    """示例：策略分析"""
    print("=" * 60)
    print("策略分析示例")
    print("=" * 60)

    # 运行回测
    config = BacktestConfig(start_date=date(2023, 1, 1), end_date=date(2023, 12, 31), initial_capital=1_000_000)

    symbols = ["000001.SZ", "000002.SZ", "600000.SH"]
    data_source = SyntheticDataSource()
    bars = data_source.get_bars(symbols, config.start_date, config.end_date)

    engine = BacktestEngine(config)
    strategy = SimpleStrategy()
    result = engine.run(strategy, bars)

    # 使用分析器
    analyzer = StrategyAnalyzer(result)

    # 基础指标
    print("\n基础指标:")
    print(f"  总收益率: {result.total_return:.2%}")
    print(f"  年化收益率: {result.annualized_return:.2%}")
    print(f"  夏普比率: {result.sharpe_ratio:.2f}")
    print(f"  最大回撤: {result.max_drawdown:.2%}")

    # 月度收益
    print("\n月度收益:")
    monthly = analyzer.monthly_returns()
    for month, ret in monthly.items():
        print(f"  {month.strftime('%Y-%m')}: {ret:.2%}")

    # 盈亏分析
    print("\n盈亏分析:")
    win_loss = analyzer.win_loss_analysis()
    print(f"  总交易次数: {win_loss['total_trades']}")
    print(f"  胜率: {win_loss['win_rate']:.2%}")
    print(f"  盈亏比: {win_loss['profit_factor']:.2f}")

    # 持仓周期
    print("\n持仓周期:")
    holding = analyzer.holding_period_analysis()
    print(f"  平均持仓天数: {holding['avg_holding_days']:.1f}")

    # 换手率
    print("\n换手率:")
    turnover = analyzer.turnover_analysis()
    print(f"  月度换手率: {turnover['monthly_turnover']:.2%}")


def example_data_download():
    """示例：数据下载"""
    print("\n" + "=" * 60)
    print("数据下载示例")
    print("=" * 60)

    downloader = DataDownloader(cache_dir=".aquant_cache")

    # 下载股票列表
    print("\n下载股票列表...")
    symbols = downloader.download_stock_list(source="synthetic")
    print(f"获取到 {len(symbols)} 只股票")
    print(f"前 5 只: {symbols[:5]}")

    # 下载日线数据
    print("\n下载日线数据...")
    df = downloader.download_daily_bars(symbols=symbols[:3], start_date=date(2023, 1, 1), end_date=date(2023, 3, 31), source="synthetic")
    print(f"获取到 {len(df)} 条数据")
    print("\n数据预览:")
    print(df.head())


def example_data_cleaning():
    """示例：数据清洗"""
    print("\n" + "=" * 60)
    print("数据清洗示例")
    print("=" * 60)

    from aquant.tools import DataCleaner, DataConverter

    # 下载数据
    downloader = DataDownloader()
    df = downloader.download_daily_bars(symbols=["000001.SZ"], start_date=date(2023, 1, 1), end_date=date(2023, 3, 31), source="synthetic")

    print(f"\n原始数据: {len(df)} 行")

    # 清洗数据
    cleaner = DataCleaner()

    # 标准化股票代码
    df = cleaner.normalize_symbols(df)
    print("✓ 股票代码已标准化")

    # 转换为 aquant 格式
    bars = DataConverter.to_aquant_format(df)
    print(f"✓ 已转换为 {len(bars)} 个 DayBar 对象")

    # 保存到 CSV
    DataConverter.to_csv(df, "cleaned_data.csv")
    print("✓ 数据已保存到 cleaned_data.csv")


def main():
    """运行所有示例"""
    example_strategy_analysis()
    example_data_download()
    example_data_cleaning()

    print("\n" + "=" * 60)
    print("所有示例运行完成！")
    print("=" * 60)


if __name__ == "__main__":
    main()
