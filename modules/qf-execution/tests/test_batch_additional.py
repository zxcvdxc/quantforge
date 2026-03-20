"""批量处理器和连接池的额外测试

覆盖更多边界情况和错误处理路径。
"""

import sys
sys.path.insert(0, 'src')

import asyncio
import pytest
from datetime import datetime, timedelta
from decimal import Decimal
from typing import List, Optional
from unittest.mock import AsyncMock, MagicMock, Mock, patch

from qf_execution import (
    AccountType,
    BatchConfig,
    BatchOrderProcessor,
    BatchResult,
    ConnectionConfig,
    ConnectionPool,
    ConnectionState,
    Order,
    OrderRateLimiter,
    OrderResult,
    OrderStatus,
    OrderType,
    PooledConnection,
    Side,
    AsyncTaskPool,
)


# ==================== Test BatchOrderProcessor Additional ====================

class TestBatchOrderProcessorAdditional:
    """批量订单处理器额外测试"""
    
    @pytest.mark.asyncio
    async def test_batch_send_without_handler(self):
        """测试没有设置处理器时的批量发送"""
        processor = BatchOrderProcessor()
        
        orders = [
            Order(symbol="TEST.SH", side=Side.BUY, order_type=OrderType.LIMIT, quantity=Decimal("100"))
            for _ in range(3)
        ]
        
        # 没有设置 send_handler
        result = await processor.batch_send(orders)
        
        assert result.success_count == 0
        assert result.failed_count == 3
        assert all(not r.success for _, r in result.results)
    
    @pytest.mark.asyncio
    async def test_batch_query_without_handler(self):
        """测试没有设置处理器时的批量查询"""
        processor = BatchOrderProcessor()
        
        order_ids = ["id1", "id2", "id3"]
        results = await processor.batch_query(order_ids)
        
        assert all(results[oid] is None for oid in order_ids)
    
    @pytest.mark.asyncio
    async def test_batch_cancel_without_handler(self):
        """测试没有设置处理器时的批量撤销"""
        processor = BatchOrderProcessor()
        
        order_ids = ["id1", "id2", "id3"]
        result = await processor.batch_cancel(order_ids)
        
        assert result.success_count == 0
        assert result.failed_count == 3
    
    @pytest.mark.asyncio
    async def test_batch_send_with_exception(self):
        """测试批量发送时发生异常"""
        processor = BatchOrderProcessor()
        
        async def failing_send(orders):
            raise Exception("Network error")
        
        processor.set_handlers(send_handler=failing_send, query_handler=None, cancel_handler=None)
        
        orders = [
            Order(symbol="TEST.SH", side=Side.BUY, order_type=OrderType.LIMIT, quantity=Decimal("100"))
            for _ in range(3)
        ]
        
        result = await processor.batch_send(orders)
        
        assert result.failed_count == 3
        assert all(r.error_code == "BATCH_ERROR" for _, r in result.results)
    
    @pytest.mark.asyncio
    async def test_batch_processor_large_batch(self):
        """测试大批量处理"""
        config = BatchConfig(batch_size=5)
        processor = BatchOrderProcessor(config)
        
        async def mock_send(orders):
            return [OrderResult(success=True, order_id=o.order_id) for o in orders]
        
        processor.set_handlers(send_handler=mock_send, query_handler=None, cancel_handler=None)
        
        # 创建超过批次大小的订单
        orders = [
            Order(symbol=f"BATCH{i}.SH", side=Side.BUY, order_type=OrderType.LIMIT, quantity=Decimal("100"))
            for i in range(12)
        ]
        
        result = await processor.batch_send(orders)
        
        assert result.success_count == 12
    
    @pytest.mark.asyncio
    async def test_batch_processor_empty_orders(self):
        """测试空订单列表"""
        processor = BatchOrderProcessor()
        
        result = await processor.batch_send([])
        
        assert result.success_count == 0
        assert result.failed_count == 0
        assert len(result.results) == 0
    
    @pytest.mark.asyncio
    async def test_batch_processor_start_stop_idempotent(self):
        """测试启动和停止的幂等性"""
        processor = BatchOrderProcessor()
        
        # 多次启动
        await processor.start()
        await processor.start()
        assert processor._running
        
        # 多次停止
        await processor.stop()
        await processor.stop()
        assert not processor._running


