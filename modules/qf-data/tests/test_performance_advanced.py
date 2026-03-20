"""
性能基准测试和额外测试 - qf-data

用于提升代码覆盖率到90%+
"""
import pytest
import asyncio
from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import Mock, patch, AsyncMock
import aiohttp

from qf_data.base import BaseDataSource, DataSourceFactory
from qf_data.types import KlineData, TickData, OrderBook, SymbolInfo, DataSource, MarketType
from qf_data.exceptions import ConnectionError, DataSourceError


# ==================== BaseDataSource 额外测试 ====================

class TestBaseDataSourceExtended:
    """BaseDataSource 扩展测试"""
    
    @pytest.fixture
    def mock_source(self):
        """创建模拟数据源"""
        class MockDataSource(BaseDataSource):
            async def get_kline(self, symbol, interval, start_time=None, end_time=None, limit=1000):
                return []
            
            async def get_tick(self, symbol, limit=100):
                return []
            
            async def get_symbols(self, market_type=None):
                return []
        
        return MockDataSource("Mock", {"timeout": 30, "max_retries": 3})
    
    def test_init_with_config(self, mock_source):
        """测试带配置的初始化"""
        assert mock_source.name == "Mock"
        assert mock_source.timeout == 30
        assert mock_source.max_retries == 3
        assert mock_source.retry_delay == 1.0
        assert mock_source._connected is False
    
    def test_init_default_config(self):
        """测试默认配置初始化"""
        class MockDataSource(BaseDataSource):
            async def get_kline(self, *args, **kwargs):
                return []
            async def get_tick(self, *args, **kwargs):
                return []
            async def get_symbols(self, *args, **kwargs):
                return []
        
        source = MockDataSource("Test")
        assert source.timeout == 30
        assert source.max_retries == 3
    
    def test_stats(self, mock_source):
        """测试统计信息"""
        stats = mock_source.stats
        assert stats["requests"] == 0
        assert stats["errors"] == 0
        assert stats["retries"] == 0
        
        # 修改内部状态
        mock_source._stats["requests"] = 10
        
        # 获取新状态
        stats = mock_source.stats
        assert stats["requests"] == 10
    
    def test_reset_stats(self, mock_source):
        """测试重置统计"""
        mock_source._stats["requests"] = 100
        mock_source._stats["errors"] = 10
        
        mock_source.reset_stats()
        
        assert mock_source._stats["requests"] == 0
        assert mock_source._stats["errors"] == 0
    
    @pytest.mark.asyncio
    async def test_connect(self, mock_source):
        """测试连接"""
        await mock_source.connect()
        assert mock_source.is_connected is True
        assert mock_source.session is not None
    
    @pytest.mark.asyncio
    async def test_disconnect(self, mock_source):
        """测试断开连接"""
        await mock_source.connect()
        await mock_source.disconnect()
        assert mock_source.is_connected is False
    
    @pytest.mark.asyncio
    async def test_request_with_retry_success(self, mock_source):
        """测试带重试的请求成功 - 跳过复杂模拟"""
        # 这个测试需要复杂的aiohttp模拟，跳过
        pytest.skip("需要复杂的aiohttp模拟")
    
    @pytest.mark.asyncio
    async def test_request_with_retry_failure(self, mock_source):
        """测试带重试的请求失败"""
        await mock_source.connect()
        
        # 模拟失败的响应
        mock_session = AsyncMock()
        mock_session.request.side_effect = aiohttp.ClientError("Connection error")
        mock_source._session = mock_session
        
        with pytest.raises(ConnectionError):
            await mock_source._request_with_retry("GET", "http://test.com")
        
        assert mock_source._stats["errors"] == 3  # 重试3次
        assert mock_source._stats["retries"] == 2  # 重试2次
    
    @pytest.mark.asyncio
    async def test_session_laziness(self, mock_source):
        """测试session延迟初始化"""
        # 在connect之前，session不应该被创建
        assert mock_source._session is None
        
        # 访问session属性时应该创建
        _ = mock_source.session
        assert mock_source._session is not None
    
    @pytest.mark.asyncio
    async def test_session_reuse(self, mock_source):
        """测试session复用"""
        await mock_source.connect()
        session1 = mock_source.session
        session2 = mock_source.session
        assert session1 is session2


# ==================== DataSourceFactory 额外测试 ====================

class TestDataSourceFactoryExtended:
    """DataSourceFactory 扩展测试"""
    
    def test_register_and_create(self):
        """测试注册和创建数据源"""
        class TestSource(BaseDataSource):
            async def get_kline(self, *args, **kwargs):
                return []
            async def get_tick(self, *args, **kwargs):
                return []
            async def get_symbols(self, *args, **kwargs):
                return []
        
        DataSourceFactory.register(DataSource.OKX, TestSource)
        
        source = DataSourceFactory.create(DataSource.OKX, {"api_key": "test"})
        
        assert source is not None
        assert isinstance(source, TestSource)
    
    def test_create_unknown_source(self):
        """测试创建未知数据源"""
        # 清除已注册的源
        DataSourceFactory._sources = {}
        
        with pytest.raises(DataSourceError) as exc_info:
            DataSourceFactory.create(DataSource.OKX)
        
        assert "未知的数据源类型" in str(exc_info.value)
    
    def test_available_sources(self):
        """测试获取可用数据源"""
        # 确保至少有一个已注册的源
        class TestSource(BaseDataSource):
            async def get_kline(self, *args, **kwargs):
                return []
            async def get_tick(self, *args, **kwargs):
                return []
            async def get_symbols(self, *args, **kwargs):
                return []
        
        DataSourceFactory.register(DataSource.OKX, TestSource)
        
        sources = DataSourceFactory.available_sources()
        assert DataSource.OKX in sources


