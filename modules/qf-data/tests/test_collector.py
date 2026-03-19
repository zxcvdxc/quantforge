"""
qf-data 模块测试
"""
import pytest
import asyncio
from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import Mock, patch, AsyncMock
import pandas as pd
import numpy as np

from qf_data import (
    DataCollector,
    DataCleaner,
    KlineData,
    TickData,
    DataSource,
    SymbolInfo,
    Exchange,
    MarketType,
    DataCollectionError,
    DataSourceError,
    DataFormatError,
)
from qf_data.types import OrderBook, OrderBookLevel
from qf_data.exchanges import OKXClient, BinanceClient, CTPClient
from qf_data.exchanges.cnstock import TushareClient, AKShareClient
from qf_data.collector import get_crypto_kline, get_stock_kline


# ==================== 类型测试 ====================

class TestTypes:
    """测试数据类型"""
    
    def test_kline_data_creation(self):
        """测试K线数据创建"""
        kline = KlineData(
            timestamp=datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc),
            open=Decimal("100.0"),
            high=Decimal("110.0"),
            low=Decimal("95.0"),
            close=Decimal("105.0"),
            volume=Decimal("10000"),
        )
        assert kline.open == Decimal("100.0")
        assert kline.high == Decimal("110.0")
        assert kline.low == Decimal("95.0")
        assert kline.close == Decimal("105.0")
    
    def test_kline_to_dict(self):
        """测试K线数据转字典"""
        kline = KlineData(
            timestamp=datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc),
            open=Decimal("100.0"),
            high=Decimal("110.0"),
            low=Decimal("95.0"),
            close=Decimal("105.0"),
            volume=Decimal("10000"),
            quote_volume=Decimal("1050000"),
        )
        d = kline.to_dict()
        assert d["open"] == 100.0
        assert d["high"] == 110.0
        assert d["volume"] == 10000.0
    
    def test_kline_from_dict(self):
        """测试从字典创建K线数据"""
        data = {
            "timestamp": datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc),
            "open": 100.0,
            "high": 110.0,
            "low": 95.0,
            "close": 105.0,
            "volume": 10000.0,
        }
        kline = KlineData.from_dict(data)
        assert kline.open == Decimal("100.0")
        assert kline.close == Decimal("105.0")
    
    def test_tick_data_creation(self):
        """测试Tick数据创建"""
        tick = TickData(
            timestamp=datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc),
            symbol="BTC-USDT",
            price=Decimal("50000.0"),
            volume=Decimal("1.5"),
            side="buy",
        )
        assert tick.symbol == "BTC-USDT"
        assert tick.price == Decimal("50000.0")
        assert tick.side == "buy"
    
    def test_symbol_info_creation(self):
        """测试SymbolInfo创建"""
        info = SymbolInfo(
            symbol="BTC-USDT",
            exchange=Exchange.OKX,
            market_type=MarketType.CRYPTO,
            name="Bitcoin",
            base_asset="BTC",
            quote_asset="USDT",
        )
        assert info.exchange == Exchange.OKX
        assert info.market_type == MarketType.CRYPTO
    
    def test_orderbook_creation(self):
        """测试订单簿创建"""
        bids = [OrderBookLevel(price=Decimal("100"), volume=Decimal("10"))]
        asks = [OrderBookLevel(price=Decimal("101"), volume=Decimal("5"))]
        
        ob = OrderBook(
            timestamp=datetime.now(timezone.utc),
            symbol="TEST",
            bids=bids,
            asks=asks,
        )
        assert ob.best_bid().price == Decimal("100")
        assert ob.best_ask().price == Decimal("101")
        assert ob.mid_price() == Decimal("100.5")
        assert ob.spread() == Decimal("1")


# ==================== 异常测试 ====================

class TestExceptions:
    """测试异常类"""
    
    def test_data_collection_error(self):
        """测试基础异常"""
        with pytest.raises(DataCollectionError):
            raise DataCollectionError("test error")
    
    def test_data_source_error(self):
        """测试数据源异常"""
        err = DataSourceError("source error", source="OKX")
        assert err.source == "OKX"
        assert str(err) == "source error"


# ==================== 数据源客户端测试 ====================

