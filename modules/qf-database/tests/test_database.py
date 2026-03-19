"""
qf-database 模块测试
覆盖 MySQLManager, InfluxDBManager, RedisManager, DatabaseManager
"""
import pytest
from datetime import datetime, timedelta
from decimal import Decimal
from unittest.mock import Mock, patch, MagicMock

# 导入被测模块
from qf_database.models import Contract, Trade, Account, Kline, Tick
from qf_database.mysql_manager import MySQLManager, ContractModel, TradeModel, AccountModel
from qf_database.influxdb_manager import InfluxDBManager
from qf_database.redis_manager import RedisManager
from qf_database.database_manager import DatabaseManager, DatabaseConfig


# ==================== Fixtures ====================

@pytest.fixture
def sample_contract():
    """样本合约数据"""
    return Contract(
        symbol="BTCUSDT",
        exchange="binance",
        name="Bitcoin/USDT",
        contract_type="spot",
        base_asset="BTC",
        quote_asset="USDT",
        price_precision=2,
        quantity_precision=6,
        min_quantity=Decimal("0.00001"),
        max_quantity=Decimal("9000"),
        status="active"
    )


@pytest.fixture
def sample_trade():
    """样本交易数据"""
    return Trade(
        symbol="BTCUSDT",
        exchange="binance",
        side="buy",
        order_type="limit",
        price=Decimal("50000.00"),
        quantity=Decimal("0.1"),
        amount=Decimal("5000.00"),
        fee=Decimal("5.00"),
        fee_asset="USDT",
        status="filled",
        order_id="123456",
        trade_id="789012",
        account_id="test_account",
        strategy_id="strategy_1"
    )


@pytest.fixture
def sample_account():
    """样本账户数据"""
    return Account(
        account_id="test_account",
        exchange="binance",
        account_type="spot",
        asset="BTC",
        free=Decimal("1.5"),
        locked=Decimal("0.5")
    )


@pytest.fixture
def sample_kline():
    """样本K线数据"""
    return Kline(
        symbol="BTCUSDT",
        exchange="binance",
        interval="1h",
        timestamp=datetime(2024, 1, 1, 12, 0, 0),
        open=Decimal("50000.00"),
        high=Decimal("51000.00"),
        low=Decimal("49000.00"),
        close=Decimal("50500.00"),
        volume=Decimal("100.5"),
        quote_volume=Decimal("5075250.00"),
        trades=1500
    )


@pytest.fixture
def sample_tick():
    """样本Tick数据"""
    return Tick(
        symbol="BTCUSDT",
        exchange="binance",
        timestamp=datetime(2024, 1, 1, 12, 0, 0),
        price=Decimal("50000.00"),
        quantity=Decimal("0.5"),
        side="buy",
        trade_id="tick_001"
    )


# ==================== Models Tests ====================

class TestModels:
    """测试数据模型"""
    
    def test_contract_to_dict(self, sample_contract):
        """测试Contract转换为字典"""
        data = sample_contract.to_dict()
        assert data["symbol"] == "BTCUSDT"
        assert data["exchange"] == "binance"
        assert data["min_quantity"] == "0.00001"  # Decimal转为字符串
        assert data["max_quantity"] == "9000"
    
    def test_trade_to_dict(self, sample_trade):
        """测试Trade转换为字典"""
        data = sample_trade.to_dict()
        assert data["symbol"] == "BTCUSDT"
        assert data["price"] == "50000.00"
        assert data["side"] == "buy"
    
    def test_account_to_dict(self, sample_account):
        """测试Account转换为字典"""
        data = sample_account.to_dict()
        assert data["account_id"] == "test_account"
        assert data["free"] == "1.5"
        assert data["locked"] == "0.5"
        assert data["total"] == "0"  # 默认值
    
    def test_kline_to_dict(self, sample_kline):
        """测试Kline转换为字典"""
        data = sample_kline.to_dict()
        assert data["symbol"] == "BTCUSDT"
        assert data["open"] == 50000.00  # Decimal转为float
        assert data["trades"] == 1500
        assert "timestamp" in data
    
    def test_tick_to_dict(self, sample_tick):
        """测试Tick转换为字典"""
        data = sample_tick.to_dict()
        assert data["symbol"] == "BTCUSDT"
        assert data["price"] == 50000.00  # Decimal转为float
        assert data["side"] == "buy"