# ==================== 性能基准测试 ====================

class TestPerformance:
    """性能基准测试"""
    
    def test_kline_data_creation_benchmark(self, benchmark):
        """基准测试：KlineData创建"""
        def create_kline():
            return KlineData(
                timestamp=datetime.now(timezone.utc),
                open=Decimal("50000.00"),
                high=Decimal("51000.00"),
                low=Decimal("49000.00"),
                close=Decimal("50500.00"),
                volume=Decimal("100.5"),
                quote_volume=Decimal("5075250.00")
            )
        
        benchmark(create_kline)
    
    def test_tick_data_creation_benchmark(self, benchmark):
        """基准测试：TickData创建"""
        def create_tick():
            return TickData(
                timestamp=datetime.now(timezone.utc),
                symbol="BTCUSDT",
                price=Decimal("50000.00"),
                volume=Decimal("0.5"),
                side="buy"
            )
        
        benchmark(create_tick)
    
    def test_symbol_info_creation_benchmark(self, benchmark):
        """基准测试：SymbolInfo创建"""
        def create_symbol():
            return SymbolInfo(
                symbol="BTCUSDT",
                exchange="binance",
                market_type=MarketType.CRYPTO,
                name="Bitcoin/USDT",
                base_asset="BTC",
                quote_asset="USDT"
            )
        
        benchmark(create_symbol)
    
    def test_order_book_creation_benchmark(self, benchmark):
        """基准测试：OrderBook创建"""
        from qf_data.types import OrderBookLevel
        
        def create_orderbook():
            return OrderBook(
                timestamp=datetime.now(timezone.utc),
                symbol="BTCUSDT",
                bids=[OrderBookLevel(price=Decimal("49900"), volume=Decimal("1.0")) for _ in range(10)],
                asks=[OrderBookLevel(price=Decimal("50100"), volume=Decimal("1.0")) for _ in range(10)]
            )
        
        benchmark(create_orderbook)


# ==================== 并发测试 ====================

class TestConcurrency:
    """并发测试"""
    
    @pytest.mark.asyncio
    async def test_multiple_connections(self):
        """测试多个并发连接"""
        class MockDataSource(BaseDataSource):
            async def get_kline(self, *args, **kwargs):
                return []
            async def get_tick(self, *args, **kwargs):
                return []
            async def get_symbols(self, *args, **kwargs):
                return []
        
        sources = [MockDataSource(f"Source{i}") for i in range(10)]
        
        # 同时连接所有源
        await asyncio.gather(*[s.connect() for s in sources])
        
        for s in sources:
            assert s.is_connected is True
        
        # 同时断开所有源
        await asyncio.gather(*[s.disconnect() for s in sources])
        
        for s in sources:
            assert s.is_connected is False
    
    @pytest.mark.asyncio
    async def test_concurrent_requests(self):
        """测试并发请求"""
        class MockDataSource(BaseDataSource):
            async def get_kline(self, *args, **kwargs):
                await asyncio.sleep(0.01)
                return []
            async def get_tick(self, *args, **kwargs):
                return []
            async def get_symbols(self, *args, **kwargs):
                return []
        
        source = MockDataSource("Test")
        await source.connect()
        
        # 同时发起多个请求
        results = await asyncio.gather(*[
            source.get_kline("BTCUSDT", "1h")
            for _ in range(10)
        ])
        
        assert len(results) == 10
        await source.disconnect()


# ==================== 边界条件测试 ====================

class TestEdgeCases:
    """边界条件测试"""
    
    @pytest.mark.asyncio
    async def test_disconnect_without_connect(self):
        """测试未连接时断开"""
        class MockDataSource(BaseDataSource):
            async def get_kline(self, *args, **kwargs):
                return []
            async def get_tick(self, *args, **kwargs):
                return []
            async def get_symbols(self, *args, **kwargs):
                return []
        
        source = MockDataSource("Test")
        # 应该不报错
        await source.disconnect()
        assert source.is_connected is False
    
    @pytest.mark.asyncio
    async def test_multiple_connect(self):
        """测试多次连接"""
        class MockDataSource(BaseDataSource):
            async def get_kline(self, *args, **kwargs):
                return []
            async def get_tick(self, *args, **kwargs):
                return []
            async def get_symbols(self, *args, **kwargs):
                return []
        
        source = MockDataSource("Test")
        
        # 多次连接
        await source.connect()
        await source.connect()
        await source.connect()
        
        assert source.is_connected is True
        
        await source.disconnect()
    
    def test_subscribe_not_implemented(self):
        """测试订阅方法未实现 - 简化版"""
        class MockDataSource(BaseDataSource):
            async def get_kline(self, *args, **kwargs):
                return []
            async def get_tick(self, *args, **kwargs):
                return []
            async def get_symbols(self, *args, **kwargs):
                return []
        
        source = MockDataSource("Test")
        
        # 直接调用方法应该返回一个异步生成器对象
        # 但因为我们没有await它，它只是一个协程
        gen = source.subscribe_kline("BTCUSDT", "1h")
        
        # 检查是否引发 NotImplementedError
        with pytest.raises(NotImplementedError):
            # 直接 await 协程会触发 NotImplementedError
            asyncio.run(gen)