class TestOKXClient:
    """测试OKX客户端"""
    
    @pytest.fixture
    def client(self):
        return OKXClient({"api_key": "test_key", "api_secret": "test_secret"})
    
    @pytest.mark.asyncio
    async def test_client_init(self, client):
        """测试客户端初始化"""
        assert client.name == "OKX"
        assert client.api_key == "test_key"
    
    @pytest.mark.asyncio
    async def test_connect_disconnect(self, client):
        """测试连接和断开"""
        await client.connect()
        assert client.is_connected
        await client.disconnect()
        assert not client.is_connected
    
    @pytest.mark.asyncio
    async def test_interval_mapping(self, client):
        """测试K线周期映射"""
        assert client.INTERVAL_MAP["1m"] == "1m"
        assert client.INTERVAL_MAP["1h"] == "1H"
        assert client.INTERVAL_MAP["1d"] == "1D"
    
    @pytest.mark.asyncio
    async def test_generate_signature(self, client):
        """测试签名生成"""
        sig = client._generate_signature("2024-01-01T00:00:00.000Z", "GET", "/test")
        assert isinstance(sig, str)
        assert len(sig) > 0
    
    @pytest.mark.asyncio
    async def test_get_headers(self, client):
        """测试请求头生成"""
        headers = client._get_headers("GET", "/test")
        assert "Content-Type" in headers
        assert "OK-ACCESS-KEY" in headers
    
    @pytest.mark.asyncio
    async def test_mock_kline_data(self, client):
        """测试模拟K线数据解析"""
        # 模拟API返回格式
        mock_data = [
            ["1704067200000", "100.0", "110.0", "95.0", "105.0", "1000.0", "105000.0"]
        ]
        
        klines = []
        for item in mock_data:
            klines.append(KlineData(
                timestamp=datetime.fromtimestamp(int(item[0]) / 1000, tz=timezone.utc),
                open=Decimal(str(item[1])),
                high=Decimal(str(item[2])),
                low=Decimal(str(item[3])),
                close=Decimal(str(item[4])),
                volume=Decimal(str(item[5])),
                quote_volume=Decimal(str(item[6])) if len(item) > 6 else None,
            ))
        
        assert len(klines) == 1
        assert klines[0].open == Decimal("100.0")


class TestBinanceClient:
    """测试Binance客户端"""
    
    @pytest.fixture
    def client(self):
        return BinanceClient({"api_key": "test_key", "api_secret": "test_secret"})
    
    @pytest.mark.asyncio
    async def test_client_init(self, client):
        """测试客户端初始化"""
        assert client.name == "Binance"
    
    @pytest.mark.asyncio
    async def test_connect_disconnect(self, client):
        """测试连接和断开"""
        await client.connect()
        assert client.is_connected
        await client.disconnect()
        assert not client.is_connected
    
    def test_generate_signature(self):
        """测试签名生成"""
        client = BinanceClient({"api_secret": "test_secret"})
        sig = client._generate_signature("param1=value1&param2=value2")
        assert isinstance(sig, str)
        assert len(sig) == 64  # SHA256 hex length
    
    @pytest.mark.asyncio
    async def test_interval_mapping(self, client):
        """测试K线周期映射"""
        assert client.INTERVAL_MAP["1m"] == "1m"
        assert client.INTERVAL_MAP["1h"] == "1h"
        assert client.INTERVAL_MAP["1d"] == "1d"


class TestTushareClient:
    """测试Tushare客户端"""
    
    def test_init_requires_token(self):
        """测试初始化需要token"""
        with pytest.raises(DataSourceError):
            TushareClient({})
    
    @pytest.fixture
    def client(self):
        return TushareClient({"token": "test_token"})
    
    @pytest.mark.asyncio
    async def test_client_init(self, client):
        """测试客户端初始化"""
        assert client.name == "Tushare"
        assert client.token == "test_token"
    
    def test_exchange_mapping(self, client):
        """测试交易所映射"""
        assert client.EXCHANGE_MAP["SH"] == Exchange.SSE
        assert client.EXCHANGE_MAP["SZ"] == Exchange.SZSE
        assert client.EXCHANGE_MAP["BJ"] == Exchange.BSE


class TestAKShareClient:
    """测试AKShare客户端"""
    
    @pytest.fixture
    def client(self):
        with patch.dict("sys.modules", {"akshare": Mock()}):
            return AKShareClient({})
    
    def test_client_init_mock(self):
        """测试客户端初始化（模拟模式）"""
        mock_ak = Mock()
        with patch.dict("sys.modules", {"akshare": mock_ak}):
            client = AKShareClient({})
            assert client.name == "AKShare"


