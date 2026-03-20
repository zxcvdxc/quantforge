"""
qf-database 模块测试 - 补充测试以提高覆盖率
"""
import pytest
from datetime import datetime, timedelta
from decimal import Decimal
from unittest.mock import Mock, patch, MagicMock, PropertyMock
import json

# 导入被测模块
from qf_database.models import Contract, Trade, Account, Kline, Tick
from qf_database.mysql_manager import MySQLManager
from qf_database.influxdb_manager import InfluxDBManager
from qf_database.redis_manager import RedisManager
from qf_database.database_manager import DatabaseManager, DatabaseConfig


# ==================== Extended Models Tests ====================

class TestModelsExtended:
    """扩展数据模型测试"""
    
    def test_contract_with_datetime(self):
        """测试Contract带时间戳"""
        now = datetime.now()
        contract = Contract(
            symbol="ETHUSDT",
            exchange="binance",
            name="Ethereum/USDT",
            contract_type="spot",
            base_asset="ETH",
            quote_asset="USDT",
            created_at=now,
            updated_at=now
        )
        data = contract.to_dict()
        assert data["created_at"] == now.isoformat()
        assert data["updated_at"] == now.isoformat()
    
    def test_kline_decimal_precision(self):
        """测试Kline的Decimal精度"""
        kline = Kline(
            symbol="BTCUSDT",
            exchange="binance",
            interval="1m",
            timestamp=datetime.now(),
            open=Decimal("12345.678901234567"),
            high=Decimal("12346.678901234567"),
            low=Decimal("12344.678901234567"),
            close=Decimal("12345.000000000001"),
            volume=Decimal("0.123456789012345678"),
            quote_volume=Decimal("1524.157881356473")
        )
        data = kline.to_dict()
        assert isinstance(data["open"], float)
        assert isinstance(data["close"], float)
    
    def test_tick_with_trade_id(self):
        """测试Tick带交易ID"""
        tick = Tick(
            symbol="BTCUSDT",
            exchange="binance",
            timestamp=datetime.now(),
            price=Decimal("50000"),
            quantity=Decimal("1"),
            side="sell",
            trade_id="trade_12345"
        )
        data = tick.to_dict()
        assert data["trade_id"] == "trade_12345"
        assert data["side"] == "sell"


# ==================== Extended MySQLManager Tests ====================

