# 工具模块使用指南

Aquant 提供了一套实用工具，帮助你分析策略性能和管理数据。

## 策略分析器 (StrategyAnalyzer)

策略分析器提供深度分析功能，帮助你更好地理解策略表现。

### 基本使用

```python
from aquant.tools.strategy_analyzer import StrategyAnalyzer

# 运行回测
result = engine.run()

# 创建分析器
analyzer = StrategyAnalyzer(result)

# 获取完整分析摘要
summary = analyzer.summary()
print(summary)
```

### 月度收益分析

```python
# 获取月度收益率
monthly_returns = analyzer.monthly_returns()

# 打印月度收益
for date, ret in monthly_returns.items():
    print(f"{date}: {ret:.2%}")
```

输出示例：
```
2023-01: 2.35%
2023-02: -0.87%
2023-03: 1.45%
...
```

### 年度收益分析

```python
# 获取年度收益率
yearly_returns = analyzer.yearly_returns()

for year, ret in yearly_returns.items():
    print(f"{year}: {ret:.2%}")
```

### 滚动指标分析

#### 滚动夏普比率

```python
# 计算滚动夏普比率（252天窗口）
rolling_sharpe = analyzer.rolling_sharpe(window=252)

# 可视化
import matplotlib.pyplot as plt
rolling_sharpe.plot()
plt.title("滚动夏普比率 (252天)")
plt.show()
```

#### 滚动最大回撤

```python
# 计算滚动最大回撤
rolling_dd = analyzer.rolling_max_drawdown(window=252)

rolling_dd.plot()
plt.title("滚动最大回撤 (252天)")
plt.show()
```

### 盈亏分析

```python
# 获取盈亏统计
win_loss = analyzer.win_loss_analysis()

print(f"总交易次数: {win_loss['total_trades']}")
print(f"盈利次数: {win_loss['win_trades']}")
print(f"亏损次数: {win_loss['loss_trades']}")
print(f"胜率: {win_loss['win_rate']:.2%}")
print(f"平均盈利: {win_loss['avg_win']:.2f}")
print(f"平均亏损: {win_loss['avg_loss']:.2f}")
print(f"盈亏比: {win_loss['profit_factor']:.2f}")
```

输出示例：
```
总交易次数: 45
盈利次数: 28
亏损次数: 17
胜率: 62.22%
平均盈利: 1250.50
平均亏损: -850.30
盈亏比: 1.47
```

### 持仓周期分析

```python
# 分析持仓周期
holding = analyzer.holding_period_analysis()

print(f"平均持仓天数: {holding['avg_holding_days']:.1f}")
print(f"最短持仓: {holding['min_holding_days']} 天")
print(f"最长持仓: {holding['max_holding_days']} 天")
```

### 换手率分析

```python
# 计算换手率
turnover = analyzer.turnover_analysis()

print(f"日均换手率: {turnover['daily_turnover']:.2%}")
print(f"月均换手率: {turnover['monthly_turnover']:.2%}")
```

### 行业暴露分析

```python
# 分析行业暴露（需要行业数据）
exposure = analyzer.sector_exposure()

for sector, weight in exposure.items():
    print(f"{sector}: {weight:.2%}")
```

### 完整示例

```python
from datetime import date
from aquant.core.engine import Engine, BacktestConfig
from aquant.data.alds import ALDSDataSource
from aquant.tools.strategy_analyzer import StrategyAnalyzer
from my_strategy import MyStrategy

# 运行回测
config = BacktestConfig(
    start=date(2023, 1, 1),
    end=date(2023, 12, 31),
    initial_capital=1_000_000,
)

data_source = ALDSDataSource()
strategy = MyStrategy(data_source)
engine = Engine(strategy, data_source, config)
result = engine.run()

# 创建分析器
analyzer = StrategyAnalyzer(result)

# 1. 月度收益热力图
monthly = analyzer.monthly_returns()
# ... 绘制热力图 ...

# 2. 滚动指标
rolling_sharpe = analyzer.rolling_sharpe(window=60)
rolling_dd = analyzer.rolling_max_drawdown(window=60)

# 3. 盈亏分析
win_loss = analyzer.win_loss_analysis()
print(f"胜率: {win_loss['win_rate']:.2%}")
print(f"盈亏比: {win_loss['profit_factor']:.2f}")

# 4. 持仓分析
holding = analyzer.holding_period_analysis()
print(f"平均持仓: {holding['avg_holding_days']:.1f} 天")

# 5. 换手率
turnover = analyzer.turnover_analysis()
print(f"日均换手: {turnover['daily_turnover']:.2%}")

# 6. 完整摘要
summary = analyzer.summary()
for category, metrics in summary.items():
    print(f"\n{category}:")
    for key, value in metrics.items():
        print(f"  {key}: {value}")
```

## 数据工具 (DataTools)

数据工具提供数据下载、清洗和转换功能。

### 数据下载器 (DataDownloader)

#### 初始化