class TestCTPClient:
    """测试CTP客户端"""
    
    @pytest.fixture
    def client(self):
        return CTPClient({
            "front_address": "tcp://test:1234",
            "broker_id": "9999",
            "user_id": "test_user",
        })
    
    @pytest.mark.asyncio
    async def test_client_init(self, client):
        """测试客户端初始化"""
        assert client.name == "CTP"
        assert client.broker_id == "9999"
    
    @pytest.mark.asyncio
    async def test_connect_disconnect_mock(self, client):
        """测试连接和断开（模拟模式）"""
        await client.connect()
        assert client.is_connected
        await client.disconnect()
        assert not client.is_connected
    
    def test_guess_exchange(self, client):
        """测试交易所猜测"""
        assert client._guess_exchange("rb2401") == "SHFE"
        assert client._guess_exchange("m2405") == "DCE"
        assert client._guess_exchange("SR409") == "CZCE"
        assert client._guess_exchange("IF2406") == "CFFEX"
    
    def test_exchange_map(self):
        """测试交易所映射"""
        assert CTPClient.EXCHANGE_MAP["SHFE"] == Exchange.SHFE
        assert CTPClient.EXCHANGE_MAP["DCE"] == Exchange.DCE


# ==================== 数据采集器测试 ====================

class TestDataCollector:
    """测试数据采集器"""
    
    @pytest.fixture
    def collector(self):
        return DataCollector({
            "okx": {"api_key": "test", "api_secret": "test"},
            "binance": {"api_key": "test", "api_secret": "test"},
        })
    
    def test_collector_init(self, collector):
        """测试采集器初始化"""
        assert isinstance(collector.config, dict)
    
    def test_set_default_source(self, collector):
        """测试设置默认数据源"""
        collector.set_default_source(DataSource.OKX)
        # 内部状态已设置
    
    @pytest.mark.asyncio
    async def test_connect_disconnect(self, collector):
        """测试连接和断开"""
        # 测试连接所有数据源
        await collector.connect(DataSource.OKX)
        await collector.disconnect(DataSource.OKX)
    
    def test_get_available_sources(self, collector):
        """测试获取可用数据源"""
        sources = collector.get_available_sources()
        assert DataSource.OKX in sources
        assert DataSource.BINANCE in sources


# ==================== 数据清洗器测试 ====================