# ==================== Test ConnectionPool Additional ====================

class TestConnectionPoolAdditional:
    """连接池额外测试"""
    
    @pytest.mark.asyncio
    async def test_pool_without_connector(self):
        """测试没有设置连接器的连接池"""
        config = ConnectionConfig()
        pool = ConnectionPool(config)
        
        await pool.start()
        
        # 无法获取连接
        conn = await pool.acquire(timeout=0.1)
        assert conn is None
        
        await pool.stop()
    
    @pytest.mark.asyncio
    async def test_pool_maintenance_removes_expired(self):
        """测试维护循环移除过期连接"""
        config = ConnectionConfig(
            max_connections=3,
            min_connections=1,
            max_lifetime=0.1,  # 很短的存活时间
        )
        pool = ConnectionPool(config)
        
        mock_connector = AsyncMock(return_value=MagicMock())
        pool.set_connector(mock_connector)
        
        await pool.start()
        await asyncio.sleep(0.05)
        
        # 等待连接过期
        await asyncio.sleep(0.2)
        
        # 过期连接应该被移除
        stats = pool.get_stats()
        # 最小连接数应该被保持
        assert stats["total_connections"] >= config.min_connections
        
        await pool.stop()
    
    @pytest.mark.asyncio
    async def test_pool_reconnect_failed(self):
        """测试重连失败"""
        config = ConnectionConfig(
            max_connections=1,
            enable_reconnect=True,
            max_reconnect_attempts=1,
        )
        pool = ConnectionPool(config)
        
        # 第一次连接成功，之后失败
        call_count = 0
        async def failing_connector():
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return MagicMock()
            raise Exception("Reconnect failed")
        
        pool.set_connector(failing_connector)
        
        await pool.start()
        await asyncio.sleep(0.1)
        
        # 模拟连接断开
        for conn in pool._connections.values():
            conn.state = ConnectionState.DISCONNECTED
        
        # 等待重连尝试
        await asyncio.sleep(0.2)
        
        await pool.stop()
    
    @pytest.mark.asyncio
    async def test_pool_broadcast_no_connections(self):
        """测试没有连接时的广播"""
        config = ConnectionConfig(max_connections=0)
        pool = ConnectionPool(config)
        
        results = await pool.broadcast("message")
        
        assert len(results) == 0
    
    @pytest.mark.asyncio
    async def test_pooled_connection_methods(self):
        """测试连接的各种方法"""
        config = ConnectionConfig()
        conn = PooledConnection("test-1", config)
        
        # 测试不同 send 方法
        conn.state = ConnectionState.CONNECTED
        
        # send_str
        mock_ws = MagicMock()
        mock_ws.send_str = AsyncMock()
        conn._connection = mock_ws
        
        result = await conn.send("test")
        assert result is True
        mock_ws.send_str.assert_called_once_with("test")
        
        # send_bytes
        mock_ws2 = MagicMock()
        mock_ws2.send_bytes = AsyncMock()
        conn._connection = mock_ws2
        
        result = await conn.send(b"test")
        assert result is True
        mock_ws2.send_bytes.assert_called_once_with(b"test")


# ==================== Test ConnectionState ====================

class TestConnectionState:
    """连接状态测试"""
    
    def test_connection_state_values(self):
        """测试连接状态值"""
        assert ConnectionState.DISCONNECTED.name == "DISCONNECTED"
        assert ConnectionState.CONNECTING.name == "CONNECTING"
        assert ConnectionState.CONNECTED.name == "CONNECTED"
        assert ConnectionState.RECONNECTING.name == "RECONNECTING"
        assert ConnectionState.CLOSED.name == "CLOSED"


# ==================== Test ConnectionStats ====================

class TestConnectionStats:
    """连接统计测试"""
    
    def test_stats_default_values(self):
        """测试统计默认值"""
        from qf_execution.connection_pool import ConnectionStats
        stats = ConnectionStats()
        
        assert stats.messages_sent == 0
        assert stats.messages_received == 0
        assert stats.reconnect_count == 0
        assert stats.error_count == 0


