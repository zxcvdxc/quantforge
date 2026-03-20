"""
额外测试 - 提升代码覆盖率
"""
import pytest
from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import Mock, patch, MagicMock

from qf_database.models import Contract, Trade, Account, Kline, Tick
from qf_database.mysql_manager import MySQLManager
from qf_database.influxdb_manager import InfluxDBManager
from qf_database.redis_manager import RedisManager
from qf_database.database_manager import DatabaseManager, DatabaseConfig


# ==================== MySQL 额外测试 ====================

class TestMySQLManagerAdditional:
    """MySQLManager 额外测试"""
    
    @patch('qf_database.mysql_manager.create_engine')
    def test_init_with_custom_pool_config(self, mock_create_engine):
        """测试使用自定义连接池配置初始化"""
        mock_engine = Mock()
        mock_create_engine.return_value = mock_engine
        
        manager = MySQLManager(
            host="custom_host",
            port=3307,
            user="admin",
            password="secret",
            database="test_db",
            pool_size=50,
            max_overflow=60,
            pool_recycle=7200,
            pool_timeout=60,
            enable_pooling=True
        )
        
        assert manager.host == "custom_host"
        assert manager.port == 3307
        assert manager.database == "test_db"
        mock_create_engine.assert_called_once()
    
    @patch('qf_database.mysql_manager.create_engine')
    def test_init_without_pooling(self, mock_create_engine):
        """测试禁用连接池初始化"""
        mock_engine = Mock()
        mock_create_engine.return_value = mock_engine
        
        manager = MySQLManager(enable_pooling=False)
        
        # 检查是否使用 NullPool
        call_args = mock_create_engine.call_args
        assert call_args[1]['poolclass'].__name__ == 'NullPool'
    
    @patch('qf_database.mysql_manager.create_engine')
    def test_get_pool_status(self, mock_create_engine):
        """测试获取连接池状态"""
        mock_engine = Mock()
        mock_pool = Mock()
        mock_pool.size.return_value = 20
        mock_pool.checkedin.return_value = 5
        mock_pool.checkedout.return_value = 10
        mock_pool.overflow.return_value = 2
        mock_engine.pool = mock_pool
        mock_create_engine.return_value = mock_engine
        
        manager = MySQLManager()
        manager.engine = mock_engine
        
        status = manager.get_pool_status()
        
        assert status["size"] == 20
        assert status["checked_in"] == 5
        assert status["checked_out"] == 10
        assert status["overflow"] == 2
    
    @patch('qf_database.mysql_manager.create_engine')
    def test_get_pool_status_without_attr(self, mock_create_engine):
        """测试获取连接池状态（无属性时）"""
        mock_engine = Mock()
        mock_pool = Mock()
        # 删除 size 属性，模拟没有该属性的情况
        del mock_pool.size
        mock_engine.pool = mock_pool
        mock_create_engine.return_value = mock_engine
        
        manager = MySQLManager()
        manager.engine = mock_engine
        
        status = manager.get_pool_status()
        
        # 当没有属性时应该返回 -1
        assert status["size"] == -1
    
    @patch('qf_database.mysql_manager.create_engine')
    def test_health_check_success(self, mock_create_engine):
        """测试健康检查成功"""
        mock_engine = Mock()
        mock_conn = Mock()
        mock_engine.connect.return_value.__enter__ = Mock(return_value=mock_conn)
        mock_engine.connect.return_value.__exit__ = Mock(return_value=False)
        mock_create_engine.return_value = mock_engine
        
        manager = MySQLManager()
        manager.engine = mock_engine
        
        is_healthy, latency, error = manager.health_check()
        
        assert is_healthy is True
        assert latency >= 0
        assert error is None
    
    @patch('qf_database.mysql_manager.create_engine')
    def test_health_check_failure(self, mock_create_engine):
        """测试健康检查失败"""
        from sqlalchemy.exc import OperationalError
        
        mock_engine = Mock()
        mock_engine.connect.side_effect = OperationalError("Connection refused", "", "")
        mock_create_engine.return_value = mock_engine
        
        manager = MySQLManager()
        manager.engine = mock_engine
        
        is_healthy, latency, error = manager.health_check()
        
        assert is_healthy is False
        assert error is not None
    
    @patch('qf_database.mysql_manager.create_engine')
    def test_batch_session(self, mock_create_engine):
        """测试批量会话"""
        mock_engine = Mock()
        mock_create_engine.return_value = mock_engine
        
        manager = MySQLManager()
        manager.SessionLocal = Mock()
        mock_session = Mock()
        manager.SessionLocal.return_value = mock_session
        
        with manager.batch_session(batch_size=10) as batch:
            from qf_database.mysql_manager import _BatchSession
            assert isinstance(batch, _BatchSession)


