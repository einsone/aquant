# 数据源

数据源抽象层，支持自定义数据源。

## DataSource

::: aquant.data.source.DataSource
    options:
      show_root_heading: true
      show_source: true
      members:
        - load_calendar
        - load_bars
        - load_adjustments
        - load_delisted

## DayBar

::: aquant.market.bar.DayBar
    options:
      show_root_heading: true
      show_source: true

## AssetType

::: aquant.market.bar.AssetType
    options:
      show_root_heading: true
      show_source: true

## ALDSDataSource

::: aquant.data.alds.ALDSDataSource
    options:
      show_root_heading: true
      show_source: true

## CSVDataSource

::: aquant.data.csv.CSVDataSource
    options:
      show_root_heading: true
      show_source: true

## 自定义数据源示例

```python
from datetime import date
from aquant.data.source import DataSource
from aquant.market.bar import DayBar

class MyDataSource(DataSource):
    """自定义数据源"""
    
    def load_calendar(self, start: date, end: date) -> list[date]:
        """加载交易日历"""
        # 从数据库查询交易日
        return trading_days
    
    def load_bars(self, dt: date, symbols: set[str]) -> dict[str, DayBar]:
        """加载行情数据"""
        # 从数据库查询行情
        bars = {}
        for symbol in symbols:
            bars[symbol] = DayBar(...)
        return bars
    
    def load_adjustments(self, start: date, end: date):
        """加载企业行动（分红、送转）"""
        return []
    
    def load_delisted(self, start: date, end: date):
        """加载退市信息"""
        return {}
```