# ==================== MySQLManager Tests ====================

class TestMySQLManager:
    """测试MySQL管理器"""
    
    @patch('qf_database.mysql_manager.create_engine')
    def test_init(self, mock_create_engine):
        """测试初始化"""
        manager = MySQLManager(
            host="localhost",
            port=3306,
            user="root",
            password="test",
            database="quantforge"
        )
        assert manager.host == "localhost"
        assert manager.port == 3306
        assert manager.database == "quantforge"
        mock_create_engine.assert_called_once()
    
    @patch('qf_database.mysql_manager.create_engine')
    def test_connect_success(self, mock_create_engine):
        """测试连接成功"""
        mock_engine = Mock()
        mock_conn = Mock()
        mock_engine.connect.return_value.__enter__ = Mock(return_value=mock_conn)
        mock_engine.connect.return_value.__exit__ = Mock(return_value=False)
        mock_create_engine.return_value = mock_engine
        
        manager = MySQLManager()
        result = manager.connect()
        
        assert result is True
        assert manager.is_connected is True
    
    @patch('qf_database.mysql_manager.create_engine')
    def test_connect_failure(self, mock_create_engine):
        """测试连接失败"""
        mock_engine = Mock()
        mock_engine.connect.side_effect = Exception("Connection refused")
        mock_create_engine.return_value = mock_engine
        
        manager = MySQLManager()
        result = manager.connect()
        
        assert result is False
        assert manager.is_connected is False
    
    @patch('qf_database.mysql_manager.create_engine')
    def test_save_contract(self, mock_create_engine):
        """测试保存合约"""
        mock_engine = Mock()
        mock_create_engine.return_value = mock_engine
        
        manager = MySQLManager()
        manager.SessionLocal = Mock()
        mock_session = Mock()
        manager.SessionLocal.return_value = mock_session
        mock_session.__enter__ = Mock(return_value=mock_session)
        mock_session.__exit__ = Mock(return_value=False)
        
        contract = Contract(
            symbol="ETHUSDT",
            exchange="binance",
            name="Ethereum/USDT",
            contract_type="spot",
            base_asset="ETH",
            quote_asset="USDT"
        )
        
        # 模拟查询结果为空（新增）
        mock_session.execute.return_value.scalar_one_or_none.return_value = None
        
        result = manager.save_contract(contract)
        assert result is True
    
    @patch('qf_database.mysql_manager.create_engine')
    def test_get_contract(self, mock_create_engine):
        """测试获取合约"""
        mock_engine = Mock()
        mock_create_engine.return_value = mock_engine
        
        manager = MySQLManager()
        manager.SessionLocal = Mock()
        mock_session = Mock()
        manager.SessionLocal.return_value = mock_session
        mock_session.__enter__ = Mock(return_value=mock_session)
        mock_session.__exit__ = Mock(return_value=False)
        
        # 模拟返回合约数据
        mock_contract = Mock()
        mock_contract.symbol = "BTCUSDT"
        mock_contract.exchange = "binance"
        mock_contract.name = "Bitcoin/USDT"
        mock_contract.contract_type = "spot"
        mock_contract.base_asset = "BTC"
        mock_contract.quote_asset = "USDT"
        mock_contract.price_precision = 2
        mock_contract.quantity_precision = 6
        mock_contract.min_quantity = Decimal("0.00001")
        mock_contract.max_quantity = Decimal("9000")
        mock_contract.status = "active"
        mock_contract.created_at = datetime.utcnow()
        mock_contract.updated_at = datetime.utcnow()
        
        mock_session.execute.return_value.scalar_one_or_none.return_value = mock_contract
        
        result = manager.get_contract("BTCUSDT", "binance")
        assert result is not None
        assert result.symbol == "BTCUSDT"
        assert result.exchange == "binance"
    
    @patch('qf_database.mysql_manager.create_engine')
    def test_save_trade(self, mock_create_engine):
        """测试保存交易记录"""
        mock_engine = Mock()
        mock_create_engine.return_value = mock_engine
        
        manager = MySQLManager()
        manager.SessionLocal = Mock()
        mock_session = Mock()
        manager.SessionLocal.return_value = mock_session
        mock_session.__enter__ = Mock(return_value=mock_session)
        mock_session.__exit__ = Mock(return_value=False)
        
        trade = Trade(
            id=1,
            symbol="BTCUSDT",
            exchange="binance",
            side="sell",
            order_type="market",
            price=Decimal("51000.00"),
            quantity=Decimal("0.05"),
            amount=Decimal("2550.00"),
            account_id="test_account"
        )
        
        result = manager.save_trade(trade)
        assert result is True
    
    @patch('qf_database.mysql_manager.create_engine')
    def test_query_trades(self, mock_create_engine):
        """测试查询交易记录"""
        mock_engine = Mock()
        mock_create_engine.return_value = mock_engine
        
        manager = MySQLManager()
        manager.SessionLocal = Mock()
        mock_session = Mock()
        manager.SessionLocal.return_value = mock_session
        mock_session.__enter__ = Mock(return_value=mock_session)
        mock_session.__exit__ = Mock(return_value=False)
        
        # 模拟返回交易列表
        mock_trade = Mock()
        mock_trade.id = 1
        mock_trade.symbol = "BTCUSDT"
        mock_trade.exchange = "binance"
        mock_trade.side = "buy"
        mock_trade.order_type = "limit"
        mock_trade.price = Decimal("50000.00")
        mock_trade.quantity = Decimal("0.1")
        mock_trade.amount = Decimal("5000.00")
        mock_trade.fee = Decimal("5.00")
        mock_trade.fee_asset = "USDT"
        mock_trade.status = "filled"
        mock_trade.order_id = "123"
        mock_trade.trade_id = "456"
        mock_trade.account_id = "test_account"
        mock_trade.strategy_id = None
        mock_trade.created_at = datetime.utcnow()
        mock_trade.updated_at = datetime.utcnow()
        
        mock_session.execute.return_value.scalars.return_value.all.return_value = [mock_trade]
        
        results = manager.query_trades(account_id="test_account", limit=10)
        assert isinstance(results, list)
        assert len(results) == 1
        assert results[0].symbol == "BTCUSDT"
    
    @patch('qf_database.mysql_manager.create_engine')
    def test_save_account(self, mock_create_engine):
        """测试保存账户信息"""
        mock_engine = Mock()
        mock_create_engine.return_value = mock_engine
        
        manager = MySQLManager()
        manager.SessionLocal = Mock()
        mock_session = Mock()
        manager.SessionLocal.return_value = mock_session
        mock_session.__enter__ = Mock(return_value=mock_session)
        mock_session.__exit__ = Mock(return_value=False)
        
        # 模拟查询结果为空
        mock_session.execute.return_value.scalar_one_or_none.return_value = None
        
        account = Account(
            account_id="test_account",
            exchange="binance",
            account_type="spot",
            asset="ETH",
            free=Decimal("10.0"),
            locked=Decimal("2.0")
        )
        
        result = manager.save_account(account)
        assert result is True
    
    @patch('qf_database.mysql_manager.create_engine')
    def test_list_contracts_empty(self, mock_create_engine):
        """测试列出合约（空列表）"""
        mock_engine = Mock()
        mock_create_engine.return_value = mock_engine
        
        manager = MySQLManager()
        manager.SessionLocal = Mock()
        mock_session = Mock()
        manager.SessionLocal.return_value = mock_session
        mock_session.__enter__ = Mock(return_value=mock_session)
        mock_session.__exit__ = Mock(return_value=False)
        
        mock_session.execute.return_value.scalars.return_value.all.return_value = []
        
        results = manager.list_contracts()
        assert results == []