class TestMySQLManagerExtended:
    """扩展MySQL管理器测试"""
    
    @patch('qf_database.mysql_manager.create_engine')
    def test_disconnect(self, mock_create_engine):
        """测试断开连接"""
        mock_engine = Mock()
        mock_create_engine.return_value = mock_engine
        
        manager = MySQLManager()
        manager._connected = True
        manager.disconnect()
        
        mock_engine.dispose.assert_called_once()
        assert manager.is_connected is False
    
    @patch('qf_database.mysql_manager.create_engine')
    def test_create_and_drop_tables(self, mock_create_engine):
        """测试创建和删除表"""
        mock_engine = Mock()
        mock_create_engine.return_value = mock_engine
        
        manager = MySQLManager()
        
        # 测试创建表
        with patch('qf_database.mysql_manager.Base.metadata') as mock_metadata:
            manager.create_tables()
            mock_metadata.create_all.assert_called_once_with(bind=mock_engine)
        
        # 测试删除表
        with patch('qf_database.mysql_manager.Base.metadata') as mock_metadata:
            manager.drop_tables()
            mock_metadata.drop_all.assert_called_once_with(bind=mock_engine)
    
    @patch('qf_database.mysql_manager.create_engine')
    def test_session_scope_rollback(self, mock_create_engine):
        """测试session_scope回滚"""
        mock_engine = Mock()
        mock_create_engine.return_value = mock_engine
        
        manager = MySQLManager()
        manager.SessionLocal = Mock()
        mock_session = Mock()
        manager.SessionLocal.return_value = mock_session
        mock_session.__enter__ = Mock(return_value=mock_session)
        mock_session.__exit__ = Mock(return_value=False)
        
        # 测试异常时回滚
        with pytest.raises(Exception):
            with manager.session_scope() as session:
                raise Exception("Test error")
        
        mock_session.rollback.assert_called_once()
        mock_session.close.assert_called_once()
    
    @patch('qf_database.mysql_manager.create_engine')
    def test_list_contracts_with_filters(self, mock_create_engine):
        """测试列出合约带筛选"""
        mock_engine = Mock()
        mock_create_engine.return_value = mock_engine
        
        manager = MySQLManager()
        manager.SessionLocal = Mock()
        mock_session = Mock()
        manager.SessionLocal.return_value = mock_session
        mock_session.__enter__ = Mock(return_value=mock_session)
        mock_session.__exit__ = Mock(return_value=False)
        
        # 模拟返回结果
        mock_contract1 = Mock()
        mock_contract1.symbol = "BTCUSDT"
        mock_contract1.exchange = "binance"
        mock_contract1.name = "Bitcoin/USDT"
        mock_contract1.contract_type = "spot"
        mock_contract1.base_asset = "BTC"
        mock_contract1.quote_asset = "USDT"
        mock_contract1.price_precision = 2
        mock_contract1.quantity_precision = 6
        mock_contract1.min_quantity = Decimal("0.00001")
        mock_contract1.max_quantity = Decimal("9000")
        mock_contract1.status = "active"
        mock_contract1.created_at = datetime.now()
        mock_contract1.updated_at = datetime.now()
        
        mock_session.execute.return_value.scalars.return_value.all.return_value = [mock_contract1]
        
        results = manager.list_contracts(exchange="binance", contract_type="spot", status="active")
        assert len(results) == 1
        assert results[0].symbol == "BTCUSDT"
    
    @patch('qf_database.mysql_manager.create_engine')
    def test_delete_contract_success(self, mock_create_engine):
        """测试删除合约成功"""
        mock_engine = Mock()
        mock_create_engine.return_value = mock_engine
        
        manager = MySQLManager()
        manager.SessionLocal = Mock()
        mock_session = Mock()
        manager.SessionLocal.return_value = mock_session
        mock_session.__enter__ = Mock(return_value=mock_session)
        mock_session.__exit__ = Mock(return_value=False)
        
        result = manager.delete_contract("BTCUSDT", "binance")
        assert result is True
    
    @patch('qf_database.mysql_manager.create_engine')
    def test_delete_contract_failure(self, mock_create_engine):
        """测试删除合约失败"""
        mock_engine = Mock()
        mock_engine.connect.side_effect = Exception("DB Error")
        mock_create_engine.return_value = mock_engine
        
        manager = MySQLManager()
        manager.SessionLocal = Mock()
        mock_session = Mock()
        mock_session.__enter__ = Mock(return_value=mock_session)
        mock_session.__exit__ = Mock(return_value=False)
        mock_session.execute.side_effect = Exception("Delete error")
        manager.SessionLocal.return_value = mock_session
        
        result = manager.delete_contract("BTCUSDT", "binance")
        assert result is False
    
    @patch('qf_database.mysql_manager.create_engine')
    def test_get_trade_not_found(self, mock_create_engine):
        """测试获取不存在的交易"""
        mock_engine = Mock()
        mock_create_engine.return_value = mock_engine
        
        manager = MySQLManager()
        manager.SessionLocal = Mock()
        mock_session = Mock()
        manager.SessionLocal.return_value = mock_session
        mock_session.__enter__ = Mock(return_value=mock_session)
        mock_session.__exit__ = Mock(return_value=False)
        mock_session.execute.return_value.scalar_one_or_none.return_value = None
        
        result = manager.get_trade(999)
        assert result is None
    
    @patch('qf_database.mysql_manager.create_engine')
    def test_query_trades_with_time_range(self, mock_create_engine):
        """测试按时间范围查询交易"""
        mock_engine = Mock()
        mock_create_engine.return_value = mock_engine
        
        manager = MySQLManager()
        manager.SessionLocal = Mock()
        mock_session = Mock()
        manager.SessionLocal.return_value = mock_session
        mock_session.__enter__ = Mock(return_value=mock_session)
        mock_session.__exit__ = Mock(return_value=False)
        mock_session.execute.return_value.scalars.return_value.all.return_value = []
        
        start = datetime(2024, 1, 1)
        end = datetime(2024, 1, 31)
        results = manager.query_trades(
            account_id="test",
            start_time=start,
            end_time=end,
            limit=50
        )
        assert results == []
    
    @patch('qf_database.mysql_manager.create_engine')
    def test_count_trades(self, mock_create_engine):
        """测试统计交易数量"""
        mock_engine = Mock()
        mock_create_engine.return_value = mock_engine
        
        manager = MySQLManager()
        manager.SessionLocal = Mock()
        mock_session = Mock()
        manager.SessionLocal.return_value = mock_session
        mock_session.__enter__ = Mock(return_value=mock_session)
        mock_session.__exit__ = Mock(return_value=False)
        
        # 模拟count返回
        mock_result = Mock()
        mock_result.scalar.return_value = 100
        mock_session.execute.return_value = mock_result
        
        count = manager.count_trades(account_id="test", symbol="BTCUSDT")
        assert count == 100
    
    @patch('qf_database.mysql_manager.create_engine')
    def test_get_account_not_found(self, mock_create_engine):
        """测试获取不存在的账户"""
        mock_engine = Mock()
        mock_create_engine.return_value = mock_engine
        
        manager = MySQLManager()
        manager.SessionLocal = Mock()
        mock_session = Mock()
        manager.SessionLocal.return_value = mock_session
        mock_session.__enter__ = Mock(return_value=mock_session)
        mock_session.__exit__ = Mock(return_value=False)
        mock_session.execute.return_value.scalar_one_or_none.return_value = None
        
        result = manager.get_account("non_existent", "binance", "BTC")
        assert result is None
    
    @patch('qf_database.mysql_manager.create_engine')
    def test_list_accounts_with_exchange_filter(self, mock_create_engine):
        """测试按交易所筛选账户"""
        mock_engine = Mock()
        mock_create_engine.return_value = mock_engine
        
        manager = MySQLManager()
        manager.SessionLocal = Mock()
        mock_session = Mock()
        manager.SessionLocal.return_value = mock_session
        mock_session.__enter__ = Mock(return_value=mock_session)
        mock_session.__exit__ = Mock(return_value=False)
        
        mock_account = Mock()
        mock_account.id = 1
        mock_account.account_id = "test_account"
        mock_account.exchange = "binance"
        mock_account.account_type = "spot"
        mock_account.asset = "BTC"
        mock_account.free = Decimal("1.0")
        mock_account.locked = Decimal("0.5")
        mock_account.total = Decimal("1.5")
        mock_account.created_at = datetime.now()
        mock_account.updated_at = datetime.now()
        
        mock_session.execute.return_value.scalars.return_value.all.return_value = [mock_account]
        
        results = manager.list_accounts(exchange="binance")
        assert len(results) == 1
        assert results[0].exchange == "binance"
    
    @patch('qf_database.mysql_manager.create_engine')
    def test_delete_account(self, mock_create_engine):
        """测试删除账户"""
        mock_engine = Mock()
        mock_create_engine.return_value = mock_engine
        
        manager = MySQLManager()
        manager.SessionLocal = Mock()
        mock_session = Mock()
        manager.SessionLocal.return_value = mock_session
        mock_session.__enter__ = Mock(return_value=mock_session)
        mock_session.__exit__ = Mock(return_value=False)
        
        result = manager.delete_account("test_account", "binance", "BTC")
        assert result is True


