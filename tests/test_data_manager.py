"""DataManager 单元测试"""

from datetime import date, timedelta
from unittest.mock import Mock

import pytest

from aquant.data.manager import DataManager
from aquant.market.bar import DayBar


class TestDataManager:
    """测试 DataManager 的缓存和数据加载功能"""

    @pytest.fixture
    def mock_source(self):
        """创建 mock 数据源"""
        source = Mock()

        def mock_fetch(dt: date, symbols: set[str]) -> dict[str, DayBar]:
            """模拟数据源返回"""
            result = {}
            for symbol in symbols:
                # 为每个标的生成不同的价格
                price = 10.0 if symbol == "000001.SZ" else 20.0
                result[symbol] = DayBar(symbol=symbol, date=dt, open=price, high=price * 1.1, low=price * 0.9, close=price, volume=1000000, up_limit=price * 1.1, down_limit=price * 0.9, is_halted=False)
            return result

        def mock_calendar(start: date, end: date) -> list[date]:
            """模拟交易日历"""

            dates = []
            current = start
            while current <= end:
                dates.append(current)
                current += timedelta(days=1)
            return dates

        source.load_bars = Mock(side_effect=mock_fetch)
        source.load_calendar = Mock(side_effect=mock_calendar)
        return source

    @pytest.fixture
    def manager(self, mock_source):
        """创建 DataManager 实例"""
        return DataManager(primary_source=mock_source)

    def test_load_bars_first_time(self, manager, mock_source):
        """测试首次加载数据"""
        dt = date(2024, 1, 1)
        symbols = {"000001.SZ", "600000.SH"}

        bars = manager.load_bars(dt, symbols)

        # 验证返回的数据
        assert len(bars) == 2
        assert "000001.SZ" in bars
        assert "600000.SH" in bars
        assert bars["000001.SZ"].close == 10.0
        assert bars["600000.SH"].close == 20.0

        # 验证调用了数据源
        mock_source.load_bars.assert_called_once_with(dt, symbols)

    def test_load_bars_cached(self, manager, mock_source):
        """测试缓存命中"""
        dt = date(2024, 1, 1)
        symbols = {"000001.SZ"}

        # 首次加载
        bars1 = manager.load_bars(dt, symbols)
        # 再次加载相同数据
        bars2 = manager.load_bars(dt, symbols)

        # 两次返回结果相同
        assert bars1 == bars2
        # 数据源只调用一次
        assert mock_source.load_bars.call_count == 1

    def test_load_bars_different_dates(self, manager, mock_source):
        """测试不同日期分别缓存"""
        symbols = {"000001.SZ"}

        manager.load_bars(date(2024, 1, 1), symbols)
        manager.load_bars(date(2024, 1, 2), symbols)

        # 不同日期，调用两次数据源
        assert mock_source.load_bars.call_count == 2

    def test_load_bars_different_symbols(self, manager, mock_source):
        """测试不同标的分别缓存"""
        dt = date(2024, 1, 1)

        manager.load_bars(dt, {"000001.SZ"})
        manager.load_bars(dt, {"600000.SH"})

        # 不同标的集合，调用两次数据源
        assert mock_source.load_bars.call_count == 2

    def test_load_bars_subset_cached(self, manager, mock_source):
        """测试加载标的子集时利用缓存"""
        dt = date(2024, 1, 1)

        # 先加载多个标的
        manager.load_bars(dt, {"000001.SZ", "600000.SH"})
        # 再加载其中一个标的（需要重新调用，因为 frozenset 不同）
        bars = manager.load_bars(dt, {"000001.SZ"})

        # 由于缓存键是 (date, frozenset)，两次调用的 frozenset 不同，所以会调用 2 次
        assert mock_source.load_bars.call_count == 2
        assert len(bars) == 1
        assert "000001.SZ" in bars

    def test_preload_range(self, manager, mock_source):
        """测试预加载日期区间"""
        start = date(2024, 1, 1)
        end = date(2024, 1, 5)
        symbols = {"000001.SZ", "600000.SH"}

        manager.preload_range(start, end, symbols)

        # 应该为每个交易日调用一次数据源（5 天）
        assert mock_source.load_bars.call_count == 5

        # 验证缓存已生效
        mock_source.load_bars.reset_mock()
        bars = manager.load_bars(date(2024, 1, 3), symbols)
        # 不应再调用数据源
        assert mock_source.load_bars.call_count == 0
        assert len(bars) == 2

    def test_preload_single_day(self, manager, mock_source):
        """测试预加载单日（start == end）"""
        dt = date(2024, 1, 1)
        symbols = {"000001.SZ"}

        manager.preload_range(dt, dt, symbols)

        # 只调用一次
        assert mock_source.load_bars.call_count == 1

    def test_cache_info(self, manager):
        """测试缓存信息输出"""
        dt = date(2024, 1, 1)
        symbols = {"000001.SZ"}

        # 首次加载（缓存未命中）
        manager.load_bars(dt, symbols)
        info1 = manager.cache_info()
        assert "hits=0" in info1
        assert "misses=1" in info1

        # 再次加载（缓存命中）
        manager.load_bars(dt, symbols)
        info2 = manager.cache_info()
        assert "hits=1" in info2
        assert "misses=1" in info2

    def test_lru_eviction(self, mock_source):
        """测试 LRU 缓存淘汰"""
        # 创建只能缓存 2 个条目的 DataManager
        manager = DataManager(primary_source=mock_source, cache_size=2)

        # 加载 3 个不同的日期
        manager.load_bars(date(2024, 1, 1), {"000001.SZ"})
        manager.load_bars(date(2024, 1, 2), {"000001.SZ"})
        manager.load_bars(date(2024, 1, 3), {"000001.SZ"})

        # 应该调用 3 次数据源
        assert mock_source.load_bars.call_count == 3

        # 重新加载第 1 天（应该被淘汰了，需要重新加载）
        mock_source.load_bars.reset_mock()
        manager.load_bars(date(2024, 1, 1), {"000001.SZ"})
        assert mock_source.load_bars.call_count == 1

        # 重新加载第 3 天（最近使用，应该还在缓存中）
        mock_source.load_bars.reset_mock()
        manager.load_bars(date(2024, 1, 3), {"000001.SZ"})
        assert mock_source.load_bars.call_count == 0

    def test_empty_symbols(self, manager, mock_source):
        """测试空标的集合"""
        dt = date(2024, 1, 1)
        bars = manager.load_bars(dt, set())

        # 返回空字典
        assert len(bars) == 0
        # 仍会调用一次数据源（传入空集合）
        assert mock_source.load_bars.call_count == 1

    def test_preload_backwards_range(self, manager, mock_source):
        """测试预加载逆序日期区间"""
        start = date(2024, 1, 5)
        end = date(2024, 1, 1)
        symbols = {"000001.SZ"}

        manager.preload_range(start, end, symbols)

        # 日期逆序时不应加载任何数据
        assert mock_source.load_bars.call_count == 0