# ==================== InfluxDBManager Tests ====================

class TestInfluxDBManager:
    """测试InfluxDB管理器"""
    
    @patch('qf_database.influxdb_manager.InfluxDBClient')
    def test_init(self, mock_influx_client):
        """测试初始化"""
        manager = InfluxDBManager(
            url="http://localhost:8086",
            token="test_token",
            org="quantforge",
            bucket="market_data"
        )
        assert manager.url == "http://localhost:8086"
        assert manager.org == "quantforge"
        assert manager.bucket == "market_data"
        mock_influx_client.assert_called_once()
    
    @patch('qf_database.influxdb_manager.InfluxDBClient')
    def test_connect_success(self, mock_influx_client):
        """测试连接成功"""
        mock_client = Mock()
        mock_orgs_api = Mock()
        mock_orgs_api.find_organizations.return_value = [{"name": "quantforge"}]
        mock_client.organizations_api.return_value = mock_orgs_api
        mock_influx_client.return_value = mock_client
        
        manager = InfluxDBManager()
        result = manager.connect()
        
        assert result is True
        assert manager.is_connected is True
    
    @patch('qf_database.influxdb_manager.InfluxDBClient')
    def test_connect_failure(self, mock_influx_client):
        """测试连接失败"""
        mock_client = Mock()
        mock_client.organizations_api.side_effect = Exception("Connection refused")
        mock_influx_client.return_value = mock_client
        
        manager = InfluxDBManager()
        result = manager.connect()
        
        assert result is False
        assert manager.is_connected is False
    
    @patch('qf_database.influxdb_manager.InfluxDBClient')
    def test_save_kline(self, mock_influx_client):
        """测试保存K线数据"""
        mock_client = Mock()
        mock_write_api = Mock()
        mock_client.write_api.return_value = mock_write_api
        mock_influx_client.return_value = mock_client
        
        manager = InfluxDBManager()
        manager.write_api = mock_write_api
        
        kline = Kline(
            symbol="BTCUSDT",
            exchange="binance",
            interval="1h",
            timestamp=datetime(2024, 1, 1, 12, 0, 0),
            open=Decimal("50000.00"),
            high=Decimal("51000.00"),
            low=Decimal("49000.00"),
            close=Decimal("50500.00"),
            volume=Decimal("100.5"),
            quote_volume=Decimal("5075250.00"),
            trades=1500
        )
        
        result = manager.save_kline(kline)
        assert result is True
        mock_write_api.write.assert_called_once()
    
    @patch('qf_database.influxdb_manager.InfluxDBClient')
    def test_save_klines_batch(self, mock_influx_client):
        """测试批量保存K线数据"""
        mock_client = Mock()
        mock_write_api = Mock()
        mock_client.write_api.return_value = mock_write_api
        mock_influx_client.return_value = mock_client
        
        manager = InfluxDBManager()
        manager.write_api = mock_write_api
        
        klines = [
            Kline(
                symbol="BTCUSDT",
                exchange="binance",
                interval="1h",
                timestamp=datetime(2024, 1, 1, 12, 0, 0),
                open=Decimal("50000.00"),
                high=Decimal("51000.00"),
                low=Decimal("49000.00"),
                close=Decimal("50500.00"),
                volume=Decimal("100.5"),
                quote_volume=Decimal("5075250.00"),
                trades=1500
            ),
            Kline(
                symbol="BTCUSDT",
                exchange="binance",
                interval="1h",
                timestamp=datetime(2024, 1, 1, 13, 0, 0),
                open=Decimal("50500.00"),
                high=Decimal("51500.00"),
                low=Decimal("50000.00"),
                close=Decimal("51000.00"),
                volume=Decimal("120.0"),
                quote_volume=Decimal("6120000.00"),
                trades=1800
            )
        ]
        
        result = manager.save_klines(klines)
        assert result is True
        mock_write_api.write.assert_called_once()
    
    @patch('qf_database.influxdb_manager.InfluxDBClient')
    def test_save_tick(self, mock_influx_client):
        """测试保存Tick数据"""
        mock_client = Mock()
        mock_write_api = Mock()
        mock_client.write_api.return_value = mock_write_api
        mock_influx_client.return_value = mock_client
        
        manager = InfluxDBManager()
        manager.write_api = mock_write_api
        
        tick = Tick(
            symbol="BTCUSDT",
            exchange="binance",
            timestamp=datetime(2024, 1, 1, 12, 0, 0),
            price=Decimal("50000.00"),
            quantity=Decimal("0.5"),
            side="buy",
            trade_id="tick_001"
        )
        
        result = manager.save_tick(tick)
        assert result is True
        mock_write_api.write.assert_called_once()
    
    @patch('qf_database.influxdb_manager.InfluxDBClient')
    def test_query_klines_empty(self, mock_influx_client):
        """测试查询K线（空结果）"""
        mock_client = Mock()
        mock_query_api = Mock()
        mock_query_api.query.return_value = []
        mock_client.query_api.return_value = mock_query_api
        mock_influx_client.return_value = mock_client
        
        manager = InfluxDBManager()
        manager.query_api = mock_query_api
        
        results = manager.query_klines(
            symbol="BTCUSDT",
            exchange="binance",
            interval="1h",
            start_time=datetime(2024, 1, 1)
        )
        assert results == []
    
    @patch('qf_database.influxdb_manager.InfluxDBClient')
    def test_delete_klines(self, mock_influx_client):
        """测试删除K线数据"""
        mock_client = Mock()
        mock_delete_api = Mock()
        mock_client.delete_api.return_value = mock_delete_api
        mock_influx_client.return_value = mock_client
        
        manager = InfluxDBManager()
        manager.delete_api = mock_delete_api
        
        result = manager.delete_klines(
            symbol="BTCUSDT",
            exchange="binance",
            interval="1h",
            start_time=datetime(2024, 1, 1),
            end_time=datetime(2024, 1, 2)
        )
        assert result is True


