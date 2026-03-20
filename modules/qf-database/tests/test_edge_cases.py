"""
额外边界条件测试 - qf-database
用于提升覆盖率到90%+
"""
import pytest
from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import Mock, patch, MagicMock

from qf_database.models import Contract, Trade, Account, Kline, Tick
from qf_database.mysql_manager import MySQLManager, _BatchSession
from qf_database.influxdb_manager import InfluxDBManager
from qf_database.redis_manager import RedisManager


# ==================== MySQL 边界条件测试 ====================

class TestMySQLManagerEdgeCases:
    """MySQLManager 边界条件测试"""
    
    @patch('qf_database.mysql_manager.create_engine')
    def test_connect_with_operational_error(self, mock_create_engine):
        """测试连接时OperationalError"""
        from sqlalchemy.exc import OperationalError
        
        mock_engine = Mock()
        mock_engine.connect.side_effect = OperationalError("Connection refused", "", "")
        mock_create_engine.return_value = mock_engine
        
        manager = MySQLManager()
        manager.engine = mock_engine
        
        result = manager.connect()
        assert result is False
    
    @patch('qf_database.mysql_manager.create_engine')
    def test_connect_with_generic_error(self, mock_create_engine):
        """测试连接时通用错误"""
        mock_engine = Mock()
        mock_engine.connect.side_effect = Exception("Unexpected error")
        mock_create_engine.return_value = mock_engine
        
        manager = MySQLManager()
        manager.engine = mock_engine
        
        result = manager.connect()
        assert result is False
    
    @patch('qf_database.mysql_manager.create_engine')
    def test_disconnect_with_error(self, mock_create_engine):
        """测试断开时出错"""
        mock_engine = Mock()
        mock_engine.dispose.side_effect = Exception("Dispose error")
        mock_create_engine.return_value = mock_engine
        
        manager = MySQLManager()
        manager.engine = mock_engine
        
        # 应该不抛出异常
        manager.disconnect()
        assert manager.is_connected is False
    
    @patch('qf_database.mysql_manager.create_engine')
    def test_health_check_unexpected_error(self, mock_create_engine):
        """测试健康检查意外错误"""
        mock_engine = Mock()
        mock_engine.connect.side_effect = Exception("Unexpected")
        mock_create_engine.return_value = mock_engine
        
        manager = MySQLManager()
        manager.engine = mock_engine
        
        is_healthy, latency, error = manager.health_check()
        assert is_healthy is False
        assert error is not None


# ==================== BatchSession 测试 ====================

class TestBatchSession:
    """BatchSession 测试"""
    
    def test_batch_session_add_and_flush(self):
        """测试批量添加和刷新"""
        mock_session = Mock()
        batcher = _BatchSession(mock_session, batch_size=2)
        
        obj1 = Mock()
        obj2 = Mock()
        obj3 = Mock()
        
        batcher.add(obj1)
        # 还没达到批量大小
        mock_session.add_all.assert_not_called()
        
        batcher.add(obj2)
        # 达到批量大小，应该刷新
        mock_session.add_all.assert_called_once()
        
        batcher.add(obj3)
        batcher.flush()
        
        # 检查总共调用了两次 add_all
        assert mock_session.add_all.call_count == 2
    
    def test_batch_session_add_all(self):
        """测试批量添加多个对象"""
        mock_session = Mock()
        batcher = _BatchSession(mock_session, batch_size=5)
        
        objs = [Mock() for _ in range(3)]
        batcher.add_all(objs)
        
        # 还没达到批量大小，不会自动刷新
        mock_session.add_all.assert_not_called()
        
        # 手动刷新
        batcher.flush()
        mock_session.add_all.assert_called_once()
    
    def test_batch_session_flush_empty(self):
        """测试刷新空缓冲区"""
        mock_session = Mock()
        batcher = _BatchSession(mock_session, batch_size=5)
        
        # 刷新空的缓冲区
        batcher.flush()
        
        # 不应该调用 add_all
        mock_session.add_all.assert_not_called()


# ==================== InfluxDB 边界条件测试 ====================