# ==================== Test BatchResult ====================

class TestBatchResultAdditional:
    """批量结果额外测试"""
    
    def test_batch_result_empty(self):
        """测试空结果"""
        result = BatchResult()
        
        assert result.success_count == 0
        assert result.failed_count == 0
        assert result.success_rate == 0.0
        assert result.get_by_order_id("any") is None
    
    def test_batch_result_zero_success_rate(self):
        """测试零成功率"""
        result = BatchResult(
            success_count=0,
            failed_count=5,
            results=[("id1", OrderResult(success=False, message="Error"))],
        )
        
        assert result.success_rate == 0.0
    
    def test_batch_result_full_success(self):
        """测试全部成功"""
        result = BatchResult(
            success_count=5,
            failed_count=0,
            results=[
                (f"id{i}", OrderResult(success=True, order_id=f"id{i}"))
                for i in range(5)
            ],
        )
        
        assert result.success_rate == 1.0


# ==================== Test AsyncTaskPool Additional ====================

class TestAsyncTaskPoolAdditional:
    """异步任务池额外测试"""
    
    @pytest.mark.asyncio
    async def test_task_pool_exception_handling(self):
        """测试任务异常处理"""
        pool = AsyncTaskPool(max_workers=3)
        
        async def failing_task():
            raise ValueError("Task failed")
        
        with pytest.raises(ValueError):
            await pool.submit(failing_task())
    
    @pytest.mark.asyncio
    async def test_task_pool_submit_many_with_failures(self):
        """测试批量提交部分失败"""
        pool = AsyncTaskPool(max_workers=5)
        
        async def mixed_task(should_fail):
            if should_fail:
                raise ValueError("Failed")
            return "success"
        
        tasks = [mixed_task(i % 2 == 0) for i in range(4)]
        
        # 应该抛出异常
        with pytest.raises(ValueError):
            await pool.submit_many(tasks)


# ==================== Integration Tests ====================

class TestIntegrationAdditional:
    """额外集成测试"""
    
    @pytest.mark.asyncio
    async def test_batch_processor_with_connection_pool(self):
        """测试批量处理器与连接池集成"""
        conn_config = ConnectionConfig(max_connections=3)
        conn_pool = ConnectionPool(conn_config)
        
        batch_config = BatchConfig(max_concurrency=5)
        processor = BatchOrderProcessor(batch_config, conn_pool)
        
        # 设置模拟处理器
        async def mock_send(orders):
            return [OrderResult(success=True, order_id=o.order_id) for o in orders]
        
        processor.set_handlers(send_handler=mock_send, query_handler=None, cancel_handler=None)
        
        await processor.start()
        
        orders = [
            Order(symbol=f"INT{i}.SH", side=Side.BUY, order_type=OrderType.LIMIT, quantity=Decimal("100"))
            for i in range(10)
        ]
        
        result = await processor.batch_send(orders)
        
        assert result.success_count == 10
        
        await processor.stop()
    
    @pytest.mark.asyncio
    async def test_end_to_end_batch_processing(self):
        """测试端到端批处理流程"""
        processor = BatchOrderProcessor(BatchConfig(batch_size=5))
        
        processed_orders = []
        
        async def mock_send(orders):
            processed_orders.extend(orders)
            return [OrderResult(success=True, order_id=o.order_id) for o in orders]
        
        processor.set_handlers(send_handler=mock_send, query_handler=None, cancel_handler=None)
        await processor.start()
        
        # 发送订单
        orders = [
            Order(symbol=f"E2E{i}.SH", side=Side.BUY, order_type=OrderType.LIMIT, quantity=Decimal("100"))
            for i in range(15)
        ]
        
        send_result = await processor.batch_send(orders)
        
        # 查询订单
        order_ids = [o.order_id for o in orders[:5]]
        
        async def mock_query(oid):
            return next((o for o in orders if o.order_id == oid), None)
        
        processor._query_handler = mock_query
        query_results = await processor.batch_query(order_ids)
        
        await processor.stop()
        
        assert send_result.success_count == 15
        assert len(query_results) == 5


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