# ==================== RedisManager Tests ====================

class TestRedisManager:
    """测试Redis管理器"""
    
    @patch('qf_database.redis_manager.redis.ConnectionPool')
    @patch('qf_database.redis_manager.redis.Redis')
    def test_init(self, mock_redis, mock_pool):
        """测试初始化"""
        manager = RedisManager(
            host="localhost",
            port=6379,
            db=0
        )
        assert manager.host == "localhost"
        assert manager.port == 6379
        assert manager.db == 0
    
    @patch('qf_database.redis_manager.redis.ConnectionPool')
    @patch('qf_database.redis_manager.redis.Redis')
    def test_connect_success(self, mock_redis_class, mock_pool):
        """测试连接成功"""
        mock_client = Mock()
        mock_client.ping.return_value = True
        mock_redis_class.return_value = mock_client
        
        manager = RedisManager()
        manager.client = mock_client
        result = manager.connect()
        
        assert result is True
        assert manager.is_connected is True
    
    @patch('qf_database.redis_manager.redis.ConnectionPool')
    @patch('qf_database.redis_manager.redis.Redis')
    def test_connect_failure(self, mock_redis_class, mock_pool):
        """测试连接失败"""
        mock_client = Mock()
        mock_client.ping.side_effect = Exception("Connection refused")
        mock_redis_class.return_value = mock_client
        
        manager = RedisManager()
        manager.client = mock_client
        result = manager.connect()
        
        assert result is False
        assert manager.is_connected is False
    
    @patch('qf_database.redis_manager.redis.ConnectionPool')
    @patch('qf_database.redis_manager.redis.Redis')
    def test_set_and_get(self, mock_redis_class, mock_pool):
        """测试设置和获取"""
        mock_client = Mock()
        mock_redis_class.return_value = mock_client
        
        manager = RedisManager()
        manager.client = mock_client
        
        # 测试设置
        mock_client.setex.return_value = True
        result = manager.set("test_key", {"data": "value"}, ttl=60)
        assert result is True
        
        # 测试获取
        mock_client.get.return_value = b'{"data": "value"}'
        value = manager.get("test_key")
        assert value == {"data": "value"}
    
    @patch('qf_database.redis_manager.redis.ConnectionPool')
    @patch('qf_database.redis_manager.redis.Redis')
    def test_cache_tick(self, mock_redis_class, mock_pool):
        """测试缓存Tick数据"""
        mock_client = Mock()
        mock_redis_class.return_value = mock_client
        
        manager = RedisManager()
        manager.client = mock_client
        
        tick = Tick(
            symbol="BTCUSDT",
            exchange="binance",
            timestamp=datetime(2024, 1, 1, 12, 0, 0),
            price=Decimal("50000.00"),
            quantity=Decimal("0.5"),
            side="buy",
            trade_id="tick_001"
        )
        
        mock_client.setex.return_value = True
        result = manager.cache_tick(tick, ttl=60)
        assert result is True
    
    @patch('qf_database.redis_manager.redis.ConnectionPool')
    @patch('qf_database.redis_manager.redis.Redis')
    def test_get_cached_tick(self, mock_redis_class, mock_pool):
        """测试获取缓存的Tick数据"""
        mock_client = Mock()
        mock_redis_class.return_value = mock_client
        
        manager = RedisManager()
        manager.client = mock_client
        
        mock_client.get.return_value = json.dumps({
            "symbol": "BTCUSDT",
            "exchange": "binance",
            "timestamp": "2024-01-01T12:00:00",
            "price": "50000.00",
            "quantity": "0.5",
            "side": "buy",
            "trade_id": "tick_001"
        }).encode()
        
        result = manager.get_cached_tick("BTCUSDT", "binance")
        assert result is not None
        assert result.symbol == "BTCUSDT"
        assert result.price == Decimal("50000.00")
    
    @patch('qf_database.redis_manager.redis.ConnectionPool')
    @patch('qf_database.redis_manager.redis.Redis')
    def test_cache_kline(self, mock_redis_class, mock_pool):
        """测试缓存K线数据"""
        mock_client = Mock()
        mock_redis_class.return_value = mock_client
        
        manager = RedisManager()
        manager.client = mock_client
        
        kline = Kline(
            symbol="BTCUSDT",
            exchange="binance",
            interval="1h",
            timestamp=datetime(2024, 1, 1, 12, 0, 0),
            open=Decimal("50000.00"),
            high=Decimal("51000.00"),
            low=Decimal("49000.00"),
            close=Decimal("50500.00"),
            volume=Decimal("100.5"),
            quote_volume=Decimal("5075250.00"),
            trades=1500
        )
        
        mock_client.setex.return_value = True
        result = manager.cache_kline(kline, ttl=300)
        assert result is True
    
    @patch('qf_database.redis_manager.redis.ConnectionPool')
    @patch('qf_database.redis_manager.redis.Redis')
    def test_rate_limit_check(self, mock_redis_class, mock_pool):
        """测试限流检查"""
        mock_client = Mock()
        mock_redis_class.return_value = mock_client
        
        manager = RedisManager()
        manager.client = mock_client
        
        # 首次请求
        mock_client.get.return_value = None
        mock_client.pipeline.return_value = mock_client
        
        allowed, count, ttl = manager.rate_limit_check("api_key", max_requests=100, window_seconds=60)
        assert allowed is True
        assert count == 1
    
    @patch('qf_database.redis_manager.redis.ConnectionPool')
    @patch('qf_database.redis_manager.redis.Redis')
    def test_acquire_lock(self, mock_redis_class, mock_pool):
        """测试获取分布式锁"""
        mock_client = Mock()
        mock_redis_class.return_value = mock_client
        
        manager = RedisManager()
        manager.client = mock_client
        
        mock_client.set.return_value = True
        result = manager.acquire_lock("test_lock", ttl=30)
        assert result is True
    
    @patch('qf_database.redis_manager.redis.ConnectionPool')
    @patch('qf_database.redis_manager.redis.Redis')
    def test_release_lock(self, mock_redis_class, mock_pool):
        """测试释放分布式锁"""
        mock_client = Mock()
        mock_redis_class.return_value = mock_client
        
        manager = RedisManager()
        manager.client = mock_client
        
        mock_client.delete.return_value = 1
        result = manager.release_lock("test_lock")
        assert result is True
    
    @patch('qf_database.redis_manager.redis.ConnectionPool')
    @patch('qf_database.redis_manager.redis.Redis')
    def test_publish_subscribe(self, mock_redis_class, mock_pool):
        """测试发布订阅"""
        mock_client = Mock()
        mock_redis_class.return_value = mock_client
        
        manager = RedisManager()
        manager.client = mock_client
        
        # 测试发布
        mock_client.publish.return_value = 2
        result = manager.publish("test_channel", {"message": "hello"})
        assert result == 2
        
        # 测试订阅
        mock_pubsub = Mock()
        mock_client.pubsub.return_value = mock_pubsub
        result = manager.subscribe("test_channel")
        assert result == mock_pubsub


