# 数据源接入

本文介绍如何接入自定义数据源，支持各种行情数据提供商。

## 数据源接口

aquant 定义了统一的数据源接口 `DataSource`，所有数据源都需要实现以下方法：

```python
from datetime import date
from aquant.data.source import DataSource
from aquant.market.bar import DayBar

class MyDataSource(DataSource):
    def load_calendar(self, start: date, end: date) -> list[date]:
        """加载交易日历

        Args:
            start: 开始日期
            end: 结束日期

        Returns:
            交易日列表（升序）
        """
        pass

    def load_bars(self, dt: date, symbols: set[str]) -> dict[str, DayBar]:
        """加载指定日期的行情数据

        Args:
            dt: 日期
            symbols: 股票代码集合

        Returns:
            股票代码 -> DayBar 的字典
        """
        pass

    def load_adjustments(self, start: date, end: date):
        """加载企业行动（分红、送转）

        Args:
            start: 开始日期
            end: 结束日期

        Returns:
            调整事件列表
        """
        return []

    def load_delisted(self, start: date, end: date):
        """加载退市信息

        Args:
            start: 开始日期
            end: 结束日期

        Returns:
            退市信息字典
        """
        return {}
```

## DayBar 数据结构

行情数据使用 `DayBar` 表示：

```python
from aquant.market.bar import DayBar, AssetType
from datetime import date

bar = DayBar(
    symbol="000001.SZ",           # 股票代码
    date=date(2023, 1, 3),        # 日期
    open=10.0,                    # 开盘价
    high=10.5,                    # 最高价
    low=9.8,                      # 最低价
    close=10.2,                   # 收盘价
    volume=1000000,               # 成交量
    amount=10200000.0,            # 成交额（可选）
    asset_type=AssetType.STOCK,   # 资产类型（可选）
)
```

## 内置数据源

### ALDSDataSource

从 ALDS 数据服务加载数据：

```python
from aquant.data.alds import ALDSDataSource

data_source = ALDSDataSource()
```

### CSVDataSource

从 CSV 文件加载数据：

```python
from aquant.data.csv import CSVDataSource

# CSV 文件格式：
# symbol,date,open,high,low,close,volume
# 000001.SZ,2023-01-03,10.0,10.5,9.8,10.2,1000000

data_source = CSVDataSource(path="data/bars.csv")
```

## 自定义数据源示例

### 示例 1：从数据库加载

```python
from datetime import date
from aquant.data.source import DataSource
from aquant.market.bar import DayBar
import psycopg2

class PostgreSQLDataSource(DataSource):
    def __init__(self, conn_string: str):
        self.conn = psycopg2.connect(conn_string)

    def load_calendar(self, start: date, end: date) -> list[date]:
        """从数据库加载交易日历"""
        with self.conn.cursor() as cursor:
            cursor.execute(
                """
                SELECT DISTINCT trade_date
                FROM trading_calendar
                WHERE trade_date BETWEEN %s AND %s
                ORDER BY trade_date
                """,
                (start, end)
            )
            return [row[0] for row in cursor.fetchall()]

    def load_bars(self, dt: date, symbols: set[str]) -> dict[str, DayBar]:
        """从数据库加载行情数据"""
        with self.conn.cursor() as cursor:
            cursor.execute(
                """
                SELECT symbol, open, high, low, close, volume, amount
                FROM daily_bars
                WHERE date = %s AND symbol = ANY(%s)
                """,
                (dt, list(symbols))
            )

            bars = {}
            for row in cursor.fetchall():
                symbol, open_, high, low, close, volume, amount = row
                bars[symbol] = DayBar(
                    symbol=symbol,
                    date=dt,
                    open=open_,
                    high=high,
                    low=low,
                    close=close,
                    volume=volume,
                    amount=amount,
                )
            return bars

    def load_adjustments(self, start: date, end: date):
        """加载企业行动"""
        with self.conn.cursor() as cursor:
            cursor.execute(
                """
                SELECT symbol, ex_date, dividend, split_ratio
                FROM corporate_actions
                WHERE ex_date BETWEEN %s AND %s
                """,
                (start, end)
            )
            return cursor.fetchall()

    def load_delisted(self, start: date, end: date):
        """加载退市信息"""
        with self.conn.cursor() as cursor:
            cursor.execute(
                """
                SELECT symbol, delist_date
                FROM delisted_stocks
                WHERE delist_date BETWEEN %s AND %s
                """,
                (start, end)
            )
            return {symbol: delist_date for symbol, delist_date in cursor.fetchall()}
```

### 示例 2：从 Tushare 加载

