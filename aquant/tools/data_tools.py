"""数据工具

提供数据下载、清洗、转换等实用工具。
"""

from datetime import date
from pathlib import Path

import pandas as pd
import structlog


logger = structlog.get_logger()


class DataDownloader:
    """数据下载器

    支持从多个数据源下载股票数据并缓存到本地。
    """

    def __init__(self, cache_dir: str = ".aquant_cache"):
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(exist_ok=True)

    def download_stock_list(self, source: str = "synthetic") -> list[str]:
        """下载股票列表

        Args:
            source: 数据源（synthetic, tushare, akshare）

        Returns:
            股票代码列表
        """
        cache_file = self.cache_dir / f"stock_list_{source}.txt"

        # 检查缓存
        if cache_file.exists():
            with open(cache_file, encoding="utf-8") as f:
                symbols = [line.strip() for line in f if line.strip()]
            logger.info("从缓存加载股票列表", count=len(symbols), source=source)
            return symbols

        # 下载数据
        if source == "synthetic":
            # 合成数据：常见的 A 股代码
            symbols = ["000001.SZ", "000002.SZ", "600000.SH", "600519.SH", "000858.SZ"]
        elif source == "tushare":
            try:
                import tushare as ts

                pro = ts.pro_api()
                df = pro.stock_basic(exchange="", list_status="L", fields="ts_code")
                symbols = df["ts_code"].tolist()
            except Exception as e:
                logger.error("Tushare 下载失败", error=str(e))
                return []
        elif source == "akshare":
            try:
                import akshare as ak

                df = ak.stock_info_a_code_name()
                # 转换代码格式
                symbols = []
                for code in df["code"]:
                    if code.startswith("6"):
                        symbols.append(f"{code}.SH")
                    else:
                        symbols.append(f"{code}.SZ")
            except Exception as e:
                logger.error("AKShare 下载失败", error=str(e))
                return []
        else:
            logger.error("不支持的数据源", source=source)
            return []

        # 缓存到本地
        with open(cache_file, "w", encoding="utf-8") as f:
            for symbol in symbols:
                f.write(f"{symbol}\n")

        logger.info("下载股票列表完成", count=len(symbols), source=source)
        return symbols

    def download_daily_bars(self, symbols: list[str], start_date: date, end_date: date, source: str = "synthetic") -> pd.DataFrame:
        """下载日线数据

        Args:
            symbols: 股票代码列表
            start_date: 开始日期
            end_date: 结束日期
            source: 数据源

        Returns:
            包含 OHLCV 的 DataFrame
        """
        cache_file = self.cache_dir / f"daily_{source}_{start_date.isoformat()}_{end_date.isoformat()}.parquet"

        # 检查缓存
        if cache_file.exists():
            df = pd.read_parquet(cache_file)
            logger.info("从缓存加载日线数据", rows=len(df), source=source)
            return df

        # 下载数据
        if source == "synthetic":
            from aquant.data.synthetic import SyntheticDataSource

            data_source = SyntheticDataSource()
            bars = data_source.get_bars(symbols, start_date, end_date)

            # 转换为 DataFrame
            records = []
            for bar in bars:
                records.append({"symbol": bar.symbol, "date": bar.date, "open": bar.open, "high": bar.high, "low": bar.low, "close": bar.close, "volume": bar.volume})
            df = pd.DataFrame(records)

        elif source == "tushare":
            # Tushare 实现
            logger.warning("Tushare 下载未实现")
            df = pd.DataFrame()

        elif source == "akshare":
            # AKShare 实现
            logger.warning("AKShare 下载未实现")
            df = pd.DataFrame()

        else:
            logger.error("不支持的数据源", source=source)
            return pd.DataFrame()

        # 缓存到本地
        if not df.empty:
            df.to_parquet(cache_file, index=False)
            logger.info("下载日线数据完成", rows=len(df), source=source)

        return df

    def clear_cache(self):
        """清空缓存"""
        import shutil

        if self.cache_dir.exists():
            shutil.rmtree(self.cache_dir)
            self.cache_dir.mkdir(exist_ok=True)
            logger.info("缓存已清空")