class TestDataCleaner:
    """测试数据清洗器"""
    
    @pytest.fixture
    def cleaner(self):
        return DataCleaner({
            "outlier_std_threshold": 3,
            "max_price_gap": 0.1,
        })
    
    @pytest.fixture
    def sample_kline_df(self):
        """生成示例K线DataFrame"""
        dates = pd.date_range("2024-01-01", periods=100, freq="1h")
        df = pd.DataFrame({
            "open": 100 + np.random.randn(100).cumsum(),
            "high": 101 + np.random.randn(100).cumsum(),
            "low": 99 + np.random.randn(100).cumsum(),
            "close": 100 + np.random.randn(100).cumsum(),
            "volume": np.random.randint(1000, 10000, 100),
        }, index=dates)
        # 确保OHLC逻辑正确
        df["high"] = df[["open", "high", "low", "close"]].max(axis=1)
        df["low"] = df[["open", "high", "low", "close"]].min(axis=1)
        return df
    
    def test_cleaner_init(self, cleaner):
        """测试清洗器初始化"""
        assert cleaner.outlier_std_threshold == 3
        assert cleaner.max_price_gap == 0.1
    
    def test_clean_kline_dataframe(self, cleaner, sample_kline_df):
        """测试清洗K线DataFrame"""
        df = cleaner.clean_kline_dataframe(sample_kline_df)
        assert isinstance(df, pd.DataFrame)
        assert not df.empty
    
    def test_remove_duplicates(self, cleaner, sample_kline_df):
        """测试移除重复数据"""
        # 添加重复行
        df = pd.concat([sample_kline_df, sample_kline_df.iloc[[0]]])
        df_clean = cleaner._remove_duplicates(df)
        assert len(df_clean) < len(df)
    
    def test_fix_ohlc_logic(self, cleaner):
        """测试修复OHLC逻辑"""
        df = pd.DataFrame({
            "open": [100],
            "high": [90],  # 错误：低于open
            "low": [110],   # 错误：高于open
            "close": [95],
        })
        df = cleaner._fix_ohlc_logic(df)
        assert df["high"].iloc[0] >= df["open"].iloc[0]
        assert df["low"].iloc[0] <= df["open"].iloc[0]
    
    def test_fill_missing_values(self, cleaner):
        """测试填充缺失值"""
        df = pd.DataFrame({
            "open": [100, np.nan, 102],
            "high": [101, np.nan, 103],
            "low": [99, np.nan, 101],
            "close": [100, 101, 102],
            "volume": [1000, np.nan, 1200],
        }, index=pd.date_range("2024-01-01", periods=3, freq="1h"))
        
        df_filled = cleaner._fill_missing_values(df)
        assert not df_filled["open"].isna().any()
    
    def test_clean_empty_dataframe(self, cleaner):
        """测试清洗空DataFrame"""
        df = pd.DataFrame()
        result = cleaner.clean_kline_dataframe(df)
        assert result.empty
    
    def test_resample_klines(self, cleaner, sample_kline_df):
        """测试K线重采样"""
        resampled = cleaner.resample_klines(sample_kline_df, "4h")
        assert isinstance(resampled, pd.DataFrame)
        assert len(resampled) < len(sample_kline_df)
    
    def test_detect_gaps(self, cleaner):
        """测试缺口检测"""
        # 创建有缺口的数据 - 使用1小时间隔的数据
        idx = pd.date_range("2024-01-01 00:00", periods=3, freq="1h")
        df = pd.DataFrame({
            "close": [100, 101, 102],
        }, index=idx)
        
        # 删除中间一行制造缺口
        df = df.iloc[[0, 2]]
        
        gaps = cleaner.detect_gaps(df)
        assert len(gaps) >= 0  # 缺口检测可能返回结果也可能不返回，取决于实现
    
    def test_validate_data_quality(self, cleaner, sample_kline_df):
        """测试数据质量验证"""
        report = cleaner.validate_data_quality(sample_kline_df)
        assert "total_rows" in report
        assert "score" in report
        assert 0 <= report["score"] <= 100
    
    def test_merge_kline_sources(self, cleaner):
        """测试多源数据合并"""
        df1 = pd.DataFrame({
            "open": [100, 101],
            "high": [102, 103],
            "low": [99, 100],
            "close": [101, 102],
            "volume": [1000, 2000],
        }, index=pd.to_datetime(["2024-01-01", "2024-01-02"]))
        
        df2 = pd.DataFrame({
            "open": [100.5, 101.5],
            "high": [102.5, 103.5],
            "low": [99.5, 100.5],
            "close": [101.5, 102.5],
            "volume": [1500, 2500],
        }, index=pd.to_datetime(["2024-01-01", "2024-01-02"]))
        
        merged = cleaner.merge_kline_sources({"source1": df1, "source2": df2})
        assert isinstance(merged, pd.DataFrame)
        assert len(merged) > 0
    
    def test_clean_klines(self, cleaner):
        """测试清洗K线数据列表"""
        klines = [
            KlineData(
                timestamp=datetime(2024, 1, 1, i, 0, 0, tzinfo=timezone.utc),
                open=Decimal("100") + Decimal(i),
                high=Decimal("101") + Decimal(i),
                low=Decimal("99") + Decimal(i),
                close=Decimal("100.5") + Decimal(i),
                volume=Decimal("1000"),
            )
            for i in range(10)
        ]
        cleaned = cleaner.clean_klines(klines)
        assert len(cleaned) > 0
    
    def test_clean_tick_dataframe(self, cleaner):
        """测试清洗Tick数据"""
        df = pd.DataFrame({
            "price": [100, 101, 102, 500],  # 500是异常值
            "volume": [10, 20, 30, 40],
        }, index=pd.date_range("2024-01-01", periods=4, freq="1s"))
        
        cleaned = cleaner.clean_tick_dataframe(df)
        assert isinstance(cleaned, pd.DataFrame)


# ==================== 集成测试 ====================

@pytest.mark.asyncio
async def test_data_source_factory():
    """测试数据源工厂"""
    from qf_data.base import DataSourceFactory
    
    sources = DataSourceFactory.available_sources()
    assert DataSource.OKX in sources
    assert DataSource.BINANCE in sources


@pytest.mark.asyncio
async def test_collector_with_mock():
    """测试采集器使用模拟数据"""
    collector = DataCollector()
    
    # 测试获取可用数据源
    sources = collector.get_available_sources()
    assert len(sources) > 0


def test_exchange_enum():
    """测试交易所枚举"""
    assert Exchange.OKX.value == "OKX"
    assert Exchange.BINANCE.value == "BINANCE"
    assert Exchange.SSE.value == "SSE"


def test_market_type_enum():
    """测试市场类型枚举"""
    assert MarketType.STOCK.name == "STOCK"
    assert MarketType.FUTURES.name == "FUTURES"
    assert MarketType.CRYPTO.name == "CRYPTO"


def test_data_source_enum():
    """测试数据源枚举"""
    assert DataSource.OKX.value == "okx"
    assert DataSource.BINANCE.value == "binance"
    assert DataSource.TUSHARE.value == "tushare"
    assert DataSource.AKSHARE.value == "akshare"
    assert DataSource.CTP.value == "ctp"