import json


# ==================== DatabaseManager Tests ====================

class TestDatabaseManager:
    """测试统一数据库管理器"""
    
    def test_init_default_config(self):
        """测试使用默认配置初始化"""
        with patch.object(MySQLManager, '__init__', return_value=None) as mock_mysql, \
             patch.object(InfluxDBManager, '__init__', return_value=None) as mock_influx, \
             patch.object(RedisManager, '__init__', return_value=None) as mock_redis:
            
            manager = DatabaseManager()
            assert manager.config is not None
            mock_mysql.assert_called_once()
            mock_influx.assert_called_once()
            mock_redis.assert_called_once()
    
    def test_init_custom_config(self):
        """测试使用自定义配置初始化"""
        config = DatabaseConfig(
            mysql_host="custom_mysql",
            mysql_port=3307,
            influxdb_url="http://custom:8086",
            redis_host="custom_redis"
        )
        
        with patch.object(MySQLManager, '__init__', return_value=None), \
             patch.object(InfluxDBManager, '__init__', return_value=None), \
             patch.object(RedisManager, '__init__', return_value=None):
            
            manager = DatabaseManager(config)
            assert manager.config.mysql_host == "custom_mysql"
            assert manager.config.influxdb_url == "http://custom:8086"
    
    @patch.object(MySQLManager, 'connect', return_value=True)
    @patch.object(InfluxDBManager, 'connect', return_value=True)
    @patch.object(RedisManager, 'connect', return_value=True)
    def test_connect_all(self, mock_redis, mock_influx, mock_mysql):
        """测试连接所有数据库"""
        with patch.object(MySQLManager, '__init__', return_value=None), \
             patch.object(InfluxDBManager, '__init__', return_value=None), \
             patch.object(RedisManager, '__init__', return_value=None):
            
            manager = DatabaseManager()
            results = manager.connect_all()
            
            assert results["mysql"] is True
            assert results["influxdb"] is True
            assert results["redis"] is True
    
    @patch.object(MySQLManager, 'disconnect')
    @patch.object(InfluxDBManager, 'disconnect')
    @patch.object(RedisManager, 'disconnect')
    def test_disconnect_all(self, mock_redis, mock_influx, mock_mysql):
        """测试断开所有连接"""
        with patch.object(MySQLManager, '__init__', return_value=None), \
             patch.object(InfluxDBManager, '__init__', return_value=None), \
             patch.object(RedisManager, '__init__', return_value=None):
            
            manager = DatabaseManager()
            manager.disconnect_all()
            
            mock_mysql.assert_called_once()
            mock_influx.assert_called_once()
            mock_redis.assert_called_once()
    
    @patch.object(MySQLManager, 'save_contract', return_value=True)
    def test_save_contract_shortcut(self, mock_save):
        """测试保存合约快捷方法"""
        with patch.object(MySQLManager, '__init__', return_value=None), \
             patch.object(InfluxDBManager, '__init__', return_value=None), \
             patch.object(RedisManager, '__init__', return_value=None):
            
            manager = DatabaseManager()
            contract = Contract(
                symbol="BTCUSDT",
                exchange="binance",
                name="Bitcoin/USDT",
                contract_type="spot",
                base_asset="BTC",
                quote_asset="USDT"
            )
            result = manager.save_contract(contract)
            
            assert result is True
            mock_save.assert_called_once_with(contract)
    
    @patch.object(MySQLManager, 'get_contract', return_value=None)
    def test_get_contract_shortcut(self, mock_get):
        """测试获取合约快捷方法"""
        with patch.object(MySQLManager, '__init__', return_value=None), \
             patch.object(InfluxDBManager, '__init__', return_value=None), \
             patch.object(RedisManager, '__init__', return_value=None):
            
            manager = DatabaseManager()
            result = manager.get_contract("BTCUSDT", "binance")
            
            mock_get.assert_called_once_with("BTCUSDT", "binance")
    
    @patch.object(InfluxDBManager, 'save_kline', return_value=True)
    @patch.object(RedisManager, 'cache_kline', return_value=True)
    def test_save_kline_with_cache(self, mock_redis, mock_influx):
        """测试保存K线并缓存"""
        with patch.object(MySQLManager, '__init__', return_value=None), \
             patch.object(InfluxDBManager, '__init__', return_value=None), \
             patch.object(RedisManager, '__init__', return_value=None):
            
            manager = DatabaseManager()
            kline = Kline(
                symbol="BTCUSDT",
                exchange="binance",
                interval="1h",
                timestamp=datetime(2024, 1, 1, 12, 0, 0),
                open=Decimal("50000.00"),
                high=Decimal("51000.00"),
                low=Decimal("49000.00"),
                close=Decimal("50500.00"),
                volume=Decimal("100.5"),
                quote_volume=Decimal("5075250.00"),
                trades=1500
            )
            result = manager.save_kline(kline, cache=True)
            
            assert result is True
            mock_influx.assert_called_once()
            mock_redis.assert_called_once()
    
    @patch.object(RedisManager, 'get_cached_kline', return_value=None)
    @patch.object(InfluxDBManager, 'get_latest_kline', return_value=None)
    def test_get_kline_from_db(self, mock_influx, mock_redis):
        """测试从数据库获取K线"""
        with patch.object(MySQLManager, '__init__', return_value=None), \
             patch.object(InfluxDBManager, '__init__', return_value=None), \
             patch.object(RedisManager, '__init__', return_value=None):
            
            manager = DatabaseManager()
            result = manager.get_kline("BTCUSDT", "binance", "1h", use_cache=True)
            
            mock_redis.assert_called_once()
            mock_influx.assert_called_once()
    
    @patch.object(InfluxDBManager, 'save_tick', return_value=True)
    @patch.object(RedisManager, 'cache_tick', return_value=True)
    def test_save_tick_with_cache(self, mock_redis, mock_influx):
        """测试保存Tick并缓存"""
        with patch.object(MySQLManager, '__init__', return_value=None), \
             patch.object(InfluxDBManager, '__init__', return_value=None), \
             patch.object(RedisManager, '__init__', return_value=None):
            
            manager = DatabaseManager()
            tick = Tick(
                symbol="BTCUSDT",
                exchange="binance",
                timestamp=datetime(2024, 1, 1, 12, 0, 0),
                price=Decimal("50000.00"),
                quantity=Decimal("0.5"),
                side="buy",
                trade_id="tick_001"
            )
            result = manager.save_tick(tick, cache=True)
            
            assert result is True
            mock_influx.assert_called_once()
            mock_redis.assert_called_once()
    
    @patch.object(MySQLManager, 'create_tables')
    @patch.object(InfluxDBManager, 'ensure_bucket', return_value=True)
    @patch.object(RedisManager, 'connect', return_value=True)
    def test_init_all(self, mock_redis, mock_influx, mock_mysql):
        """测试初始化所有数据库"""
        with patch.object(MySQLManager, '__init__', return_value=None), \
             patch.object(InfluxDBManager, '__init__', return_value=None), \
             patch.object(RedisManager, '__init__', return_value=None):
            
            manager = DatabaseManager()
            results = manager.init_all()
            
            assert results["influxdb_bucket"] is True
            assert results["redis_connection"] is True
    
    @patch.object(MySQLManager, 'connect', return_value=True)
    @patch.object(InfluxDBManager, 'connect', return_value=True)
    @patch.object(RedisManager, 'connect', return_value=True)
    def test_context_manager(self, mock_redis, mock_influx, mock_mysql):
        """测试上下文管理器"""
        with patch.object(MySQLManager, '__init__', return_value=None), \
             patch.object(InfluxDBManager, '__init__', return_value=None), \
             patch.object(RedisManager, '__init__', return_value=None), \
             patch.object(MySQLManager, 'disconnect') as mock_mysql_close, \
             patch.object(InfluxDBManager, 'disconnect') as mock_influx_close, \
             patch.object(RedisManager, 'disconnect') as mock_redis_close:
            
            with DatabaseManager() as manager:
                pass
            
            mock_mysql_close.assert_called_once()
            mock_influx_close.assert_called_once()
            mock_redis_close.assert_called_once()


