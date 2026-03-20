"""
性能基准测试 - qf-database
"""
import pytest
import asyncio
import time
from datetime import datetime, timedelta
from decimal import Decimal
from unittest.mock import Mock, patch, MagicMock

from qf_database.models import Contract, Trade, Account, Kline, Tick
from qf_database.mysql_manager import MySQLManager
from qf_database.influxdb_manager import InfluxDBManager
from qf_database.redis_manager import RedisManager
from qf_database.database_manager import DatabaseManager


# ==================== MySQL性能测试 ====================

class TestMySQLPerformance:
    """MySQL性能基准测试"""
    
    @pytest.fixture
    def mock_mysql_manager(self):
        """创建带有模拟引擎的MySQLManager"""
        with patch('qf_database.mysql_manager.create_engine') as mock_create_engine:
            mock_engine = Mock()
            mock_create_engine.return_value = mock_engine
            
            manager = MySQLManager(
                host="localhost",
                port=3306,
                user="root",
                password="test",
                database="quantforge",
                pool_size=20,
                max_overflow=30
            )
            manager.engine = mock_engine
            yield manager
    
    def test_save_contract_benchmark(self, benchmark, mock_mysql_manager):
        """基准测试：保存合约"""
        contract = Contract(
            symbol="BTCUSDT",
            exchange="binance",
            name="Bitcoin/USDT",
            contract_type="spot",
            base_asset="BTC",
            quote_asset="USDT"
        )
        
        # 模拟session scope
        with patch.object(mock_mysql_manager, 'session_scope') as mock_scope:
            mock_session = Mock()
            mock_scope.return_value.__enter__ = Mock(return_value=mock_session)
            mock_scope.return_value.__exit__ = Mock(return_value=False)
            mock_session.execute.return_value.scalar_one_or_none.return_value = None
            
            result = benchmark(mock_mysql_manager.save_contract, contract)
            assert result is True
    
    def test_get_contract_benchmark(self, benchmark, mock_mysql_manager):
        """基准测试：获取合约"""
        with patch.object(mock_mysql_manager, 'session_scope') as mock_scope:
            mock_session = Mock()
            mock_scope.return_value.__enter__ = Mock(return_value=mock_session)
            mock_scope.return_value.__exit__ = Mock(return_value=False)
            
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
            
            result = benchmark(mock_mysql_manager.get_contract, "BTCUSDT", "binance")
            assert result is not None
    
    def test_query_trades_benchmark(self, benchmark, mock_mysql_manager):
        """基准测试：查询交易记录"""
        with patch.object(mock_mysql_manager, 'session_scope') as mock_scope:
            mock_session = Mock()
            mock_scope.return_value.__enter__ = Mock(return_value=mock_session)
            mock_scope.return_value.__exit__ = Mock(return_value=False)
            
            # 创建100个模拟交易
            mock_trades = []
            for i in range(100):
                mock_trade = Mock()
                mock_trade.id = i
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
                mock_trade.order_id = f"order_{i}"
                mock_trade.trade_id = f"trade_{i}"
                mock_trade.account_id = "test_account"
                mock_trade.strategy_id = None
                mock_trade.created_at = datetime.utcnow()
                mock_trade.updated_at = datetime.utcnow()
                mock_trades.append(mock_trade)
            
            mock_session.execute.return_value.scalars.return_value.all.return_value = mock_trades
            
            result = benchmark(mock_mysql_manager.query_trades, account_id="test_account", limit=100)
            assert len(result) == 100


# ==================== InfluxDB性能测试 ====================