```python
from aquant.tools.data_tools import DataDownloader

# 使用默认缓存目录
downloader = DataDownloader()

# 或指定缓存目录
downloader = DataDownloader(cache_dir="/path/to/cache")
```

#### 下载股票列表

```python
# 下载股票列表（使用合成数据）
symbols = downloader.download_stock_list(source="synthetic")
print(f"共 {len(symbols)} 只股票")

# 使用 Tushare（需要 token）
symbols = downloader.download_stock_list(
    source="tushare",
    token="your_tushare_token"
)

# 使用 AKShare
symbols = downloader.download_stock_list(source="akshare")
```

#### 下载日线数据

```python
from datetime import date

symbols = ["000001.SZ", "000002.SZ", "600000.SH"]
start_date = date(2023, 1, 1)
end_date = date(2023, 12, 31)

# 下载数据
df = downloader.download_daily_bars(
    symbols=symbols,
    start_date=start_date,
    end_date=end_date,
    source="synthetic"  # 或 "tushare", "akshare"
)

print(df.head())
```

#### 清空缓存

```python
# 清空所有缓存
downloader.clear_cache()

# 或手动删除特定缓存文件
import os
cache_file = downloader.cache_dir / "daily_synthetic_2023-01-01_2023-12-31.parquet"
if cache_file.exists():
    os.remove(cache_file)
```

### 数据清洗器 (DataCleaner)

#### 移除异常值

```python
from aquant.tools.data_tools import DataCleaner
import pandas as pd

df = pd.read_csv("raw_data.csv")

# 移除价格异常值（超过均值 ±3 标准差）
cleaned = DataCleaner.remove_outliers(df, column="close", n_std=3.0)

print(f"原始数据: {len(df)} 行")
print(f"清洗后: {len(cleaned)} 行")
```

#### 填充缺失日期

```python
# 填充缺失的交易日
filled = DataCleaner.fill_missing_dates(df, date_column="date")

# 使用前向填充
filled = DataCleaner.fill_missing_dates(
    df, 
    date_column="date",
    method="ffill"
)
```

#### 标准化股票代码

```python
# 标准化股票代码格式
df["symbol"] = df["symbol"].apply(DataCleaner.normalize_symbol)

# 或批量处理
normalized_df = DataCleaner.normalize_symbols(df, column="symbol")
```

### 数据转换器 (DataConverter)

#### 转换为 Aquant 格式

```python
from aquant.tools.data_tools import DataConverter

# 从 DataFrame 转换为 DayBar 列表
bars = DataConverter.to_aquant_format(df)

# 用于回测
for bar in bars:
    print(f"{bar.symbol} {bar.date}: {bar.close}")
```

#### CSV 文件操作

```python
# 读取 CSV
df = DataConverter.from_csv("data.csv")

# 保存为 CSV
DataConverter.to_csv(df, "output.csv")
```

#### Parquet 文件操作

```python
# 读取 Parquet（更快，更小）
df = DataConverter.from_parquet("data.parquet")

# 保存为 Parquet
DataConverter.to_parquet(df, "output.parquet")
```

### 完整数据处理流程

```python
from datetime import date
from aquant.tools.data_tools import (
    DataDownloader,
    DataCleaner,
    DataConverter
)

# 1. 下载数据
downloader = DataDownloader(cache_dir=".cache")
symbols = ["000001.SZ", "000002.SZ", "600000.SH"]

df = downloader.download_daily_bars(
    symbols=symbols,
    start_date=date(2023, 1, 1),
    end_date=date(2023, 12, 31),
    source="tushare",
    token="your_token"
)

# 2. 清洗数据
# 移除异常值
df_clean = DataCleaner.remove_outliers(df, "close", n_std=3.0)

# 填充缺失日期
df_filled = DataCleaner.fill_missing_dates(df_clean, "date")

# 标准化股票代码
df_normalized = DataCleaner.normalize_symbols(df_filled)

# 3. 保存处理后的数据
DataConverter.to_parquet(df_normalized, "processed_data.parquet")

# 4. 转换为 Aquant 格式用于回测
bars = DataConverter.to_aquant_format(df_normalized)
print(f"共处理 {len(bars)} 条数据")
```

## 最佳实践

### 策略分析

1. **定期分析**：每次修改策略后都运行完整分析
2. **对比基准**：将策略指标与市场基准对比
3. **关注细节**：不只看总收益，要关注胜率、盈亏比、持仓周期等
4. **滚动分析**：使用滚动指标观察策略稳定性

### 数据管理

1. **使用缓存**：下载数据后使用缓存，避免重复下载
2. **数据清洗**：始终清洗原始数据，移除异常值
3. **标准格式**：统一使用 Parquet 格式存储，提升性能
4. **版本控制**：对处理后的数据打上时间戳或版本号

## 相关文档

- [CLI 工具指南](./cli.md)
- [策略开发指南](./guide/01_basics.md)
- [性能优化](./performance.md)
