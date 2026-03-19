"""
qf-database 模块测试 - 最终补充测试以达到80%覆盖率
"""
import pytest
from datetime import datetime, timedelta
from decimal import Decimal
from unittest.mock import Mock, patch, MagicMock, call

# 导入被测模块
from qf_database.models import Contract, Trade, Account, Kline, Tick
from qf_database.mysql_manager import MySQLManager
from qf_database.influxdb_manager import InfluxDBManager
from qf_database.redis_manager import RedisManager
from qf_database.database_manager import DatabaseManager, DatabaseConfig


# ==================== Additional Models Tests ====================

class TestModelsAdditional:
    """补充模型测试"""
    
    def test_trade_with_id_and_strategy(self):
        """测试带ID和策略的交易"""
        trade = Trade(
            id=123,
            symbol="BTCUSDT",
            exchange="binance",
            side="sell",
            order_type="market",
            price=Decimal("51000"),
            quantity=Decimal("0.05"),
            amount=Decimal("2550"),
            fee=Decimal("2.55"),
            fee_asset="USDT",
            status="filled",
            order_id="order_123",
            trade_id="trade_456",
            account_id="acc_789",
            strategy_id="strat_001",
            created_at=datetime.now(),
            updated_at=datetime.now()
        )
        data = trade.to_dict()
        assert data["id"] == 123
        assert data["strategy_id"] == "strat_001"
    
    def test_account_total_property(self):
        """测试账户总资产计算"""
        account = Account(
            account_id="test",
            exchange="binance",
            account_type="spot",
            asset="BTC",
            free=Decimal("1.0"),
            locked=Decimal("0.5"),
            total=Decimal("1.5")
        )
        assert account.total == Decimal("1.5")
        data = account.to_dict()
        assert data["total"] == "1.5"


# ==================== Additional MySQLManager Tests ====================