# ==================== Extended InfluxDBManager Tests ====================

class TestInfluxDBManagerExtended:
    """扩展InfluxDB管理器测试"""
    
    @patch('qf_database.influxdb_manager.InfluxDBClient')
    def test_disconnect(self, mock_influx_client):
        """测试断开连接"""
        mock_client = Mock()
        mock_write_api = Mock()
        mock_client.write_api.return_value = mock_write_api
        mock_influx_client.return_value = mock_client
        
        manager = InfluxDBManager()
        manager.client = mock_client
        manager.write_api = mock_write_api
        manager._connected = True
        
        manager.disconnect()
        
        mock_write_api.close.assert_called_once()
        mock_client.close.assert_called_once()
        assert manager.is_connected is False
    
    @patch('qf_database.influxdb_manager.InfluxDBClient')
    def test_ensure_bucket_exists(self, mock_influx_client):
        """测试确保存储桶存在"""
        mock_client = Mock()
        mock_buckets_api = Mock()
        mock_bucket = Mock()
        mock_buckets_api.find_bucket_by_name.return_value = mock_bucket
        mock_client.buckets_api.return_value = mock_buckets_api
        mock_influx_client.return_value = mock_client
        
        manager = InfluxDBManager()
        manager.client = mock_client
        
        result = manager.ensure_bucket()
        assert result is True
    
    @patch('qf_database.influxdb_manager.InfluxDBClient')
    def test_ensure_bucket_create_new(self, mock_influx_client):
        """测试创建新存储桶"""
        mock_client = Mock()
        mock_buckets_api = Mock()
        mock_buckets_api.find_bucket_by_name.return_value = None
        mock_client.buckets_api.return_value = mock_buckets_api
        mock_influx_client.return_value = mock_client
        
        manager = InfluxDBManager()
        manager.client = mock_client
        
        result = manager.ensure_bucket()
        assert result is True
        mock_buckets_api.create_bucket.assert_called_once()
    
    @patch('qf_database.influxdb_manager.InfluxDBClient')
    def test_get_kline(self, mock_influx_client):
        """测试获取单条K线"""
        mock_client = Mock()
        mock_query_api = Mock()
        mock_influx_client.return_value = mock_client
        
        manager = InfluxDBManager()
        manager.query_api = mock_query_api
        
        # 模拟返回结果
        mock_table = Mock()
        mock_record = Mock()
        mock_record.get_time.return_value = datetime(2024, 1, 1, 12, 0, 0)
        mock_record.values = {
            'symbol': 'BTCUSDT',
            'exchange': 'binance',
            'interval': '1h',
            'open': 50000.0,
            'high': 51000.0,
            'low': 49000.0,
            'close': 50500.0,
            'volume': 100.5,
            'quote_volume': 5075250.0,
            'trades': 1500
        }
        mock_table.records = [mock_record]
        mock_query_api.query.return_value = [mock_table]
        
        result = manager.get_kline(
            symbol="BTCUSDT",
            exchange="binance",
            interval="1h",
            timestamp=datetime(2024, 1, 1, 12, 0, 0)
        )
        assert result is not None
        assert result.symbol == "BTCUSDT"
    
    @patch('qf_database.influxdb_manager.InfluxDBClient')
    def test_get_latest_kline(self, mock_influx_client):
        """测试获取最新K线"""
        mock_client = Mock()
        mock_query_api = Mock()
        mock_influx_client.return_value = mock_client
        
        manager = InfluxDBManager()
        manager.query_api = mock_query_api
        
        # 模拟返回结果
        mock_table = Mock()
        mock_record = Mock()
        mock_record.get_time.return_value = datetime(2024, 1, 1, 12, 0, 0)
        mock_record.values = {
            'symbol': 'BTCUSDT',
            'exchange': 'binance',
            'interval': '1h',
            'open': 50000.0,
            'high': 51000.0,
            'low': 49000.0,
            'close': 50500.0,
            'volume': 100.5,
            'quote_volume': 5075250.0,
            'trades': 1500
        }
        mock_table.records = [mock_record]
        mock_query_api.query.return_value = [mock_table]
        
        result = manager.get_latest_kline("BTCUSDT", "binance", "1h")
        assert result is not None
    
    @patch('qf_database.influxdb_manager.InfluxDBClient')
    def test_save_ticks_batch(self, mock_influx_client):
        """测试批量保存Tick"""
        mock_client = Mock()
        mock_write_api = Mock()
        mock_influx_client.return_value = mock_client
        
        manager = InfluxDBManager()
        manager.write_api = mock_write_api
        
        ticks = [
            Tick(
                symbol="BTCUSDT",
                exchange="binance",
                timestamp=datetime(2024, 1, 1, 12, 0, 0),
                price=Decimal("50000"),
                quantity=Decimal("0.1"),
                side="buy",
                trade_id="tick_001"
            ),
            Tick(
                symbol="BTCUSDT",
                exchange="binance",
                timestamp=datetime(2024, 1, 1, 12, 0, 1),
                price=Decimal("50001"),
                quantity=Decimal("0.2"),
                side="sell",
                trade_id="tick_002"
            )
        ]
        
        result = manager.save_ticks(ticks)
        assert result is True
    
    @patch('qf_database.influxdb_manager.InfluxDBClient')
    def test_get_latest_tick(self, mock_influx_client):
        """测试获取最新Tick"""
        mock_client = Mock()
        mock_query_api = Mock()
        mock_influx_client.return_value = mock_client
        
        manager = InfluxDBManager()
        manager.query_api = mock_query_api
        
        # 模拟返回结果
        mock_table = Mock()
        mock_record = Mock()
        mock_record.get_time.return_value = datetime(2024, 1, 1, 12, 0, 0)
        mock_record.values = {
            'symbol': 'BTCUSDT',
            'exchange': 'binance',
            'side': 'buy',
            'price': 50000.0,
            'quantity': 0.5,
            'trade_id': 'tick_001'
        }
        mock_table.records = [mock_record]
        mock_query_api.query.return_value = [mock_table]
        
        result = manager.get_latest_tick("BTCUSDT", "binance")
        assert result is not None
    
    @patch('qf_database.influxdb_manager.InfluxDBClient')
    def test_delete_ticks(self, mock_influx_client):
        """测试删除Tick数据"""
        mock_client = Mock()
        mock_delete_api = Mock()
        mock_influx_client.return_value = mock_client
        
        manager = InfluxDBManager()
        manager.delete_api = mock_delete_api
        
        result = manager.delete_ticks(
            symbol="BTCUSDT",
            exchange="binance",
            start_time=datetime(2024, 1, 1),
            end_time=datetime(2024, 1, 2)
        )
        assert result is True