# ==================== Integration Tests ====================

class TestIntegration:
    """集成测试"""
    
    def test_models_json_serialization(self, sample_contract, sample_trade, sample_kline, sample_tick):
        """测试模型JSON序列化"""
        import json
        
        # 测试Contract
        contract_json = json.dumps(sample_contract.to_dict())
        assert "BTCUSDT" in contract_json
        
        # 测试Trade
        trade_json = json.dumps(sample_trade.to_dict())
        assert "50000.00" in trade_json
        
        # 测试Kline
        kline_json = json.dumps(sample_kline.to_dict())
        assert "50000.0" in kline_json
        
        # 测试Tick
        tick_json = json.dumps(sample_tick.to_dict())
        assert "tick_001" in tick_json
    
    def test_decimal_conversion(self):
        """测试Decimal转换"""
        from decimal import Decimal
        
        kline = Kline(
            symbol="TEST",
            exchange="test",
            interval="1m",
            timestamp=datetime.utcnow(),
            open=Decimal("123.456789012345678901"),
            high=Decimal("123.456789012345678901"),
            low=Decimal("123.456789012345678901"),
            close=Decimal("123.456789012345678901"),
            volume=Decimal("1000.123456789012345678"),
            quote_volume=Decimal("100000.123456789012345678")
        )
        
        data = kline.to_dict()
        # Decimal应转换为float
        assert isinstance(data["open"], float)
        assert isinstance(data["close"], float)