class TestMySQLManagerAdditional:
    """补充MySQL管理器测试"""
    
    @patch('qf_database.mysql_manager.create_engine')
    def test_save_contract_update_existing(self, mock_create_engine):
        """测试更新已存在的合约"""
        mock_engine = Mock()
        mock_create_engine.return_value = mock_engine
        
        manager = MySQLManager()
        manager.SessionLocal = Mock()
        mock_session = Mock()
        manager.SessionLocal.return_value = mock_session
        mock_session.__enter__ = Mock(return_value=mock_session)
        mock_session.__exit__ = Mock(return_value=False)
        
        # 模拟已存在的合约
        existing = Mock()
        existing.name = "Old Name"
        mock_session.execute.return_value.scalar_one_or_none.return_value = existing
        
        contract = Contract(
            symbol="BTCUSDT",
            exchange="binance",
            name="New Name",
            contract_type="spot",
            base_asset="BTC",
            quote_asset="USDT"
        )
        
        result = manager.save_contract(contract)
        assert result is True
        assert existing.name == "New Name"
    
    @patch('qf_database.mysql_manager.create_engine')
    def test_query_trades_with_all_filters(self, mock_create_engine):
        """测试查询交易使用所有筛选条件"""
        mock_engine = Mock()
        mock_create_engine.return_value = mock_engine
        
        manager = MySQLManager()
        manager.SessionLocal = Mock()
        mock_session = Mock()
        manager.SessionLocal.return_value = mock_session
        mock_session.__enter__ = Mock(return_value=mock_session)
        mock_session.__exit__ = Mock(return_value=False)
        mock_session.execute.return_value.scalars.return_value.all.return_value = []
        
        results = manager.query_trades(
            account_id="acc1",
            symbol="BTCUSDT",
            exchange="binance",
            side="buy",
            status="filled",
            start_time=datetime(2024, 1, 1),
            end_time=datetime(2024, 1, 31),
            strategy_id="strat1",
            limit=50,
            offset=10
        )
        assert results == []
    
    @patch('qf_database.mysql_manager.create_engine')
    def test_query_trades_exception(self, mock_create_engine):
        """测试查询交易异常"""
        mock_engine = Mock()
        mock_create_engine.return_value = mock_engine
        
        manager = MySQLManager()
        manager.SessionLocal = Mock()
        mock_session = Mock()
        manager.SessionLocal.return_value = mock_session
        mock_session.__enter__ = Mock(return_value=mock_session)
        mock_session.__exit__ = Mock(return_value=False)
        mock_session.execute.side_effect = Exception("Query error")
        
        results = manager.query_trades(account_id="test")
        assert results == []
    
    @patch('qf_database.mysql_manager.create_engine')
    def test_count_trades_exception(self, mock_create_engine):
        """测试统计交易数量异常"""
        mock_engine = Mock()
        mock_create_engine.return_value = mock_engine
        
        manager = MySQLManager()
        manager.SessionLocal = Mock()
        mock_session = Mock()
        manager.SessionLocal.return_value = mock_session
        mock_session.__enter__ = Mock(return_value=mock_session)
        mock_session.__exit__ = Mock(return_value=False)
        mock_session.execute.side_effect = Exception("Count error")
        
        count = manager.count_trades()
        assert count == 0
    
    @patch('qf_database.mysql_manager.create_engine')
    def test_save_account_update_existing(self, mock_create_engine):
        """测试更新已存在的账户"""
        mock_engine = Mock()
        mock_create_engine.return_value = mock_engine
        
        manager = MySQLManager()
        manager.SessionLocal = Mock()
        mock_session = Mock()
        manager.SessionLocal.return_value = mock_session
        mock_session.__enter__ = Mock(return_value=mock_session)
        mock_session.__exit__ = Mock(return_value=False)
        
        # 模拟已存在的账户
        existing = Mock()
        existing.free = Decimal("0")
        existing.locked = Decimal("0")
        existing.total = Decimal("0")
        mock_session.execute.return_value.scalar_one_or_none.return_value = existing
        
        account = Account(
            account_id="test",
            exchange="binance",
            account_type="spot",
            asset="BTC",
            free=Decimal("2.0"),
            locked=Decimal("0.5")
        )
        
        result = manager.save_account(account)
        assert result is True
        assert existing.free == Decimal("2.0")
        assert existing.total == Decimal("2.5")  # free + locked
    
    @patch('qf_database.mysql_manager.create_engine')
    def test_list_accounts_exception(self, mock_create_engine):
        """测试列出账户异常"""
        mock_engine = Mock()
        mock_create_engine.return_value = mock_engine
        
        manager = MySQLManager()
        manager.SessionLocal = Mock()
        mock_session = Mock()
        manager.SessionLocal.return_value = mock_session
        mock_session.__enter__ = Mock(return_value=mock_session)
        mock_session.__exit__ = Mock(return_value=False)
        mock_session.execute.side_effect = Exception("List error")
        
        results = manager.list_accounts()
        assert results == []
    
    @patch('qf_database.mysql_manager.create_engine')
    def test_delete_account_exception(self, mock_create_engine):
        """测试删除账户异常"""
        mock_engine = Mock()
        mock_create_engine.return_value = mock_engine
        
        manager = MySQLManager()
        manager.SessionLocal = Mock()
        mock_session = Mock()
        manager.SessionLocal.return_value = mock_session
        mock_session.__enter__ = Mock(return_value=mock_session)
        mock_session.__exit__ = Mock(return_value=False)
        mock_session.execute.side_effect = Exception("Delete error")
        
        result = manager.delete_account("test", "binance", "BTC")
        assert result is False


# ==================== Additional InfluxDBManager Tests ====================