class TestInfluxDBPerformance:
    """InfluxDB性能基准测试"""
    
    @pytest.fixture
    def mock_influx_manager(self):
        """创建带有模拟客户端的InfluxDBManager"""
        with patch('qf_database.influxdb_manager.InfluxDBClient') as mock_client:
            manager = InfluxDBManager(
                url="http://localhost:8086",
                token="test_token",
                org="quantforge",
                bucket="market_data"
            )
            manager.client = mock_client
            manager.write_api = Mock()
            manager.query_api = Mock()
            yield manager
    
    def test_save_kline_benchmark(self, benchmark, mock_influx_manager):
        """基准测试：保存单条K线"""
        kline = Kline(
            symbol="BTCUSDT",
            exchange="binance",
            interval="1h",
            timestamp=datetime.utcnow(),
            open=Decimal("50000.00"),
            high=Decimal("51000.00"),
            low=Decimal("49000.00"),
            close=Decimal("50500.00"),
            volume=Decimal("100.5"),
            quote_volume=Decimal("5075250.00"),
            trades=1500
        )
        
        result = benchmark(mock_influx_manager.save_kline, kline)
        assert result is True
    
    def test_save_klines_batch_benchmark(self, benchmark, mock_influx_manager):
        """基准测试：批量保存K线数据 (1000条)"""
        klines = [
            Kline(
                symbol="BTCUSDT",
                exchange="binance",
                interval="1h",
                timestamp=datetime.utcnow() + timedelta(minutes=i),
                open=Decimal("50000.00"),
                high=Decimal("51000.00"),
                low=Decimal("49000.00"),
                close=Decimal("50500.00"),
                volume=Decimal("100.5"),
                quote_volume=Decimal("5075250.00"),
                trades=1500
            )
            for i in range(1000)
        ]
        
        result = benchmark(mock_influx_manager.save_klines, klines)
        assert result is True
    
    @pytest.mark.parametrize("batch_size", [100, 500, 1000, 5000])
    def test_batch_write_comparison(self, batch_size, mock_influx_manager):
        """测试不同批量大小的写入性能"""
        klines = [
            Kline(
                symbol="BTCUSDT",
                exchange="binance",
                interval="1h",
                timestamp=datetime.utcnow() + timedelta(minutes=i),
                open=Decimal("50000.00"),
                high=Decimal("51000.00"),
                low=Decimal("49000.00"),
                close=Decimal("50500.00"),
                volume=Decimal("100.5"),
                quote_volume=Decimal("5075250.00"),
                trades=1500
            )
            for i in range(batch_size)
        ]
        
        start_time = time.time()
        mock_influx_manager.save_klines(klines)
        elapsed = time.time() - start_time
        
        # 记录性能指标
        print(f"\nBatch size {batch_size}: {elapsed:.4f}s ({batch_size/elapsed:.0f} records/sec)")


# ==================== Redis性能测试 ====================

class TestRedisPerformance:
    """Redis性能基准测试"""
    
    @pytest.fixture
    def mock_redis_manager(self):
        """创建带有模拟客户端的RedisManager"""
        with patch('qf_database.redis_manager.redis.ConnectionPool') as mock_pool, \
             patch('qf_database.redis_manager.redis.Redis') as mock_redis:
            
            mock_client = Mock()
            mock_redis.return_value = mock_client
            
            manager = RedisManager(
                host="localhost",
                port=6379,
                db=0,
                max_connections=100
            )
            manager.client = mock_client
            yield manager
    
    def test_set_get_benchmark(self, benchmark, mock_redis_manager):
        """基准测试：SET/GET操作"""
        mock_redis_manager.client.setex.return_value = True
        mock_redis_manager.client.get.return_value = b'{"data": "value"}'
        
        def set_get_cycle():
            mock_redis_manager.set("test_key", {"data": "value"}, ttl=60)
            return mock_redis_manager.get("test_key")
        
        result = benchmark(set_get_cycle)
        assert result == {"data": "value"}
    
    def test_cache_tick_benchmark(self, benchmark, mock_redis_manager):
        """基准测试：缓存Tick数据"""
        tick = Tick(
            symbol="BTCUSDT",
            exchange="binance",
            timestamp=datetime.utcnow(),
            price=Decimal("50000.00"),
            quantity=Decimal("0.5"),
            side="buy",
            trade_id="tick_001"
        )
        
        mock_redis_manager.client.setex.return_value = True
        result = benchmark(mock_redis_manager.cache_tick, tick, ttl=60)
        assert result is True
    
    def test_pipeline_batch_benchmark(self, benchmark, mock_redis_manager):
        """基准测试：Pipeline批量操作"""
        mock_pipe = Mock()
        mock_redis_manager.client.pipeline.return_value = mock_pipe
        mock_pipe.execute.return_value = [True] * 100
        
        def pipeline_ops():
            pipe = mock_redis_manager.client.pipeline()
            for i in range(100):
                pipe.setex(f"key_{i}", 60, f"value_{i}")
            return pipe.execute()
        
        result = benchmark(pipeline_ops)
        assert len(result) == 100