class TestInfluxDBManagerEdgeCases:
    """InfluxDBManager 边界条件测试"""
    
    @patch('qf_database.influxdb_manager.InfluxDBClient')
    def test_connect_with_api_exception(self, mock_client):
        """测试连接时ApiException"""
        from influxdb_client.rest import ApiException
        
        mock_instance = Mock()
        mock_instance.organizations_api.side_effect = ApiException("Connection refused")
        mock_client.return_value = mock_instance
        
        manager = InfluxDBManager()
        manager.client = mock_instance
        
        result = manager.connect()
        assert result is False
    
    @patch('qf_database.influxdb_manager.InfluxDBClient')
    def test_flush_without_write_api(self, mock_client):
        """测试无write_api时flush"""
        manager = InfluxDBManager()
        manager.write_api = None
        
        # 不应该报错
        manager.flush()
    
    @patch('qf_database.influxdb_manager.InfluxDBClient')
    def test_save_kline_with_api_exception(self, mock_client):
        """测试保存K线时ApiException"""
        from influxdb_client.rest import ApiException
        
        mock_write_api = Mock()
        mock_write_api.write.side_effect = ApiException("Write failed")
        
        manager = InfluxDBManager()
        manager.write_api = mock_write_api
        
        kline = Kline(
            symbol="BTCUSDT",
            exchange="binance",
            interval="1h",
            timestamp=datetime.utcnow(),
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
    
    @patch('qf_database.influxdb_manager.InfluxDBClient')
    def test_save_klines_with_api_exception(self, mock_client):
        """测试批量保存K线时ApiException"""
        from influxdb_client.rest import ApiException
        
        mock_write_api = Mock()
        mock_write_api.write.side_effect = ApiException("Write failed")
        
        manager = InfluxDBManager()
        manager.write_api = mock_write_api
        
        klines = [
            Kline(
                symbol="BTCUSDT",
                exchange="binance",
                interval="1h",
                timestamp=datetime.utcnow(),
                open=Decimal("50000"),
                high=Decimal("51000"),
                low=Decimal("49000"),
                close=Decimal("50500"),
                volume=Decimal("100"),
                quote_volume=Decimal("5050000"),
                trades=1000
            )
        ]
        
        result = manager.save_klines(klines)
        assert result is False
        # 检查统计是否正确更新
        assert manager._write_stats["failed_writes"] == 1
    
    @patch('qf_database.influxdb_manager.InfluxDBClient')
    def test_save_empty_klines(self, mock_client):
        """测试保存空K线列表"""
        mock_write_api = Mock()
        
        manager = InfluxDBManager()
        manager.write_api = mock_write_api
        
        result = manager.save_klines([])
        assert result is True
        # 不应该调用write_api
        mock_write_api.write.assert_not_called()


# ==================== Redis 边界条件测试 ====================

class TestRedisManagerEdgeCases:
    """RedisManager 边界条件测试"""
    
    @patch('qf_database.redis_manager.redis.ConnectionPool')
    @patch('qf_database.redis_manager.redis.Redis')
    def test_connect_with_connection_error(self, mock_redis, mock_pool):
        """测试连接时ConnectionError"""
        from redis.exceptions import ConnectionError as RedisConnectionError
        
        mock_client = Mock()
        mock_client.ping.side_effect = RedisConnectionError("Connection refused")
        mock_redis.return_value = mock_client
        
        manager = RedisManager()
        manager.client = mock_client
        
        result = manager.connect()
        assert result is False
    
    @patch('qf_database.redis_manager.redis.ConnectionPool')
    @patch('qf_database.redis_manager.redis.Redis')
    def test_disconnect_with_error(self, mock_redis, mock_pool):
        """测试断开时出错"""
        mock_pool_instance = Mock()
        mock_pool_instance.disconnect.side_effect = Exception("Disconnect error")
        mock_pool.return_value = mock_pool_instance
        
        mock_client = Mock()
        mock_redis.return_value = mock_client
        
        manager = RedisManager()
        
        # 应该不抛出异常
        manager.disconnect()
        assert manager.is_connected is False
    
    @patch('qf_database.redis_manager.redis.ConnectionPool')
    @patch('qf_database.redis_manager.redis.Redis')
    def test_set_with_pickle_serialize(self, mock_redis, mock_pool):
        """测试pickle序列化设置"""
        mock_client = Mock()
        mock_client.setex.return_value = True
        mock_redis.return_value = mock_client
        
        manager = RedisManager()
        manager.client = mock_client
        
        # 测试pickle序列化
        result = manager.set("test_key", {"data": "value"}, ttl=60, serialize="pickle")
        assert result is True
    
    @patch('qf_database.redis_manager.redis.ConnectionPool')
    @patch('qf_database.redis_manager.redis.Redis')
    def test_get_with_pickle_deserialize(self, mock_redis, mock_pool):
        """测试pickle反序列化获取"""
        import pickle
        
        mock_client = Mock()
        mock_client.get.return_value = pickle.dumps({"data": "value"})
        mock_redis.return_value = mock_client
        
        manager = RedisManager()
        manager.client = mock_client
        
        result = manager.get("test_key", deserialize="pickle")
        assert result == {"data": "value"}
    
    @patch('qf_database.redis_manager.redis.ConnectionPool')
    @patch('qf_database.redis_manager.redis.Redis')
    def test_get_raw_value(self, mock_redis, mock_pool):
        """测试获取原始值"""
        mock_client = Mock()
        mock_client.get.return_value = b"raw_value"
        mock_redis.return_value = mock_client
        
        manager = RedisManager()
        manager.client = mock_client
        
        result = manager.get("test_key", deserialize="raw")
        assert result == b"raw_value"
    
    @patch('qf_database.redis_manager.redis.ConnectionPool')
    @patch('qf_database.redis_manager.redis.Redis')
    def test_set_batch_with_pickle(self, mock_redis, mock_pool):
        """测试pickle序列化批量设置"""
        mock_client = Mock()
        mock_pipe = Mock()
        mock_client.pipeline.return_value = mock_pipe
        mock_redis.return_value = mock_client
        
        manager = RedisManager()
        manager.client = mock_client
        
        items = {"key1": {"data": 1}, "key2": {"data": 2}}
        result = manager.set_batch(items, ttl=60, serialize="pickle")
        assert result is True
    
    @patch('qf_database.redis_manager.redis.ConnectionPool')
    @patch('qf_database.redis_manager.redis.Redis')
    def test_set_batch_error(self, mock_redis, mock_pool):
        """测试批量设置错误"""
        mock_client = Mock()
        mock_client.pipeline.side_effect = Exception("Pipeline error")
        mock_redis.return_value = mock_client
        
        manager = RedisManager()
        manager.client = mock_client
        
        items = {"key1": "value1", "key2": "value2"}
        result = manager.set_batch(items, ttl=60)
        assert result is False
    
    @patch('qf_database.redis_manager.redis.ConnectionPool')
    @patch('qf_database.redis_manager.redis.Redis')
    def test_get_batch_error(self, mock_redis, mock_pool):
        """测试批量获取错误"""
        mock_client = Mock()
        mock_client.pipeline.side_effect = Exception("Pipeline error")
        mock_redis.return_value = mock_client
        
        manager = RedisManager()
        manager.client = mock_client
        
        result = manager.get_batch(["key1", "key2"])
        assert result == {}
    
    @patch('qf_database.redis_manager.redis.ConnectionPool')
    @patch('qf_database.redis_manager.redis.Redis')
    def test_delete_batch_error(self, mock_redis, mock_pool):
        """测试批量删除错误"""
        mock_client = Mock()
        mock_client.pipeline.side_effect = Exception("Pipeline error")
        mock_redis.return_value = mock_client
        
        manager = RedisManager()
        manager.client = mock_client
        
        result = manager.delete_batch(["key1", "key2"])
        assert result == 0


# ==================== DatabaseManager 边界条件测试 ====================

class TestDatabaseManagerEdgeCases:
    """DatabaseManager 边界条件测试"""
    
    @patch.object(MySQLManager, '__init__', return_value=None)
    @patch.object(InfluxDBManager, '__init__', return_value=None)
    @patch.object(RedisManager, '__init__', return_value=None)
    @patch.object(MySQLManager, 'health_check', side_effect=Exception("MySQL error"))
    @patch.object(InfluxDBManager, 'health_check', side_effect=Exception("InfluxDB error"))
    @patch.object(RedisManager, 'health_check', side_effect=Exception("Redis error"))
    def test_check_health_with_all_errors(self, mock_redis, mock_influx, mock_mysql, *args):
        """测试所有健康检查都出错"""
        from qf_database.database_manager import DatabaseManager
        
        manager = DatabaseManager()
        health = manager.check_health()
        
        assert health["overall"] == "unhealthy"
        assert "error" in health["mysql"]
        assert "error" in health["influxdb"]
        assert "error" in health["redis"]