class TestInfluxDBManagerAdditional:
    """补充InfluxDB管理器测试"""
    
    @patch('qf_database.influxdb_manager.InfluxDBClient')
    def test_ensure_bucket_exception(self, mock_influx_client):
        """测试确保存储桶异常"""
        mock_client = Mock()
        mock_client.buckets_api.side_effect = Exception("Bucket error")
        mock_influx_client.return_value = mock_client
        
        manager = InfluxDBManager()
        manager.client = mock_client
        
        result = manager.ensure_bucket()
        assert result is False
    
    @patch('qf_database.influxdb_manager.InfluxDBClient')
    def test_save_klines_exception(self, mock_influx_client):
        """测试批量保存K线异常"""
        mock_client = Mock()
        mock_write_api = Mock()
        mock_write_api.write.side_effect = Exception("Write error")
        mock_client.write_api.return_value = mock_write_api
        mock_influx_client.return_value = mock_client
        
        manager = InfluxDBManager()
        manager.write_api = mock_write_api
        
        klines = [Kline(
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
        )]
        
        result = manager.save_klines(klines)
        assert result is False
    
    @patch('qf_database.influxdb_manager.InfluxDBClient')
    def test_get_kline_not_found(self, mock_influx_client):
        """测试获取不存在的K线"""
        mock_client = Mock()
        mock_query_api = Mock()
        mock_query_api.query.return_value = []
        mock_influx_client.return_value = mock_client
        
        manager = InfluxDBManager()
        manager.query_api = mock_query_api
        
        result = manager.get_kline(
            symbol="BTCUSDT",
            exchange="binance",
            interval="1h",
            timestamp=datetime(2024, 1, 1, 12, 0, 0)
        )
        assert result is None
    
    @patch('qf_database.influxdb_manager.InfluxDBClient')
    def test_query_klines_with_end_time(self, mock_influx_client):
        """测试查询K线带结束时间"""
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
        
        results = manager.query_klines(
            symbol="BTCUSDT",
            exchange="binance",
            interval="1h",
            start_time=datetime(2024, 1, 1),
            end_time=datetime(2024, 1, 2)
        )
        assert len(results) == 1
    
    @patch('qf_database.influxdb_manager.InfluxDBClient')
    def test_save_tick_exception(self, mock_influx_client):
        """测试保存Tick异常"""
        mock_client = Mock()
        mock_write_api = Mock()
        mock_write_api.write.side_effect = Exception("Write error")
        mock_client.write_api.return_value = mock_write_api
        mock_influx_client.return_value = mock_client
        
        manager = InfluxDBManager()
        manager.write_api = mock_write_api
        
        tick = Tick(
            symbol="BTCUSDT",
            exchange="binance",
            timestamp=datetime.now(),
            price=Decimal("50000"),
            quantity=Decimal("0.1"),
            side="buy",
            trade_id="tick_001"
        )
        
        result = manager.save_tick(tick)
        assert result is False
    
    @patch('qf_database.influxdb_manager.InfluxDBClient')
    def test_save_ticks_exception(self, mock_influx_client):
        """测试批量保存Tick异常"""
        mock_client = Mock()
        mock_write_api = Mock()
        mock_write_api.write.side_effect = Exception("Write error")
        mock_client.write_api.return_value = mock_write_api
        mock_influx_client.return_value = mock_client
        
        manager = InfluxDBManager()
        manager.write_api = mock_write_api
        
        ticks = [Tick(
            symbol="BTCUSDT",
            exchange="binance",
            timestamp=datetime.now(),
            price=Decimal("50000"),
            quantity=Decimal("0.1"),
            side="buy",
            trade_id="tick_001"
        )]
        
        result = manager.save_ticks(ticks)
        assert result is False
    
    @patch('qf_database.influxdb_manager.InfluxDBClient')
    def test_query_ticks_with_side_filter(self, mock_influx_client):
        """测试查询Tick带方向筛选"""
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
        
        results = manager.query_ticks(
            symbol="BTCUSDT",
            exchange="binance",
            start_time=datetime(2024, 1, 1),
            end_time=datetime(2024, 1, 2),
            side="buy"
        )
        assert len(results) == 1
    
    @patch('qf_database.influxdb_manager.InfluxDBClient')
    def test_delete_klines_exception(self, mock_influx_client):
        """测试删除K线异常"""
        mock_client = Mock()
        mock_delete_api = Mock()
        mock_delete_api.delete.side_effect = Exception("Delete error")
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
        assert result is False