# ==================== InfluxDB 额外测试 ====================

class TestInfluxDBManagerAdditional:
    """InfluxDBManager 额外测试"""
    
    @patch('qf_database.influxdb_manager.InfluxDBClient')
    def test_init_sync_mode(self, mock_influx_client):
        """测试同步模式初始化"""
        mock_client = Mock()
        mock_influx_client.return_value = mock_client
        
        manager = InfluxDBManager(write_mode="sync")
        
        assert manager.write_mode == "sync"
    
    @patch('qf_database.influxdb_manager.InfluxDBClient')
    def test_init_async_mode(self, mock_influx_client):
        """测试异步模式初始化"""
        mock_client = Mock()
        mock_influx_client.return_value = mock_client
        
        manager = InfluxDBManager(write_mode="async")
        
        assert manager.write_mode == "async"
    
    @patch('qf_database.influxdb_manager.InfluxDBClient')
    def test_flush(self, mock_influx_client):
        """测试强制刷新"""
        mock_client = Mock()
        mock_write_api = Mock()
        mock_client.write_api.return_value = mock_write_api
        mock_influx_client.return_value = mock_client
        
        manager = InfluxDBManager()
        manager.write_api = mock_write_api
        
        manager.flush()
        
        mock_write_api.flush.assert_called_once()
    
    @patch('qf_database.influxdb_manager.InfluxDBClient')
    def test_get_write_stats(self, mock_influx_client):
        """测试获取写入统计"""
        mock_client = Mock()
        mock_influx_client.return_value = mock_client
        
        manager = InfluxDBManager()
        
        stats = manager.get_write_stats()
        
        assert "total_points" in stats
        assert "total_batches" in stats
        assert "failed_writes" in stats
    
    @patch('qf_database.influxdb_manager.InfluxDBClient')
    def test_health_check_success(self, mock_influx_client):
        """测试健康检查成功"""
        mock_client = Mock()
        mock_client.ready.return_value = True
        mock_influx_client.return_value = mock_client
        
        manager = InfluxDBManager()
        manager.client = mock_client
        
        is_healthy, latency, error = manager.health_check()
        
        assert is_healthy is True
        assert latency >= 0
        assert error is None
    
    @patch('qf_database.influxdb_manager.InfluxDBClient')
    def test_health_check_failure(self, mock_influx_client):
        """测试健康检查失败"""
        mock_client = Mock()
        mock_client.ready.side_effect = Exception("Connection refused")
        mock_influx_client.return_value = mock_client
        
        manager = InfluxDBManager()
        manager.client = mock_client
        
        is_healthy, latency, error = manager.health_check()
        
        assert is_healthy is False
        assert error is not None


# ==================== Redis 额外测试 ====================