# ==================== Extended RedisManager Tests ====================

class TestRedisManagerExtended:
    """扩展Redis管理器测试"""
    
    @patch('qf_database.redis_manager.redis.ConnectionPool')
    @patch('qf_database.redis_manager.redis.Redis')
    def test_ping(self, mock_redis_class, mock_pool):
        """测试ping方法"""
        mock_client = Mock()
        mock_client.ping.return_value = True
        mock_redis_class.return_value = mock_client
        
        manager = RedisManager()
        manager.client = mock_client
        
        result = manager.ping()
        assert result is True
        
        # 测试ping失败
        mock_client.ping.side_effect = Exception("Connection error")
        result = manager.ping()
        assert result is False
    
    @patch('qf_database.redis_manager.redis.ConnectionPool')
    @patch('qf_database.redis_manager.redis.Redis')
    def test_set_with_pickle(self, mock_redis_class, mock_pool):
        """测试使用pickle序列化设置"""
        mock_client = Mock()
        mock_redis_class.return_value = mock_client
        
        manager = RedisManager()
        manager.client = mock_client
        
        import pickle
        data = {"key": "value", "number": 123}
        pickled = pickle.dumps(data)
        
        result = manager.set("test_key", data, ttl=60, serialize="pickle")
        assert result is True
        mock_client.setex.assert_called_once()
    
    @patch('qf_database.redis_manager.redis.ConnectionPool')
    @patch('qf_database.redis_manager.redis.Redis')
    def test_get_raw(self, mock_redis_class, mock_pool):
        """测试获取原始值"""
        mock_client = Mock()
        mock_client.get.return_value = b"raw_value"
        mock_redis_class.return_value = mock_client
        
        manager = RedisManager()
        manager.client = mock_client
        
        result = manager.get("test_key", deserialize="raw")
        assert result == b"raw_value"
    
    @patch('qf_database.redis_manager.redis.ConnectionPool')
    @patch('qf_database.redis_manager.redis.Redis')
    def test_exists(self, mock_redis_class, mock_pool):
        """测试键存在检查"""
        mock_client = Mock()
        mock_client.exists.return_value = 1
        mock_redis_class.return_value = mock_client
        
        manager = RedisManager()
        manager.client = mock_client
        
        result = manager.exists("test_key")
        assert result is True
        
        mock_client.exists.return_value = 0
        result = manager.exists("non_existent")
        assert result is False
    
    @patch('qf_database.redis_manager.redis.ConnectionPool')
    @patch('qf_database.redis_manager.redis.Redis')
    def test_ttl_and_expire(self, mock_redis_class, mock_pool):
        """测试TTL和过期设置"""
        mock_client = Mock()
        mock_client.ttl.return_value = 60
        mock_client.expire.return_value = True
        mock_redis_class.return_value = mock_client
        
        manager = RedisManager()
        manager.client = mock_client
        
        ttl = manager.ttl("test_key")
        assert ttl == 60
        
        result = manager.expire("test_key", 120)
        assert result is True
    
    @patch('qf_database.redis_manager.redis.ConnectionPool')
    @patch('qf_database.redis_manager.redis.Redis')
    def test_cache_ticks_batch(self, mock_redis_class, mock_pool):
        """测试批量缓存Tick"""
        mock_client = Mock()
        mock_redis_class.return_value = mock_client
        
        manager = RedisManager()
        manager.client = mock_client
        
        ticks = [
            Tick(
                symbol="BTCUSDT",
                exchange="binance",
                timestamp=datetime(2024, 1, 1, 12, 0, 0),
                price=Decimal("50000"),
                quantity=Decimal("0.1"),
                side="buy",
                trade_id="tick_001"
            ),
            Tick(
                symbol="ETHUSDT",
                exchange="binance",
                timestamp=datetime(2024, 1, 1, 12, 0, 0),
                price=Decimal("3000"),
                quantity=Decimal("1.0"),
                side="sell",
                trade_id="tick_002"
            )
        ]
        
        result = manager.cache_ticks_batch(ticks, ttl=60)
        assert result is True
    
    @patch('qf_database.redis_manager.redis.ConnectionPool')
    @patch('qf_database.redis_manager.redis.Redis')
    def test_get_cached_kline_not_found(self, mock_redis_class, mock_pool):
        """测试获取不存在的K线缓存"""
        mock_client = Mock()
        mock_client.get.return_value = None
        mock_redis_class.return_value = mock_client
        
        manager = RedisManager()
        manager.client = mock_client
        
        result = manager.get_cached_kline("BTCUSDT", "binance", "1h")
        assert result is None
    
    @patch('qf_database.redis_manager.redis.ConnectionPool')
    @patch('qf_database.redis_manager.redis.Redis')
    def test_cache_ticker(self, mock_redis_class, mock_pool):
        """测试缓存Ticker"""
        mock_client = Mock()
        mock_redis_class.return_value = mock_client
        
        manager = RedisManager()
        manager.client = mock_client
        
        ticker_data = {
            "symbol": "BTCUSDT",
            "price": 50000.0,
            "change_24h": 2.5
        }
        
        result = manager.cache_ticker("BTCUSDT", "binance", ticker_data, ttl=10)
        assert result is True
    
    @patch('qf_database.redis_manager.redis.ConnectionPool')
    @patch('qf_database.redis_manager.redis.Redis')
    def test_cache_orderbook(self, mock_redis_class, mock_pool):
        """测试缓存OrderBook"""
        mock_client = Mock()
        mock_redis_class.return_value = mock_client
        
        manager = RedisManager()
        manager.client = mock_client
        
        orderbook_data = {
            "bids": [["50000", "1.0"], ["49999", "2.0"]],
            "asks": [["50001", "1.5"], ["50002", "2.5"]]
        }
        
        result = manager.cache_orderbook("BTCUSDT", "binance", orderbook_data, ttl=5)
        assert result is True
    
    @patch('qf_database.redis_manager.redis.ConnectionPool')
    @patch('qf_database.redis_manager.redis.Redis')
    def test_cache_and_get_position(self, mock_redis_class, mock_pool):
        """测试持仓缓存"""
        mock_client = Mock()
        mock_redis_class.return_value = mock_client
        
        manager = RedisManager()
        manager.client = mock_client
        
        position_data = {
            "symbol": "BTCUSDT",
            "side": "long",
            "size": 1.5,
            "entry_price": 48000.0
        }
        
        # 测试缓存
        result = manager.cache_position("account_1", "BTCUSDT", position_data, ttl=60)
        assert result is True
        
        # 测试获取
        mock_client.get.return_value = json.dumps(position_data)
        result = manager.get_cached_position("account_1", "BTCUSDT")
        assert result is not None
        assert result["symbol"] == "BTCUSDT"
    
    @patch('qf_database.redis_manager.redis.ConnectionPool')
    @patch('qf_database.redis_manager.redis.Redis')
    def test_delete_position(self, mock_redis_class, mock_pool):
        """测试删除持仓缓存"""
        mock_client = Mock()
        mock_redis_class.return_value = mock_client
        
        manager = RedisManager()
        manager.client = mock_client
        
        result = manager.delete_position("account_1", "BTCUSDT")
        assert result is True
    
    @patch('qf_database.redis_manager.redis.ConnectionPool')
    @patch('qf_database.redis_manager.redis.Redis')
    def test_rate_limit_exceeded(self, mock_redis_class, mock_pool):
        """测试限流超过限制"""
        mock_client = Mock()
        mock_client.get.return_value = b"100"  # 已达上限
        mock_client.ttl.return_value = 30
        mock_redis_class.return_value = mock_client
        
        manager = RedisManager()
        manager.client = mock_client
        
        allowed, count, ttl = manager.rate_limit_check("api_key", max_requests=100, window_seconds=60)
        assert allowed is False
        assert count == 100
    
    @patch('qf_database.redis_manager.redis.ConnectionPool')
    @patch('qf_database.redis_manager.redis.Redis')
    def test_reset_rate_limit(self, mock_redis_class, mock_pool):
        """测试重置限流"""
        mock_client = Mock()
        mock_redis_class.return_value = mock_client
        
        manager = RedisManager()
        manager.client = mock_client
        
        result = manager.reset_rate_limit("api_key")
        assert result is True
    
    @patch('qf_database.redis_manager.redis.ConnectionPool')
    @patch('qf_database.redis_manager.redis.Redis')
    def test_acquire_lock_blocking(self, mock_redis_class, mock_pool):
        """测试阻塞模式获取锁"""
        mock_client = Mock()
        mock_client.set.return_value = True
        mock_redis_class.return_value = mock_client
        
        manager = RedisManager()
        manager.client = mock_client
        
        result = manager.acquire_lock("test_lock", ttl=30, blocking=True, blocking_timeout=5)
        assert result is True
    
    @patch('qf_database.redis_manager.redis.ConnectionPool')
    @patch('qf_database.redis_manager.redis.Redis')
    def test_keys(self, mock_redis_class, mock_pool):
        """测试获取键列表"""
        mock_client = Mock()
        mock_client.keys.return_value = [b"key1", b"key2"]
        mock_redis_class.return_value = mock_client
        
        manager = RedisManager()
        manager.client = mock_client
        
        result = manager.keys("test:*")
        assert len(result) == 2
        assert "key1" in result
    
    @patch('qf_database.redis_manager.redis.ConnectionPool')
    @patch('qf_database.redis_manager.redis.Redis')
    def test_flush_db(self, mock_redis_class, mock_pool):
        """测试清空数据库"""
        mock_client = Mock()
        mock_redis_class.return_value = mock_client
        
        manager = RedisManager()
        manager.client = mock_client
        
        result = manager.flush_db()
        assert result is True
    
    @patch('qf_database.redis_manager.redis.ConnectionPool')
    @patch('qf_database.redis_manager.redis.Redis')
    def test_info(self, mock_redis_class, mock_pool):
        """测试获取服务器信息"""
        mock_client = Mock()
        mock_client.info.return_value = {
            b"redis_version": b"7.0.0",
            b"used_memory": b"1000000"
        }
        mock_redis_class.return_value = mock_client
        
        manager = RedisManager()
        manager.client = mock_client
        
        result = manager.info()
        assert "redis_version" in result