# ==================== Additional RedisManager Tests ====================

class TestRedisManagerAdditional:
    """补充Redis管理器测试"""
    
    @patch('qf_database.redis_manager.redis.ConnectionPool')
    @patch('qf_database.redis_manager.redis.Redis')
    def test_get_default_value(self, mock_redis_class, mock_pool):
        """测试获取默认值"""
        mock_client = Mock()
        mock_client.get.return_value = None
        mock_redis_class.return_value = mock_client
        
        manager = RedisManager()
        manager.client = mock_client
        
        result = manager.get("non_existent", default="default_value")
        assert result == "default_value"
    
    @patch('qf_database.redis_manager.redis.ConnectionPool')
    @patch('qf_database.redis_manager.redis.Redis')
    def test_delete_exception(self, mock_redis_class, mock_pool):
        """测试删除异常"""
        mock_client = Mock()
        mock_client.delete.side_effect = Exception("Delete error")
        mock_redis_class.return_value = mock_client
        
        manager = RedisManager()
        manager.client = mock_client
        
        result = manager.delete("key")
        assert result is False
    
    @patch('qf_database.redis_manager.redis.ConnectionPool')
    @patch('qf_database.redis_manager.redis.Redis')
    def test_cache_tick_exception(self, mock_redis_class, mock_pool):
        """测试缓存Tick异常"""
        mock_client = Mock()
        mock_client.setex.side_effect = Exception("Cache error")
        mock_redis_class.return_value = mock_client
        
        manager = RedisManager()
        manager.client = mock_client
        
        tick = Tick(
            symbol="BTCUSDT",
            exchange="binance",
            timestamp=datetime.now(),
            price=Decimal("50000"),
            quantity=Decimal("0.1"),
            side="buy",
            trade_id="tick_001"
        )
        
        result = manager.cache_tick(tick)
        assert result is False
    
    @patch('qf_database.redis_manager.redis.ConnectionPool')
    @patch('qf_database.redis_manager.redis.Redis')
    def test_cache_kline_exception(self, mock_redis_class, mock_pool):
        """测试缓存K线异常"""
        mock_client = Mock()
        mock_client.setex.side_effect = Exception("Cache error")
        mock_redis_class.return_value = mock_client
        
        manager = RedisManager()
        manager.client = mock_client
        
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
        
        result = manager.cache_kline(kline)
        assert result is False
    
    @patch('qf_database.redis_manager.redis.ConnectionPool')
    @patch('qf_database.redis_manager.redis.Redis')
    def test_cache_ticks_batch_exception(self, mock_redis_class, mock_pool):
        """测试批量缓存Tick异常"""
        mock_client = Mock()
        mock_client.pipeline.return_value = mock_client
        mock_client.execute.side_effect = Exception("Pipeline error")
        mock_redis_class.return_value = mock_client
        
        manager = RedisManager()
        manager.client = mock_client
        
        ticks = [Tick(
            symbol="BTCUSDT",
            exchange="binance",
            timestamp=datetime.now(),
            price=Decimal("50000"),
            quantity=Decimal("0.1"),
            side="buy",
            trade_id="tick_001"
        )]
        
        result = manager.cache_ticks_batch(ticks)
        assert result is False
    
    @patch('qf_database.redis_manager.redis.ConnectionPool')
    @patch('qf_database.redis_manager.redis.Redis')
    def test_get_cached_kline_exception(self, mock_redis_class, mock_pool):
        """测试获取缓存K线异常"""
        mock_client = Mock()
        mock_client.get.side_effect = Exception("Get error")
        mock_redis_class.return_value = mock_client
        
        manager = RedisManager()
        manager.client = mock_client
        
        result = manager.get_cached_kline("BTCUSDT", "binance", "1h")
        assert result is None
    
    @patch('qf_database.redis_manager.redis.ConnectionPool')
    @patch('qf_database.redis_manager.redis.Redis')
    def test_rate_limit_check_exception(self, mock_redis_class, mock_pool):
        """测试限流检查异常"""
        mock_client = Mock()
        mock_client.get.side_effect = Exception("Rate limit error")
        mock_redis_class.return_value = mock_client
        
        manager = RedisManager()
        manager.client = mock_client
        
        # 异常时应该允许请求通过
        allowed, count, ttl = manager.rate_limit_check("key", 100, 60)
        assert allowed is True
    
    @patch('qf_database.redis_manager.redis.ConnectionPool')
    @patch('qf_database.redis_manager.redis.Redis')
    def test_publish_exception(self, mock_redis_class, mock_pool):
        """测试发布异常"""
        mock_client = Mock()
        mock_client.publish.side_effect = Exception("Publish error")
        mock_redis_class.return_value = mock_client
        
        manager = RedisManager()
        manager.client = mock_client
        
        result = manager.publish("channel", {"msg": "test"})
        assert result == 0
    
    @patch('qf_database.redis_manager.redis.ConnectionPool')
    @patch('qf_database.redis_manager.redis.Redis')
    def test_subscribe_exception(self, mock_redis_class, mock_pool):
        """测试订阅异常"""
        mock_client = Mock()
        mock_client.pubsub.side_effect = Exception("Subscribe error")
        mock_redis_class.return_value = mock_client
        
        manager = RedisManager()
        manager.client = mock_client
        
        result = manager.subscribe("channel")
        assert result is None
    
    @patch('qf_database.redis_manager.redis.ConnectionPool')
    @patch('qf_database.redis_manager.redis.Redis')
    def test_acquire_lock_exception(self, mock_redis_class, mock_pool):
        """测试获取锁异常"""
        mock_client = Mock()
        mock_client.set.side_effect = Exception("Lock error")
        mock_redis_class.return_value = mock_client
        
        manager = RedisManager()
        manager.client = mock_client
        
        result = manager.acquire_lock("test_lock", ttl=30)
        assert result is False
    
    @patch('qf_database.redis_manager.redis.ConnectionPool')
    @patch('qf_database.redis_manager.redis.Redis')
    def test_release_lock_exception(self, mock_redis_class, mock_pool):
        """测试释放锁异常"""
        mock_client = Mock()
        mock_client.delete.side_effect = Exception("Unlock error")
        mock_redis_class.return_value = mock_client
        
        manager = RedisManager()
        manager.client = mock_client
        
        result = manager.release_lock("test_lock")
        assert result is False
    
    @patch('qf_database.redis_manager.redis.ConnectionPool')
    @patch('qf_database.redis_manager.redis.Redis')
    def test_keys_exception(self, mock_redis_class, mock_pool):
        """测试获取键列表异常"""
        mock_client = Mock()
        mock_client.keys.side_effect = Exception("Keys error")
        mock_redis_class.return_value = mock_client
        
        manager = RedisManager()
        manager.client = mock_client
        
        result = manager.keys("test:*")
        assert result == []
    
    @patch('qf_database.redis_manager.redis.ConnectionPool')
    @patch('qf_database.redis_manager.redis.Redis')
    def test_flush_db_exception(self, mock_redis_class, mock_pool):
        """测试清空数据库异常"""
        mock_client = Mock()
        mock_client.flushdb.side_effect = Exception("Flush error")
        mock_redis_class.return_value = mock_client
        
        manager = RedisManager()
        manager.client = mock_client
        
        result = manager.flush_db()
        assert result is False
    
    @patch('qf_database.redis_manager.redis.ConnectionPool')
    @patch('qf_database.redis_manager.redis.Redis')
    def test_info_exception(self, mock_redis_class, mock_pool):
        """测试获取信息异常"""
        mock_client = Mock()
        mock_client.info.side_effect = Exception("Info error")
        mock_redis_class.return_value = mock_client
        
        manager = RedisManager()
        manager.client = mock_client
        
        result = manager.info()
        assert result == {}