class TestRedisManagerAdditional:
    """RedisManager 额外测试"""
    
    @patch('qf_database.redis_manager.redis.ConnectionPool')
    @patch('qf_database.redis_manager.redis.Redis')
    def test_init_with_custom_config(self, mock_redis, mock_pool):
        """测试使用自定义配置初始化"""
        mock_client = Mock()
        mock_redis.return_value = mock_client
        
        manager = RedisManager(
            host="custom_host",
            port=6380,
            db=1,
            password="secret",
            max_connections=200,
            socket_timeout=10.0,
            socket_connect_timeout=10.0,
            socket_keepalive=False
        )
        
        assert manager.host == "custom_host"
        assert manager.port == 6380
        assert manager.db == 1
    
    @patch('qf_database.redis_manager.redis.ConnectionPool')
    @patch('qf_database.redis_manager.redis.Redis')
    def test_get_pool_status(self, mock_redis, mock_pool):
        """测试获取连接池状态"""
        mock_client = Mock()
        mock_redis.return_value = mock_client
        
        manager = RedisManager()
        
        status = manager.get_pool_status()
        
        assert "max_connections" in status
    
    @patch('qf_database.redis_manager.redis.ConnectionPool')
    @patch('qf_database.redis_manager.redis.Redis')
    def test_get_stats(self, mock_redis, mock_pool):
        """测试获取统计信息"""
        mock_client = Mock()
        mock_redis.return_value = mock_client
        
        manager = RedisManager()
        
        # 先进行一些操作
        manager._stats["cache_hits"] = 80
        manager._stats["cache_misses"] = 20
        
        stats = manager.get_stats()
        
        assert stats["cache_hits"] == 80
        assert stats["cache_misses"] == 20
        assert stats["cache_hit_rate"] == 80.0
    
    @patch('qf_database.redis_manager.redis.ConnectionPool')
    @patch('qf_database.redis_manager.redis.Redis')
    def test_reset_stats(self, mock_redis, mock_pool):
        """测试重置统计信息"""
        mock_client = Mock()
        mock_redis.return_value = mock_client
        
        manager = RedisManager()
        
        # 先设置一些统计
        manager._stats["total_ops"] = 100
        manager.reset_stats()
        
        assert manager._stats["total_ops"] == 0
    
    @patch('qf_database.redis_manager.redis.ConnectionPool')
    @patch('qf_database.redis_manager.redis.Redis')
    def test_set_batch(self, mock_redis, mock_pool):
        """测试批量设置"""
        mock_client = Mock()
        mock_pipe = Mock()
        mock_client.pipeline.return_value = mock_pipe
        mock_redis.return_value = mock_client
        
        manager = RedisManager()
        manager.client = mock_client
        
        items = {"key1": "value1", "key2": "value2"}
        result = manager.set_batch(items, ttl=60)
        
        assert result is True
        mock_pipe.setex.assert_called()
    
    @patch('qf_database.redis_manager.redis.ConnectionPool')
    @patch('qf_database.redis_manager.redis.Redis')
    def test_set_batch_empty(self, mock_redis, mock_pool):
        """测试批量设置空字典"""
        mock_client = Mock()
        mock_redis.return_value = mock_client
        
        manager = RedisManager()
        manager.client = mock_client
        
        result = manager.set_batch({}, ttl=60)
        
        assert result is True
    
    @patch('qf_database.redis_manager.redis.ConnectionPool')
    @patch('qf_database.redis_manager.redis.Redis')
    def test_get_batch(self, mock_redis, mock_pool):
        """测试批量获取"""
        mock_client = Mock()
        mock_pipe = Mock()
        mock_pipe.execute.return_value = [b'"value1"', b'"value2"']
        mock_client.pipeline.return_value = mock_pipe
        mock_redis.return_value = mock_client
        
        manager = RedisManager()
        manager.client = mock_client
        
        result = manager.get_batch(["key1", "key2"])
        
        assert len(result) == 2
        assert result["key1"] == "value1"
    
    @patch('qf_database.redis_manager.redis.ConnectionPool')
    @patch('qf_database.redis_manager.redis.Redis')
    def test_get_batch_empty(self, mock_redis, mock_pool):
        """测试批量获取空列表"""
        mock_client = Mock()
        mock_redis.return_value = mock_client
        
        manager = RedisManager()
        manager.client = mock_client
        
        result = manager.get_batch([])
        
        assert result == {}
    
    @patch('qf_database.redis_manager.redis.ConnectionPool')
    @patch('qf_database.redis_manager.redis.Redis')
    def test_delete_batch(self, mock_redis, mock_pool):
        """测试批量删除"""
        mock_client = Mock()
        mock_pipe = Mock()
        mock_pipe.execute.return_value = [1, 1, 0]
        mock_client.pipeline.return_value = mock_pipe
        mock_redis.return_value = mock_client
        
        manager = RedisManager()
        manager.client = mock_client
        
        result = manager.delete_batch(["key1", "key2", "key3"])
        
        assert result == 2  # 两个成功删除
    
    @patch('qf_database.redis_manager.redis.ConnectionPool')
    @patch('qf_database.redis_manager.redis.Redis')
    def test_delete_batch_empty(self, mock_redis, mock_pool):
        """测试批量删除空列表"""
        mock_client = Mock()
        mock_redis.return_value = mock_client
        
        manager = RedisManager()
        manager.client = mock_client
        
        result = manager.delete_batch([])
        
        assert result == 0
    
    @patch('qf_database.redis_manager.redis.ConnectionPool')
    @patch('qf_database.redis_manager.redis.Redis')
    def test_health_check_success(self, mock_redis, mock_pool):
        """测试健康检查成功"""
        mock_client = Mock()
        mock_client.ping.return_value = True
        mock_redis.return_value = mock_client
        
        manager = RedisManager()
        manager.client = mock_client
        
        is_healthy, latency, error = manager.health_check()
        
        assert is_healthy is True
        assert latency >= 0
        assert error is None
    
    @patch('qf_database.redis_manager.redis.ConnectionPool')
    @patch('qf_database.redis_manager.redis.Redis')
    def test_health_check_failure(self, mock_redis, mock_pool):
        """测试健康检查失败"""
        mock_client = Mock()
        mock_client.ping.side_effect = Exception("Connection refused")
        mock_redis.return_value = mock_client
        
        manager = RedisManager()
        manager.client = mock_client
        
        is_healthy, latency, error = manager.health_check()
        
        assert is_healthy is False
        assert error is not None