```python
from datetime import date, timedelta
from aquant.data.source import DataSource
from aquant.market.bar import DayBar
import tushare as ts

class TushareDataSource(DataSource):
    def __init__(self, token: str):
        ts.set_token(token)
        self.pro = ts.pro_api()

    def load_calendar(self, start: date, end: date) -> list[date]:
        """从 Tushare 加载交易日历"""
        df = self.pro.trade_cal(
            exchange='SSE',
            start_date=start.strftime('%Y%m%d'),
            end_date=end.strftime('%Y%m%d'),
            is_open='1'
        )
        return [
            date.fromisoformat(d[:4] + '-' + d[4:6] + '-' + d[6:8])
            for d in df['cal_date'].tolist()
        ]

    def load_bars(self, dt: date, symbols: set[str]) -> dict[str, DayBar]:
        """从 Tushare 加载行情数据"""
        bars = {}
        date_str = dt.strftime('%Y%m%d')

        for symbol in symbols:
            # Tushare 股票代码格式转换
            ts_code = self._convert_symbol(symbol)

            df = self.pro.daily(
                ts_code=ts_code,
                trade_date=date_str
            )

            if not df.empty:
                row = df.iloc[0]
                bars[symbol] = DayBar(
                    symbol=symbol,
                    date=dt,
                    open=row['open'],
                    high=row['high'],
                    low=row['low'],
                    close=row['close'],
                    volume=row['vol'] * 100,  # 手转股
                    amount=row['amount'] * 1000,  # 千元转元
                )

        return bars

    def _convert_symbol(self, symbol: str) -> str:
        """转换股票代码格式

        aquant: 000001.SZ
        tushare: 000001.SZ (相同)
        """
        return symbol
```

### 示例 3：从 AKShare 加载

```python
from datetime import date
from aquant.data.source import DataSource
from aquant.market.bar import DayBar
import akshare as ak
import pandas as pd

class AKShareDataSource(DataSource):
    def __init__(self):
        self._calendar_cache = None

    def load_calendar(self, start: date, end: date) -> list[date]:
        """从 AKShare 加载交易日历"""
        if self._calendar_cache is None:
            # 获取交易日历
            df = ak.tool_trade_date_hist_sina()
            self._calendar_cache = [
                pd.to_datetime(d).date()
                for d in df['trade_date'].tolist()
            ]

        return [
            d for d in self._calendar_cache
            if start <= d <= end
        ]

    def load_bars(self, dt: date, symbols: set[str]) -> dict[str, DayBar]:
        """从 AKShare 加载行情数据"""
        bars = {}
        date_str = dt.strftime('%Y%m%d')

        for symbol in symbols:
            try:
                # 获取历史行情
                df = ak.stock_zh_a_hist(
                    symbol=self._convert_symbol(symbol),
                    start_date=date_str,
                    end_date=date_str,
                    adjust="qfq"  # 前复权
                )

                if not df.empty:
                    row = df.iloc[0]
                    bars[symbol] = DayBar(
                        symbol=symbol,
                        date=dt,
                        open=row['开盘'],
                        high=row['最高'],
                        low=row['最低'],
                        close=row['收盘'],
                        volume=row['成交量'],
                        amount=row['成交额'],
                    )
            except Exception as e:
                # 跳过获取失败的股票
                continue

        return bars

    def _convert_symbol(self, symbol: str) -> str:
        """转换股票代码格式

        aquant: 000001.SZ, 600000.SH
        akshare: 000001, 600000
        """
        return symbol.split('.')[0]
```

## 数据缓存

为了提升性能，可以实现数据缓存：

```python
from datetime import date
from aquant.data.source import DataSource
from aquant.market.bar import DayBar
from functools import lru_cache

class CachedDataSource(DataSource):
    def __init__(self, underlying: DataSource):
        self.underlying = underlying
        self._bars_cache = {}

    @lru_cache(maxsize=1)
    def load_calendar(self, start: date, end: date) -> list[date]:
        """缓存交易日历"""
        return self.underlying.load_calendar(start, end)

    def load_bars(self, dt: date, symbols: set[str]) -> dict[str, DayBar]:
        """缓存行情数据"""
        # 将 set 转为 frozenset 用于缓存键
        cache_key = (dt, frozenset(symbols))

        if cache_key not in self._bars_cache:
            self._bars_cache[cache_key] = self.underlying.load_bars(dt, symbols)

        return self._bars_cache[cache_key]

# 使用
raw_source = TushareDataSource(token="your_token")
cached_source = CachedDataSource(raw_source)
```

## 数据预加载

批量预加载数据可以提升性能：

```python
from datetime import date
from aquant.data.source import DataSource
from aquant.market.bar import DayBar

class PreloadedDataSource(DataSource):
    def __init__(self, underlying: DataSource):
        self.underlying = underlying
        self._preloaded_bars = {}

    def preload(self, start: date, end: date, symbols: set[str]):
        """预加载数据"""
        calendar = self.underlying.load_calendar(start, end)

        for dt in calendar:
            self._preloaded_bars[dt] = self.underlying.load_bars(dt, symbols)

    def load_calendar(self, start: date, end: date) -> list[date]:
        return self.underlying.load_calendar(start, end)

    def load_bars(self, dt: date, symbols: set[str]) -> dict[str, DayBar]:
        """从预加载的数据中读取"""
        if dt in self._preloaded_bars:
            return {
                s: bar for s, bar in self._preloaded_bars[dt].items()
                if s in symbols
            }
        return self.underlying.load_bars(dt, symbols)

# 使用
source = PreloadedDataSource(TushareDataSource(token="your_token"))
source.preload(
    start=date(2023, 1, 1),
    end=date(2023, 12, 31),
    symbols={"000001.SZ", "600000.SH"}
)
```