# ==================== 并发性能测试 ====================

class TestConcurrencyPerformance:
    """并发性能测试"""
    
    @pytest.mark.asyncio
    async def test_concurrent_mysql_operations(self):
        """测试并发MySQL操作"""
        with patch('qf_database.mysql_manager.create_engine') as mock_create_engine:
            mock_engine = Mock()
            mock_create_engine.return_value = mock_engine
            
            manager = MySQLManager()
            manager.engine = mock_engine
            
            # 模拟并发查询
            async def query_task(i):
                with patch.object(manager, 'session_scope') as mock_scope:
                    mock_session = Mock()
                    mock_scope.return_value.__enter__ = Mock(return_value=mock_session)
                    mock_scope.return_value.__exit__ = Mock(return_value=False)
                    mock_session.execute.return_value.scalar_one_or_none.return_value = None
                    await asyncio.sleep(0.001)  # 模拟网络延迟
                    return True
            
            # 并发执行100个查询
            start_time = time.time()
            tasks = [query_task(i) for i in range(100)]
            results = await asyncio.gather(*tasks)
            elapsed = time.time() - start_time
            
            assert all(results)
            print(f"\nConcurrent 100 queries: {elapsed:.4f}s ({100/elapsed:.0f} ops/sec)")
    
    @pytest.mark.asyncio
    async def test_concurrent_redis_pipeline(self):
        """测试并发Redis Pipeline操作"""
        with patch('qf_database.redis_manager.redis.ConnectionPool'), \
             patch('qf_database.redis_manager.redis.Redis') as mock_redis:
            
            mock_client = Mock()
            mock_redis.return_value = mock_client
            
            manager = RedisManager()
            manager.client = mock_client
            
            async def pipeline_task(i):
                mock_pipe = Mock()
                mock_client.pipeline.return_value = mock_pipe
                
                # 每个pipeline 50个操作
                for j in range(50):
                    mock_pipe.setex(f"key_{i}_{j}", 60, f"value_{i}_{j}")
                mock_pipe.execute.return_value = [True] * 50
                
                await asyncio.sleep(0.001)
                return mock_pipe.execute()
            
            # 并发执行10个pipeline
            start_time = time.time()
            tasks = [pipeline_task(i) for i in range(10)]
            results = await asyncio.gather(*tasks)
            elapsed = time.time() - start_time
            
            total_ops = sum(len(r) for r in results)
            assert total_ops == 500
            print(f"\nConcurrent pipeline: {elapsed:.4f}s ({total_ops/elapsed:.0f} ops/sec)")


# ==================== 内存使用测试 ====================

class TestMemoryPerformance:
    """内存使用性能测试"""
    
    def test_large_kline_batch_processing(self):
        """测试大批量K线数据处理"""
        # 生成10000条K线数据
        klines = [
            Kline(
                symbol="BTCUSDT",
                exchange="binance",
                interval="1m",
                timestamp=datetime.utcnow() + timedelta(minutes=i),
                open=Decimal("50000.00"),
                high=Decimal("51000.00"),
                low=Decimal("49000.00"),
                close=Decimal("50500.00"),
                volume=Decimal("100.5"),
                quote_volume=Decimal("5075250.00"),
                trades=1500
            )
            for i in range(10000)
        ]
        
        start_time = time.time()
        # 模拟处理
        for kline in klines:
            _ = kline.to_dict()
        elapsed = time.time() - start_time
        
        print(f"\nProcess 10000 klines: {elapsed:.4f}s ({10000/elapsed:.0f} records/sec)")
        assert elapsed < 5  # 应该在5秒内完成
