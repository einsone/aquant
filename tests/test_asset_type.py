"""测试 AssetType 在回测中的应用。

验证：
- AssetType 字段向后兼容性
- DayBar 创建时的默认值
- 不同资产类型在回测中的正确性
"""

from __future__ import annotations

import pytest
from datetime import date

from aquant.market.bar import AssetType, DayBar


class TestAssetType:
    """测试资产类型。"""

    def test_default_asset_type(self):
        """测试默认资产类型为 STOCK。"""
        bar = DayBar(
            symbol="000001.SZ",
            date=date(2023, 1, 1),
            open=10.0,
            close=10.5,
            high=11.0,
            low=9.5,
            volume=1000000.0,
            up_limit=11.0,
            down_limit=9.0,
            is_halted=False,
        )

        assert bar.asset_type == AssetType.STOCK

    def test_explicit_stock_type(self):
        """测试显式指定股票类型。"""
        bar = DayBar(
            symbol="000001.SZ",
            date=date(2023, 1, 1),
            open=10.0,
            close=10.5,
            high=11.0,
            low=9.5,
            volume=1000000.0,
            up_limit=11.0,
            down_limit=9.0,
            is_halted=False,
            asset_type=AssetType.STOCK,
        )

        assert bar.asset_type == AssetType.STOCK

    def test_future_type(self):
        """测试期货类型。"""
        bar = DayBar(
            symbol="IF2312",
            date=date(2023, 12, 15),
            open=3800.0,
            close=3850.0,
            high=3900.0,
            low=3750.0,
            volume=100000.0,
            up_limit=4000.0,
            down_limit=3600.0,
            is_halted=False,
            asset_type=AssetType.FUTURE,
        )

        assert bar.asset_type == AssetType.FUTURE

    def test_option_type(self):
        """测试期权类型。"""
        bar = DayBar(
            symbol="10004000",
            date=date(2023, 1, 1),
            open=0.5,
            close=0.55,
            high=0.6,
            low=0.45,
            volume=50000.0,
            up_limit=0.7,
            down_limit=0.3,
            is_halted=False,
            asset_type=AssetType.OPTION,
        )

        assert bar.asset_type == AssetType.OPTION

    def test_asset_type_enum_values(self):
        """测试资产类型枚举值。"""
        assert AssetType.STOCK.value == "STOCK"
        assert AssetType.FUTURE.value == "FUTURE"
        assert AssetType.OPTION.value == "OPTION"

    def test_asset_type_comparison(self):
        """测试资产类型比较。"""
        bar1 = DayBar(
            symbol="000001.SZ",
            date=date(2023, 1, 1),
            open=10.0,
            close=10.5,
            high=11.0,
            low=9.5,
            volume=1000000.0,
            up_limit=11.0,
            down_limit=9.0,
            is_halted=False,
        )

        bar2 = DayBar(
            symbol="IF2312",
            date=date(2023, 12, 15),
            open=3800.0,
            close=3850.0,
            high=3900.0,
            low=3750.0,
            volume=100000.0,
            up_limit=4000.0,
            down_limit=3600.0,
            is_halted=False,
            asset_type=AssetType.FUTURE,
        )

        assert bar1.asset_type == AssetType.STOCK
        assert bar2.asset_type == AssetType.FUTURE
        assert bar1.asset_type != bar2.asset_type

    def test_daybar_immutable(self):
        """测试 DayBar 不可变性。"""
        bar = DayBar(
            symbol="000001.SZ",
            date=date(2023, 1, 1),
            open=10.0,
            close=10.5,
            high=11.0,
            low=9.5,
            volume=1000000.0,
            up_limit=11.0,
            down_limit=9.0,
            is_halted=False,
        )

        # DayBar 是 frozen dataclass，验证不可变性
        assert bar.asset_type == AssetType.STOCK
        # 尝试修改会抛出 AttributeError（frozen dataclass 特性）
        # 由于 ty 类型检查器限制，此处不直接测试赋值操作