# ==================== Additional DatabaseManager Tests ====================

class TestDatabaseManagerAdditional:
    """补充统一数据库管理器测试"""
    
    @patch.object(MySQLManager, '__init__', return_value=None)
    @patch.object(InfluxDBManager, '__init__', return_value=None)
    @patch.object(RedisManager, '__init__', return_value=None)
    @patch.object(MySQLManager, 'connect', side_effect=Exception("MySQL error"))
    @patch.object(InfluxDBManager, 'connect', side_effect=Exception("InfluxDB error"))
    @patch.object(RedisManager, 'connect', side_effect=Exception("Redis error"))
    def test_check_health_with_errors(self, mock_redis, mock_influx, mock_mysql, *args):
        """测试健康检查带错误"""
        manager = DatabaseManager()
        health = manager.check_health()
        
        assert health["overall"] == "unhealthy"
        assert "error" in health["mysql"]
        assert "error" in health["influxdb"]
        assert "error" in health["redis"]
    
    @patch.object(MySQLManager, '__init__', return_value=None)
    @patch.object(InfluxDBManager, '__init__', return_value=None)
    @patch.object(RedisManager, '__init__', return_value=None)
    @patch.object(InfluxDBManager, 'ensure_bucket', return_value=False)
    def test_init_influxdb_bucket_failure(self, mock_ensure, *args):
        """测试初始化InfluxDB存储桶失败"""
        manager = DatabaseManager()
        result = manager.init_influxdb_bucket()
        
        assert result is False
    
    @patch.object(MySQLManager, '__init__', return_value=None)
    @patch.object(InfluxDBManager, '__init__', return_value=None)
    @patch.object(RedisManager, '__init__', return_value=None)
    @patch.object(InfluxDBManager, 'get_latest_kline')
    def test_get_kline_without_cache(self, mock_get, *args):
        """测试获取K线不使用缓存"""
        mock_get.return_value = None
        
        manager = DatabaseManager()
        result = manager.get_kline("BTCUSDT", "binance", "1h", use_cache=False)
        
        mock_get.assert_called_once()
    
    @patch.object(MySQLManager, '__init__', return_value=None)
    @patch.object(InfluxDBManager, '__init__', return_value=None)
    @patch.object(RedisManager, '__init__', return_value=None)
    @patch.object(InfluxDBManager, 'get_latest_tick')
    def test_get_tick_without_cache(self, mock_get, *args):
        """测试获取Tick不使用缓存"""
        mock_get.return_value = None
        
        manager = DatabaseManager()
        result = manager.get_tick("BTCUSDT", "binance", use_cache=False)
        
        mock_get.assert_called_once()
    
    @patch.object(MySQLManager, '__init__', return_value=None)
    @patch.object(InfluxDBManager, '__init__', return_value=None)
    @patch.object(RedisManager, '__init__', return_value=None)
    def test_context_manager_exception(self, *args):
        """测试上下文管理器异常处理"""
        with patch.object(MySQLManager, 'disconnect') as mock_mysql_close, \
             patch.object(InfluxDBManager, 'disconnect') as mock_influx_close, \
             patch.object(RedisManager, 'disconnect') as mock_redis_close:
            
            try:
                with DatabaseManager() as manager:
                    raise ValueError("Test exception")
            except ValueError:
                pass
            
            mock_mysql_close.assert_called_once()
            mock_influx_close.assert_called_once()
            mock_redis_close.assert_called_once()