# ==================== DatabaseConfig 测试 ====================

class TestDatabaseConfig:
    """数据库配置测试"""
    
    def test_default_config(self):
        """测试默认配置"""
        config = DatabaseConfig()
        
        assert config.mysql_host == "localhost"
        assert config.mysql_port == 3306
        assert config.influxdb_url == "http://localhost:8086"
        assert config.redis_host == "localhost"
        assert config.mysql_pool_size == 20
        assert config.influxdb_batch_size == 5000
        assert config.redis_max_connections == 100
    
    def test_custom_config(self):
        """测试自定义配置"""
        config = DatabaseConfig(
            mysql_host="custom_mysql",
            mysql_pool_size=50,
            influxdb_batch_size=10000,
            redis_max_connections=200
        )
        
        assert config.mysql_host == "custom_mysql"
        assert config.mysql_pool_size == 50
        assert config.influxdb_batch_size == 10000
        assert config.redis_max_connections == 200


# ==================== DatabaseManager 额外测试 ====================

class TestDatabaseManagerAdditional:
    """DatabaseManager 额外测试"""
    
    @patch.object(MySQLManager, '__init__', return_value=None)
    @patch.object(InfluxDBManager, '__init__', return_value=None)
    @patch.object(RedisManager, '__init__', return_value=None)
    def test_init_with_config(self, mock_redis, mock_influx, mock_mysql):
        """测试使用配置初始化"""
        config = DatabaseConfig(
            mysql_host="custom_mysql",
            influxdb_url="http://custom:8086",
            redis_host="custom_redis"
        )
        
        manager = DatabaseManager(config)
        
        assert manager.config == config
    
    @patch.object(MySQLManager, '__init__', return_value=None)
    @patch.object(InfluxDBManager, '__init__', return_value=None)
    @patch.object(RedisManager, '__init__', return_value=None)
    @patch.object(MySQLManager, 'get_pool_status', return_value={"size": 20})
    @patch.object(MySQLManager, 'connection_stats', {"query_count": 100})
    @patch.object(InfluxDBManager, 'get_write_stats', return_value={"total_points": 1000})
    @patch.object(RedisManager, 'get_pool_status', return_value={"max_connections": 100})
    @patch.object(RedisManager, 'get_stats', return_value={"cache_hits": 80})
    def test_get_performance_stats(self, mock_redis_stats, mock_redis_pool, mock_influx_stats, 
                                   mock_mysql_stats, mock_mysql_pool, *args):
        """测试获取性能统计"""
        manager = DatabaseManager()
        
        stats = manager.get_performance_stats()
        
        assert "mysql" in stats
        assert "influxdb" in stats
        assert "redis" in stats