# ==================== Extended DatabaseManager Tests ====================

class TestDatabaseManagerExtended:
    """扩展统一数据库管理器测试"""
    
    @patch.object(MySQLManager, '__init__', return_value=None)
    @patch.object(InfluxDBManager, '__init__', return_value=None)
    @patch.object(RedisManager, '__init__', return_value=None)
    @patch.object(MySQLManager, 'health_check', return_value=(False, 0, "Connection refused"))
    @patch.object(InfluxDBManager, 'health_check', return_value=(False, 0, "Connection refused"))
    @patch.object(RedisManager, 'health_check', return_value=(False, 0, "Connection refused"))
    def test_check_health_unhealthy(self, mock_redis, mock_influx, mock_mysql, *args):
        """测试健康检查 - 全部不健康"""
        manager = DatabaseManager()
        health = manager.check_health()
        
        assert health["overall"] == "unhealthy"
        assert health["mysql"]["connected"] is False
        assert health["influxdb"]["connected"] is False
        assert health["redis"]["connected"] is False
    
    @patch.object(MySQLManager, '__init__', return_value=None)
    @patch.object(InfluxDBManager, '__init__', return_value=None)
    @patch.object(RedisManager, '__init__', return_value=None)
    @patch.object(MySQLManager, 'health_check', return_value=(True, 1.5, None))
    @patch.object(InfluxDBManager, 'health_check', return_value=(True, 2.0, None))
    @patch.object(RedisManager, 'health_check', return_value=(True, 0.5, None))
    def test_check_health_healthy(self, mock_redis, mock_influx, mock_mysql, *args):
        """测试健康检查 - 全部健康"""
        manager = DatabaseManager()
        health = manager.check_health()
        
        assert health["overall"] == "healthy"
        assert health["mysql"]["connected"] is True
        assert health["influxdb"]["connected"] is True
        assert health["redis"]["connected"] is True
    
    @patch.object(MySQLManager, '__init__', return_value=None)
    @patch.object(InfluxDBManager, '__init__', return_value=None)
    @patch.object(RedisManager, '__init__', return_value=None)
    @patch.object(MySQLManager, 'health_check', return_value=(True, 1.5, None))
    @patch.object(InfluxDBManager, 'health_check', return_value=(False, 0, "Connection refused"))
    @patch.object(RedisManager, 'health_check', return_value=(False, 0, "Connection refused"))
    def test_check_health_degraded(self, mock_redis, mock_influx, mock_mysql, *args):
        """测试健康检查 - 降级"""
        manager = DatabaseManager()
        health = manager.check_health()
        
        assert health["overall"] == "degraded"
    
    @patch.object(MySQLManager, '__init__', return_value=None)
    @patch.object(InfluxDBManager, '__init__', return_value=None)
    @patch.object(RedisManager, '__init__', return_value=None)
    @patch.object(MySQLManager, 'list_contracts', return_value=[])
    def test_list_contracts_shortcut(self, mock_list, *args):
        """测试列出合约快捷方法"""
        manager = DatabaseManager()
        results = manager.list_contracts(exchange="binance")
        
        mock_list.assert_called_once_with("binance", None, "active")
    
    @patch.object(MySQLManager, '__init__', return_value=None)
    @patch.object(InfluxDBManager, '__init__', return_value=None)
    @patch.object(RedisManager, '__init__', return_value=None)
    @patch.object(MySQLManager, 'save_trade', return_value=True)
    def test_save_trade_shortcut(self, mock_save, *args):
        """测试保存交易快捷方法"""
        manager = DatabaseManager()
        trade = Trade(
            symbol="BTCUSDT",
            exchange="binance",
            side="buy",
            order_type="limit",
            price=Decimal("50000"),
            quantity=Decimal("0.1"),
            amount=Decimal("5000"),
            account_id="test"
        )
        result = manager.save_trade(trade)
        
        assert result is True
        mock_save.assert_called_once_with(trade)
    
    @patch.object(MySQLManager, '__init__', return_value=None)
    @patch.object(InfluxDBManager, '__init__', return_value=None)
    @patch.object(RedisManager, '__init__', return_value=None)
    @patch.object(MySQLManager, 'get_trade', return_value=None)
    def test_get_trade_shortcut(self, mock_get, *args):
        """测试获取交易快捷方法"""
        manager = DatabaseManager()
        result = manager.get_trade(123)
        
        mock_get.assert_called_once_with(123)
    
    @patch.object(MySQLManager, '__init__', return_value=None)
    @patch.object(InfluxDBManager, '__init__', return_value=None)
    @patch.object(RedisManager, '__init__', return_value=None)
    @patch.object(MySQLManager, 'query_trades', return_value=[])
    def test_query_trades_shortcut(self, mock_query, *args):
        """测试查询交易快捷方法"""
        manager = DatabaseManager()
        start = datetime(2024, 1, 1)
        end = datetime(2024, 1, 31)
        
        results = manager.query_trades(
            account_id="test",
            symbol="BTCUSDT",
            start_time=start,
            end_time=end,
            limit=50
        )
        
        mock_query.assert_called_once()
    
    @patch.object(MySQLManager, '__init__', return_value=None)
    @patch.object(InfluxDBManager, '__init__', return_value=None)
    @patch.object(RedisManager, '__init__', return_value=None)
    @patch.object(MySQLManager, 'save_account', return_value=True)
    def test_save_account_shortcut(self, mock_save, *args):
        """测试保存账户快捷方法"""
        manager = DatabaseManager()
        account = Account(
            account_id="test",
            exchange="binance",
            account_type="spot",
            asset="BTC",
            free=Decimal("1.0"),
            locked=Decimal("0.5")
        )
        result = manager.save_account(account)
        
        assert result is True
        mock_save.assert_called_once_with(account)
    
    @patch.object(MySQLManager, '__init__', return_value=None)
    @patch.object(InfluxDBManager, '__init__', return_value=None)
    @patch.object(RedisManager, '__init__', return_value=None)
    @patch.object(MySQLManager, 'get_account', return_value=None)
    def test_get_account_shortcut(self, mock_get, *args):
        """测试获取账户快捷方法"""
        manager = DatabaseManager()
        result = manager.get_account("test", "binance", "BTC")
        
        mock_get.assert_called_once_with("test", "binance", "BTC")
    
    @patch.object(MySQLManager, '__init__', return_value=None)
    @patch.object(InfluxDBManager, '__init__', return_value=None)
    @patch.object(RedisManager, '__init__', return_value=None)
    @patch.object(MySQLManager, 'list_accounts', return_value=[])
    def test_list_accounts_shortcut(self, mock_list, *args):
        """测试列出账户快捷方法"""
        manager = DatabaseManager()
        results = manager.list_accounts(account_id="test")
        
        mock_list.assert_called_once_with("test", None)
    
    @patch.object(MySQLManager, '__init__', return_value=None)
    @patch.object(InfluxDBManager, '__init__', return_value=None)
    @patch.object(RedisManager, '__init__', return_value=None)
    @patch.object(InfluxDBManager, 'save_klines', return_value=True)
    @patch.object(RedisManager, 'cache_kline')
    def test_save_klines_without_cache(self, mock_redis, mock_influx, *args):
        """测试保存K线不缓存"""
        manager = DatabaseManager()
        klines = [
            Kline(
                symbol="BTCUSDT",
                exchange="binance",
                interval="1h",
                timestamp=datetime(2024, 1, 1, 12, 0, 0),
                open=Decimal("50000"),
                high=Decimal("51000"),
                low=Decimal("49000"),
                close=Decimal("50500"),
                volume=Decimal("100"),
                quote_volume=Decimal("5050000"),
                trades=1000
            )
        ]
        
        result = manager.save_klines(klines, cache=False)
        
        assert result is True
        mock_influx.assert_called_once()
        mock_redis.assert_not_called()
    
    @patch.object(MySQLManager, '__init__', return_value=None)
    @patch.object(InfluxDBManager, '__init__', return_value=None)
    @patch.object(RedisManager, '__init__', return_value=None)
    @patch.object(RedisManager, 'get_cached_kline', return_value=None)
    @patch.object(InfluxDBManager, 'query_klines', return_value=[])
    def test_query_klines_shortcut(self, mock_query, mock_redis, *args):
        """测试查询K线快捷方法"""
        manager = DatabaseManager()
        start = datetime(2024, 1, 1)
        
        results = manager.query_klines(
            symbol="BTCUSDT",
            exchange="binance",
            interval="1h",
            start_time=start,
            limit=500
        )
        
        mock_query.assert_called_once()
    
    @patch.object(MySQLManager, '__init__', return_value=None)
    @patch.object(InfluxDBManager, '__init__', return_value=None)
    @patch.object(RedisManager, '__init__', return_value=None)
    @patch.object(InfluxDBManager, 'save_ticks', return_value=True)
    @patch.object(RedisManager, 'cache_ticks_batch')
    def test_save_ticks_without_cache(self, mock_redis, mock_influx, *args):
        """测试保存Tick不缓存"""
        manager = DatabaseManager()
        ticks = [
            Tick(
                symbol="BTCUSDT",
                exchange="binance",
                timestamp=datetime(2024, 1, 1, 12, 0, 0),
                price=Decimal("50000"),
                quantity=Decimal("0.1"),
                side="buy",
                trade_id="tick_001"
            )
        ]
        
        result = manager.save_ticks(ticks, cache=False)
        
        assert result is True
        mock_redis.assert_not_called()
    
    @patch.object(MySQLManager, '__init__', return_value=None)
    @patch.object(InfluxDBManager, '__init__', return_value=None)
    @patch.object(RedisManager, '__init__', return_value=None)
    @patch.object(RedisManager, 'get_cached_tick', return_value=None)
    @patch.object(InfluxDBManager, 'query_ticks', return_value=[])
    def test_query_ticks_shortcut(self, mock_query, mock_redis, *args):
        """测试查询Tick快捷方法"""
        manager = DatabaseManager()
        start = datetime(2024, 1, 1)
        
        results = manager.query_ticks(
            symbol="BTCUSDT",
            exchange="binance",
            start_time=start,
            limit=1000
        )
        
        mock_query.assert_called_once()
    
    @patch.object(MySQLManager, '__init__', return_value=None)
    @patch.object(InfluxDBManager, '__init__', return_value=None)
    @patch.object(RedisManager, '__init__', return_value=None)
    @patch.object(RedisManager, 'cache_ticker', return_value=True)
    def test_cache_ticker_shortcut(self, mock_cache, *args):
        """测试缓存Ticker快捷方法"""
        manager = DatabaseManager()
        ticker_data = {"price": 50000.0}
        
        result = manager.cache_ticker("BTCUSDT", "binance", ticker_data, ttl=10)
        
        assert result is True
        mock_cache.assert_called_once_with("BTCUSDT", "binance", ticker_data, 10)
    
    @patch.object(MySQLManager, '__init__', return_value=None)
    @patch.object(InfluxDBManager, '__init__', return_value=None)
    @patch.object(RedisManager, '__init__', return_value=None)
    @patch.object(RedisManager, 'get_cached_ticker', return_value=None)
    def test_get_cached_ticker_shortcut(self, mock_get, *args):
        """测试获取缓存Ticker快捷方法"""
        manager = DatabaseManager()
        result = manager.get_cached_ticker("BTCUSDT", "binance")
        
        mock_get.assert_called_once_with("BTCUSDT", "binance")
    
    @patch.object(MySQLManager, '__init__', return_value=None)
    @patch.object(InfluxDBManager, '__init__', return_value=None)
    @patch.object(RedisManager, '__init__', return_value=None)
    @patch.object(RedisManager, 'cache_orderbook', return_value=True)
    def test_cache_orderbook_shortcut(self, mock_cache, *args):
        """测试缓存OrderBook快捷方法"""
        manager = DatabaseManager()
        orderbook_data = {"bids": [], "asks": []}
        
        result = manager.cache_orderbook("BTCUSDT", "binance", orderbook_data, ttl=5)
        
        assert result is True
    
    @patch.object(MySQLManager, '__init__', return_value=None)
    @patch.object(InfluxDBManager, '__init__', return_value=None)
    @patch.object(RedisManager, '__init__', return_value=None)
    @patch.object(RedisManager, 'get_cached_orderbook', return_value=None)
    def test_get_cached_orderbook_shortcut(self, mock_get, *args):
        """测试获取缓存OrderBook快捷方法"""
        manager = DatabaseManager()
        result = manager.get_cached_orderbook("BTCUSDT", "binance")
        
        mock_get.assert_called_once_with("BTCUSDT", "binance")
    
    @patch.object(MySQLManager, '__init__', return_value=None)
    @patch.object(InfluxDBManager, '__init__', return_value=None)
    @patch.object(RedisManager, '__init__', return_value=None)
    @patch.object(MySQLManager, 'create_tables')
    def test_init_mysql_tables(self, mock_create, *args):
        """测试初始化MySQL表"""
        manager = DatabaseManager()
        manager.init_mysql_tables()
        
        mock_create.assert_called_once()


