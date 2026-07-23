"""基于 CSV 文件的 DataSource 实现。

CSV 文件格式要求：
- 文件名格式：YYYYMMDD.csv（如 20240101.csv）
- 必需列：symbol, date, open, high, low, close, volume
- 可选列：up_limit, down_limit, is_halted

示例::

    data_source = CSVDataSource(data_dir="./data/daily")
    bars = data_source.load_bars(date(2024, 1, 2), {"000001.SZ", "600000.SH"})
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

import polars as pl

from aquant.data.source import DataSource
from aquant.market.bar import DayBar


if TYPE_CHECKING:
    from datetime import date


class CSVDataSource(DataSource):
    """从 CSV 文件读取行情数据的数据源。

    目录结构::

        data_dir/
        ├── 20240101.csv
        ├── 20240102.csv
        └── ...

    CSV 格式示例::

        symbol,date,open,high,low,close,volume,up_limit,down_limit,is_halted
        000001.SZ,2024-01-02,10.0,10.5,9.8,10.2,1000000,11.0,9.0,False
        600000.SH,2024-01-02,20.0,20.8,19.5,20.3,2000000,22.0,18.0,False
    """

    def __init__(self, data_dir: str):
        """初始化 CSV 数据源。

        参数
        ----
        data_dir : str
            CSV 文件所在目录路径
        """
        self.data_dir = Path(data_dir)
        if not self.data_dir.exists():
            raise ValueError(f"数据目录不存在: {data_dir}")

        # 缓存：日期 -> DataFrame
        self._cache: dict[date, pl.DataFrame] = {}

    def load_calendar(self, start: date, end: date) -> list[date]:
        """加载交易日历。

        从目录中的 CSV 文件名推断交易日。

        参数
        ----
        start : date
            起始日期
        end : date
            结束日期

        返回
        ----
        list[date]
            交易日列表（升序）
        """
        from datetime import datetime

        trading_days = []

        # 遍历目录中的 CSV 文件
        for csv_file in sorted(self.data_dir.glob("*.csv")):
            # 从文件名解析日期（如 20240102.csv）
            date_str = csv_file.stem
            try:
                file_date = datetime.strptime(date_str, "%Y%m%d").date()
                if start <= file_date <= end:
                    trading_days.append(file_date)
            except ValueError:
                # 跳过无法解析的文件名
                continue

        return sorted(trading_days)

    def _load_date_csv(self, dt: date) -> pl.DataFrame | None:
        """加载指定日期的 CSV 文件。

        参数
        ----
        dt : date
            交易日期

        返回
        ----
        pl.DataFrame | None
            行情数据，文件不存在则返回 None
        """
        # 检查缓存
        if dt in self._cache:
            return self._cache[dt]

        # 构造文件路径
        csv_file = self.data_dir / f"{dt.strftime('%Y%m%d')}.csv"

        if not csv_file.exists():
            return None

        try:
            # 读取 CSV
            df = pl.read_csv(csv_file)

            # 验证必需列
            required_cols = {"symbol", "date", "open", "high", "low", "close", "volume"}
            missing_cols = required_cols - set(df.columns)
            if missing_cols:
                raise ValueError(f"CSV 文件缺少必需列: {missing_cols}")

            # 类型转换
            df = df.with_columns(pl.col("date").str.strptime(pl.Date, "%Y-%m-%d").alias("date"))

            # 处理可选列
            if "up_limit" not in df.columns:
                df = df.with_columns(pl.lit(None).cast(pl.Float64).alias("up_limit"))
            if "down_limit" not in df.columns:
                df = df.with_columns(pl.lit(None).cast(pl.Float64).alias("down_limit"))
            df = df.with_columns(pl.lit(False).alias("is_halted")) if "is_halted" not in df.columns else df.with_columns(pl.col("is_halted").cast(pl.Boolean))

            # 缓存
            self._cache[dt] = df
            return df

        except Exception as e:
            raise ValueError(f"读取 CSV 文件失败 {csv_file}: {e}") from e

    def load_bars(self, dt: date, symbols: set[str]) -> dict[str, DayBar]:
        """加载指定日期的行情数据。

        参数
        ----
        dt : date
            交易日期
        symbols : set[str]
            股票代码集合

        返回
        ----
        dict[str, DayBar]
            股票代码 -> 行情数据的字典
        """
        df = self._load_date_csv(dt)
        if df is None:
            return {}

        # 筛选指定股票
        df_filtered = df.filter(pl.col("symbol").is_in(symbols))

        result: dict[str, DayBar] = {}
        for row in df_filtered.iter_rows(named=True):
            sym = row["symbol"]
            result[sym] = DayBar(
                symbol=sym,
                date=row["date"],
                open=float(row["open"]),
                close=float(row["close"]),
                high=float(row["high"]),
                low=float(row["low"]),
                volume=float(row["volume"]),
                up_limit=float(row["up_limit"]) if row["up_limit"] is not None else float(row["close"]) * 1.1,
                down_limit=float(row["down_limit"]) if row["down_limit"] is not None else float(row["close"]) * 0.9,
                is_halted=bool(row["is_halted"]),
            )

        return result

    def load_adjustments(self, start: date, end: date) -> list:
        """加载复权数据。

        CSV 数据源不包含复权数据，返回空列表。

        参数
        ----
        start : date
            起始日期
        end : date
            结束日期

        返回
        ----
        list
            空列表
        """
        return []

    def load_delisted(self, start: date, end: date) -> dict[date, list[str]]:
        """加载退市数据。

        CSV 数据源不包含退市数据，返回空字典。

        参数
        ----
        start : date
            起始日期
        end : date
            结束日期

        返回
        ----
        dict[date, list[str]]
            空字典
        """
        return {}


def create_sample_csv(data_dir: str, start: date, end: date, symbols: list[str]) -> None:
    """创建示例 CSV 文件（用于测试）。

    参数
    ----
    data_dir : str
        输出目录
    start : date
        起始日期
    end : date
        结束日期
    symbols : list[str]
        股票代码列表
    """
    import random
    from datetime import timedelta

    data_path = Path(data_dir)
    data_path.mkdir(parents=True, exist_ok=True)

    current = start
    while current <= end:
        rows = []
        for symbol in symbols:
            # 生成随机价格
            base_price = 10.0 + random.random() * 90.0
            open_price = base_price * (1 + random.uniform(-0.02, 0.02))
            close_price = base_price * (1 + random.uniform(-0.02, 0.02))
            high_price = max(open_price, close_price) * (1 + random.uniform(0, 0.03))
            low_price = min(open_price, close_price) * (1 - random.uniform(0, 0.03))
            volume = random.randint(100000, 10000000)

            rows.append(
                {
                    "symbol": symbol,
                    "date": current.strftime("%Y-%m-%d"),
                    "open": round(open_price, 2),
                    "high": round(high_price, 2),
                    "low": round(low_price, 2),
                    "close": round(close_price, 2),
                    "volume": volume,
                    "up_limit": round(base_price * 1.1, 2),
                    "down_limit": round(base_price * 0.9, 2),
                    "is_halted": False,
                }
            )

        # 写入 CSV
        df = pl.DataFrame(rows)
        csv_file = data_path / f"{current.strftime('%Y%m%d')}.csv"
        df.write_csv(csv_file)

        # 跳过周末（简化处理）
        current += timedelta(days=1)
        while current.weekday() >= 5:  # 5=周六, 6=周日
            current += timedelta(days=1)