class DataCleaner:
    """数据清洗器"""

    @staticmethod
    def remove_outliers(df: pd.DataFrame, column: str, n_std: float = 3.0) -> pd.DataFrame:
        """移除异常值

        Args:
            df: 数据框
            column: 列名
            n_std: 标准差倍数

        Returns:
            清洗后的数据框
        """
        mean = df[column].mean()
        std = df[column].std()
        lower = mean - n_std * std
        upper = mean + n_std * std

        before = len(df)
        df = df[(df[column] >= lower) & (df[column] <= upper)]
        after = len(df)

        logger.info("移除异常值", column=column, removed=before - after)
        return df

    @staticmethod
    def fill_missing_dates(df: pd.DataFrame, date_column: str = "date") -> pd.DataFrame:
        """填充缺失日期

        Args:
            df: 数据框
            date_column: 日期列名

        Returns:
            填充后的数据框
        """
        df[date_column] = pd.to_datetime(df[date_column])
        df = df.set_index(date_column)

        # 按股票分组填充
        if "symbol" in df.columns:
            result = []
            for symbol, group in df.groupby("symbol"):
                # 重采样并前向填充
                filled = group.resample("D").ffill()
                filled["symbol"] = symbol
                result.append(filled)
            df = pd.concat(result)
        else:
            df = df.resample("D").ffill()

        return df.reset_index()

    @staticmethod
    def normalize_symbols(df: pd.DataFrame, symbol_column: str = "symbol") -> pd.DataFrame:
        """标准化股票代码格式

        Args:
            df: 数据框
            symbol_column: 股票代码列名

        Returns:
            标准化后的数据框
        """

        def normalize(symbol: str) -> str:
            symbol = symbol.upper().strip()
            # 统一为 6 位数字 + 后缀格式
            if len(symbol) == 6 and symbol.isdigit():
                # 根据首位判断市场
                if symbol.startswith("6"):
                    return f"{symbol}.SH"
                else:
                    return f"{symbol}.SZ"
            return symbol

        df[symbol_column] = df[symbol_column].apply(normalize)
        return df


class DataConverter:
    """数据转换器"""

    @staticmethod
    def to_aquant_format(df: pd.DataFrame) -> list:
        """转换为 aquant DayBar 格式

        Args:
            df: 包含 OHLCV 的 DataFrame

        Returns:
            DayBar 列表
        """
        from aquant.data.bars import DayBar

        bars = []
        for _, row in df.iterrows():
            bar = DayBar(
                symbol=row["symbol"],
                date=pd.to_datetime(row["date"]).date(),
                open=float(row["open"]),
                high=float(row["high"]),
                low=float(row["low"]),
                close=float(row["close"]),
                volume=int(row["volume"]),
                up_limit=float(row.get("up_limit", row["close"] * 1.1)),
                down_limit=float(row.get("down_limit", row["close"] * 0.9)),
                is_halted=bool(row.get("is_halted", False)),
            )
            bars.append(bar)

        return bars

    @staticmethod
    def from_csv(csv_path: str, symbol_column: str = "symbol", date_column: str = "date") -> pd.DataFrame:
        """从 CSV 加载数据

        Args:
            csv_path: CSV 文件路径
            symbol_column: 股票代码列名
            date_column: 日期列名

        Returns:
            DataFrame
        """
        df = pd.read_csv(csv_path)
        df[date_column] = pd.to_datetime(df[date_column])
        return df

    @staticmethod
    def to_csv(df: pd.DataFrame, csv_path: str):
        """保存为 CSV

        Args:
            df: 数据框
            csv_path: 输出路径
        """
        df.to_csv(csv_path, index=False, encoding="utf-8")
        logger.info("数据已保存", path=csv_path, rows=len(df))