# ==================== Error Handling Tests ====================

class TestErrorHandling:
    """错误处理测试"""
    
    @patch('qf_database.mysql_manager.create_engine')
    def test_mysql_save_contract_exception(self, mock_create_engine):
        """测试MySQL保存合约异常"""
        mock_engine = Mock()
        mock_create_engine.return_value = mock_engine
        
        manager = MySQLManager()
        manager.SessionLocal = Mock()
        mock_session = Mock()
        manager.SessionLocal.return_value = mock_session
        mock_session.__enter__ = Mock(return_value=mock_session)
        mock_session.__exit__ = Mock(return_value=False)
        mock_session.execute.side_effect = Exception("DB Error")
        
        contract = Contract(
            symbol="BTCUSDT",
            exchange="binance",
            name="Bitcoin/USDT",
            contract_type="spot",
            base_asset="BTC",
            quote_asset="USDT"
        )
        
        result = manager.save_contract(contract)
        assert result is False
    
    @patch('qf_database.influxdb_manager.InfluxDBClient')
    def test_influx_save_kline_exception(self, mock_influx_client):
        """测试InfluxDB保存K线异常"""
        mock_client = Mock()
        mock_write_api = Mock()
        mock_write_api.write.side_effect = Exception("Write Error")
        mock_client.write_api.return_value = mock_write_api
        mock_influx_client.return_value = mock_client
        
        manager = InfluxDBManager()
        manager.write_api = mock_write_api
        
        kline = Kline(
            symbol="BTCUSDT",
            exchange="binance",
            interval="1h",
            timestamp=datetime.now(),
            open=Decimal("50000"),
            high=Decimal("51000"),
            low=Decimal("49000"),
            close=Decimal("50500"),
            volume=Decimal("100"),
            quote_volume=Decimal("5050000"),
            trades=1000
        )
        
        result = manager.save_kline(kline)
        assert result is False
    
    @patch('qf_database.redis_manager.redis.ConnectionPool')
    @patch('qf_database.redis_manager.redis.Redis')
    def test_redis_set_exception(self, mock_redis_class, mock_pool):
        """测试Redis设置异常"""
        mock_client = Mock()
        mock_client.setex.side_effect = Exception("Redis Error")
        mock_redis_class.return_value = mock_client
        
        manager = RedisManager()
        manager.client = mock_client
        
        result = manager.set("key", "value", ttl=60)
        assert result is False