## 数据质量检查

在加载数据后进行质量检查：

```python
from datetime import date
from aquant.data.source import DataSource
from aquant.market.bar import DayBar
import structlog

logger = structlog.get_logger()

class ValidatedDataSource(DataSource):
    def __init__(self, underlying: DataSource):
        self.underlying = underlying

    def load_calendar(self, start: date, end: date) -> list[date]:
        return self.underlying.load_calendar(start, end)

    def load_bars(self, dt: date, symbols: set[str]) -> dict[str, DayBar]:
        bars = self.underlying.load_bars(dt, symbols)

        # 检查数据质量
        for symbol, bar in bars.items():
            if not self._is_valid(bar):
                logger.warning(
                    "无效数据",
                    symbol=symbol,
                    date=dt,
                    bar=bar
                )
                # 移除无效数据
                del bars[symbol]

        return bars

    def _is_valid(self, bar: DayBar) -> bool:
        """检查 DayBar 是否有效"""
        # 价格必须为正
        if bar.open <= 0 or bar.close <= 0:
            return False

        # 最高价 >= 最低价
        if bar.high < bar.low:
            return False

        # 最高价 >= 开盘价/收盘价
        if bar.high < max(bar.open, bar.close):
            return False

        # 最低价 <= 开盘价/收盘价
        if bar.low > min(bar.open, bar.close):
            return False

        # 成交量必须为正
        if bar.volume < 0:
            return False

        return True
```

## 数据归一化

统一不同数据源的格式：

```python
from datetime import date
from aquant.data.source import DataSource
from aquant.market.bar import DayBar, AssetType

class NormalizedDataSource(DataSource):
    """归一化数据源，统一股票代码格式"""

    def __init__(self, underlying: DataSource, format: str = "wind"):
        self.underlying = underlying
        self.format = format  # "wind", "tushare", "akshare"

    def load_calendar(self, start: date, end: date) -> list[date]:
        return self.underlying.load_calendar(start, end)

    def load_bars(self, dt: date, symbols: set[str]) -> dict[str, DayBar]:
        # 转换股票代码格式
        converted_symbols = {self._convert_to_source(s) for s in symbols}

        # 加载数据
        bars = self.underlying.load_bars(dt, converted_symbols)

        # 转回标准格式
        normalized_bars = {}
        for source_symbol, bar in bars.items():
            standard_symbol = self._convert_to_standard(source_symbol)
            normalized_bars[standard_symbol] = DayBar(
                symbol=standard_symbol,
                date=bar.date,
                open=bar.open,
                high=bar.high,
                low=bar.low,
                close=bar.close,
                volume=bar.volume,
                amount=bar.amount,
                asset_type=bar.asset_type,
            )

        return normalized_bars

    def _convert_to_source(self, symbol: str) -> str:
        """标准格式 -> 数据源格式"""
        if self.format == "akshare":
            return symbol.split('.')[0]  # 000001.SZ -> 000001
        return symbol

    def _convert_to_standard(self, symbol: str) -> str:
        """数据源格式 -> 标准格式"""
        if self.format == "akshare":
            # 根据代码推断交易所
            if symbol.startswith('6'):
                return f"{symbol}.SH"
            else:
                return f"{symbol}.SZ"
        return symbol
```

## 最佳实践

### 1. 错误处理

```python
def load_bars(self, dt: date, symbols: set[str]) -> dict[str, DayBar]:
    bars = {}
    for symbol in symbols:
        try:
            bar = self._fetch_bar(symbol, dt)
            bars[symbol] = bar
        except Exception as e:
            logger.warning("加载数据失败", symbol=symbol, date=dt, error=str(e))
            # 跳过失败的股票，继续处理其他股票
    return bars
```

### 2. 性能优化

- 批量加载数据，减少 API 调用次数
- 使用缓存避免重复加载
- 对于大规模回测，使用预加载机制

### 3. 数据版本

```python
class VersionedDataSource(DataSource):
    def __init__(self, version: str = "v1"):
        self.version = version

    def load_bars(self, dt: date, symbols: set[str]) -> dict[str, DayBar]:
        # 根据版本加载不同的数据
        if self.version == "v1":
            return self._load_bars_v1(dt, symbols)
        elif self.version == "v2":
            return self._load_bars_v2(dt, symbols)
```

## 下一步

- [策略开发](strategy.md) - 使用自定义数据源开发策略
- [风控管理](risk-management.md) - 添加风控规则
- [实盘交易](live-trading.md) - 在实盘中使用数据源
