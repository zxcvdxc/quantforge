"""高并发订单测试 - 性能测试和压力测试

测试批量订单处理、连接池、高并发场景下的系统稳定性。
"""

import sys
sys.path.insert(0, 'src')

import asyncio
import pytest
import pytest_asyncio
from datetime import datetime
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
    ConnectionStats,
    Order,
    OrderRateLimiter,
    OrderResult,
    OrderStatus,
    OrderType,
    PooledConnection,
    PriorityOrder,
    Side,
    AsyncTaskPool,
)


# ==================== Fixtures ====================

@pytest.fixture
def batch_config():
    """批量处理配置 fixture"""
    return BatchConfig(
        batch_size=10,
        batch_timeout_ms=50.0,
        max_concurrency=5,
        max_retries=2,
        retry_delay_ms=100.0,
        max_queue_size=100,
    )


@pytest.fixture
def connection_config():
    """连接配置 fixture"""
    return ConnectionConfig(
        max_connections=5,
        min_connections=1,
        connect_timeout=5.0,
        heartbeat_interval=30.0,
        enable_reconnect=True,
        max_reconnect_attempts=3,
    )


@pytest.fixture
def sample_orders():
    """示例订单列表 fixture"""
    return [
        Order(
            symbol=f"STOCK{i:03d}.SH",
            side=Side.BUY if i % 2 == 0 else Side.SELL,
            order_type=OrderType.LIMIT,
            quantity=Decimal("100"),
            price=Decimal(f"{10 + i}.50"),
            account_type=AccountType.A_STOCK,
        )
        for i in range(20)
    ]


# ==================== Test AsyncTaskPool ====================

class TestAsyncTaskPool:
    """异步任务池测试"""

    @pytest.mark.asyncio
    async def test_task_pool_submit(self):
        """测试任务提交"""
        pool = AsyncTaskPool(max_workers=3)

        async def task_func(x: int) -> int:
            await asyncio.sleep(0.01)
            return x * 2

        result = await pool.submit(task_func(5))
        assert result == 10

    @pytest.mark.asyncio
    async def test_task_pool_submit_many(self):
        """测试批量任务提交"""
        pool = AsyncTaskPool(max_workers=5)

        async def task_func(x: int) -> int:
            await asyncio.sleep(0.01)
            return x * x

        tasks = [task_func(i) for i in range(10)]
        results = await pool.submit_many(tasks)

        assert len(results) == 10
        assert results == [i * i for i in range(10)]

    @pytest.mark.asyncio
    async def test_task_pool_concurrency_limit(self):
        """测试并发限制"""
        pool = AsyncTaskPool(max_workers=2)

        running = 0
        max_running = 0

        async def task_func():
            nonlocal running, max_running
            running += 1
            max_running = max(max_running, running)
            await asyncio.sleep(0.05)
            running -= 1
            return max_running

        tasks = [pool.submit(task_func()) for _ in range(5)]
        results = await asyncio.gather(*tasks)

        assert max(results) <= 2

    @pytest.mark.asyncio
    async def test_task_pool_cancel_all(self):
        """测试取消所有任务"""
        pool = AsyncTaskPool(max_workers=5)

        async def long_task():
            await asyncio.sleep(10)
            return "done"

        # 提交一些任务
        futures = [pool.submit(long_task()) for _ in range(3)]
        await asyncio.sleep(0.01)

        # 取消所有
        await pool.cancel_all()

        # 检查统计
        stats = pool.get_stats()
        assert stats["active_tasks"] == 0

    def test_task_pool_stats(self):
        """测试任务池统计"""
        pool = AsyncTaskPool(max_workers=10)
        stats = pool.get_stats()

        assert stats["max_workers"] == 10
        assert stats["active_tasks"] == 0
        assert stats["available_slots"] == 10


# ==================== Test PooledConnection ====================

class TestPooledConnection:
    """连接池中的连接测试"""

    def test_connection_initial_state(self):
        """测试连接初始状态"""
        config = ConnectionConfig()
        conn = PooledConnection("test-1", config)

        assert conn.connection_id == "test-1"
        assert conn.state == ConnectionState.DISCONNECTED
        assert not conn.is_available
        assert not conn.in_use
        assert conn.age >= 0

    def test_connection_acquire_release(self):
        """测试连接获取和释放"""
        config = ConnectionConfig()
        conn = PooledConnection("test-1", config)

        # 手动设置为已连接状态
        conn.state = ConnectionState.CONNECTED

        assert conn.acquire()
        assert conn.in_use
        assert not conn.is_available

        conn.release()
        assert not conn.in_use

    def test_connection_cannot_acquire_when_in_use(self):
        """测试无法获取正在使用的连接"""
        config = ConnectionConfig()
        conn = PooledConnection("test-1", config)
        conn.state = ConnectionState.CONNECTED

        assert conn.acquire()
        assert not conn.acquire()  # 第二次获取应该失败

    def test_connection_cannot_acquire_when_disconnected(self):
        """测试无法获取未连接的连接"""
        config = ConnectionConfig()
        conn = PooledConnection("test-1", config)

        assert not conn.acquire()

    @pytest.mark.asyncio
    async def test_connection_connect(self):
        """测试连接建立"""
        config = ConnectionConfig()
        conn = PooledConnection("test-1", config)

        mock_connector = AsyncMock(return_value=MagicMock())

        result = await conn.connect(mock_connector)

        assert result is True
        assert conn.state == ConnectionState.CONNECTED
        mock_connector.assert_called_once()

    @pytest.mark.asyncio
    async def test_connection_connect_failure(self):
        """测试连接失败"""
        config = ConnectionConfig()
        conn = PooledConnection("test-1", config)

        mock_connector = AsyncMock(side_effect=Exception("Connection refused"))

        result = await conn.connect(mock_connector)

        assert result is False
        assert conn.state == ConnectionState.DISCONNECTED
        assert conn.stats.error_count == 1

    @pytest.mark.asyncio
    async def test_connection_disconnect(self):
        """测试连接断开"""
        config = ConnectionConfig()
        conn = PooledConnection("test-1", config)

        mock_connection = MagicMock()
        mock_connection.close = AsyncMock()

        conn._connection = mock_connection
        conn.state = ConnectionState.CONNECTED

        await conn.disconnect()

        assert conn.state == ConnectionState.CLOSED
        mock_connection.close.assert_called_once()

    @pytest.mark.asyncio
    async def test_connection_send(self):
        """测试发送消息"""
        config = ConnectionConfig()
        conn = PooledConnection("test-1", config)

        mock_connection = MagicMock()
        mock_connection.send = AsyncMock()

        conn._connection = mock_connection
        conn.state = ConnectionState.CONNECTED

        result = await conn.send("test message")

        assert result is True
        mock_connection.send.assert_called_once_with("test message")
        assert conn.stats.messages_sent == 1

    @pytest.mark.asyncio
    async def test_connection_send_not_connected(self):
        """测试未连接时发送失败"""
        config = ConnectionConfig()
        conn = PooledConnection("test-1", config)

        result = await conn.send("test message")

        assert result is False

    @pytest.mark.asyncio
    async def test_connection_receive(self):
        """测试接收消息"""
        config = ConnectionConfig()
        conn = PooledConnection("test-1", config)

        mock_connection = MagicMock()
        mock_connection.receive = AsyncMock(return_value="response")

        conn._connection = mock_connection
        conn.state = ConnectionState.CONNECTED

        result = await conn.receive()

        assert result == "response"
        assert conn.stats.messages_received == 1

    @pytest.mark.asyncio
    async def test_connection_receive_timeout(self):
        """测试接收超时"""
        config = ConnectionConfig(receive_timeout=0.01)
        conn = PooledConnection("test-1", config)

        mock_connection = MagicMock()
        mock_connection.receive = AsyncMock(side_effect=asyncio.TimeoutError())

        conn._connection = mock_connection
        conn.state = ConnectionState.CONNECTED

        result = await conn.receive()

        assert result is None

    def test_connection_handlers(self):
        """测试事件处理器"""
        config = ConnectionConfig()
        conn = PooledConnection("test-1", config)

        message_handler = MagicMock()
        error_handler = MagicMock()
        close_handler = MagicMock()

        conn.on_message(message_handler)
        conn.on_error(error_handler)
        conn.on_close(close_handler)

        # 测试消息通知
        conn.notify_message("test")
        message_handler.assert_called_once_with("test")

        # 测试错误通知
        error = Exception("test error")
        conn.notify_error(error)
        error_handler.assert_called_once_with(error)

    def test_connection_health_check(self):
        """测试连接健康检查"""
        config = ConnectionConfig(
            heartbeat_interval=1.0,
            heartbeat_timeout=0.5,
            max_idle_time=2.0,
        )
        conn = PooledConnection("test-1", config)
        conn.state = ConnectionState.CONNECTED
        conn._last_heartbeat = datetime.now().timestamp()

        assert conn.is_healthy

        # 模拟心跳超时
        conn._last_heartbeat = datetime.now().timestamp() - 10
        assert not conn.is_healthy


# ==================== Test ConnectionPool ====================

class TestConnectionPool:
    """连接池测试"""

    @pytest.mark.asyncio
    async def test_pool_start_stop(self):
        """测试连接池启动和停止"""
        config = ConnectionConfig(max_connections=3, min_connections=1)
        pool = ConnectionPool(config)

        mock_connector = AsyncMock(return_value=MagicMock())
        pool.set_connector(mock_connector)

        await pool.start()
        assert pool._running

        await pool.stop()
        assert not pool._running

    @pytest.mark.asyncio
    async def test_pool_acquire_release(self):
        """测试连接获取和释放"""
        config = ConnectionConfig(max_connections=2)
        pool = ConnectionPool(config)

        mock_connector = AsyncMock(return_value=MagicMock())
        pool.set_connector(mock_connector)

        await pool.start()

        # 获取连接
        conn = await pool.acquire(timeout=1.0)
        assert conn is not None

        # 释放连接
        await pool.release(conn)

        await pool.stop()

    @pytest.mark.asyncio
    async def test_pool_acquire_timeout(self):
        """测试连接获取超时"""
        config = ConnectionConfig(max_connections=1)
        pool = ConnectionPool(config)

        mock_connector = AsyncMock(return_value=MagicMock())
        pool.set_connector(mock_connector)

        await pool.start()

        # 获取唯一连接
        conn1 = await pool.acquire(timeout=0.1)
        assert conn1 is not None

        # 第二次获取应该超时
        conn2 = await pool.acquire(timeout=0.1)
        assert conn2 is None

        await pool.release(conn1)
        await pool.stop()

    @pytest.mark.asyncio
    async def test_pool_get_stats(self):
        """测试连接池统计"""
        config = ConnectionConfig(max_connections=3, min_connections=1)
        pool = ConnectionPool(config)

        mock_connector = AsyncMock(return_value=MagicMock())
        pool.set_connector(mock_connector)

        await pool.start()

        stats = pool.get_stats()
        assert "total_connections" in stats
        assert "available" in stats
        assert "in_use" in stats

        await pool.stop()

    @pytest.mark.asyncio
    async def test_pool_broadcast(self):
        """测试广播消息"""
        config = ConnectionConfig(max_connections=2, min_connections=2)
        pool = ConnectionPool(config)

        mock_connection = MagicMock()
        mock_connection.send = AsyncMock(return_value=True)

        mock_connector = AsyncMock(return_value=mock_connection)
        pool.set_connector(mock_connector)

        await pool.start()
        await asyncio.sleep(0.1)  # 等待连接建立

        results = await pool.broadcast("test message")

        assert len(results) == 2

        await pool.stop()


# ==================== Test BatchOrderProcessor ====================

class TestBatchOrderProcessor:
    """批量订单处理器测试"""

    @pytest.mark.asyncio
    async def test_processor_start_stop(self, batch_config):
        """测试处理器启动和停止"""
        processor = BatchOrderProcessor(batch_config)

        await processor.start()
        assert processor._running

        await processor.stop()
        assert not processor._running

    @pytest.mark.asyncio
    async def test_batch_send(self, batch_config, sample_orders):
        """测试批量发送订单"""
        processor = BatchOrderProcessor(batch_config)

        # 设置模拟处理器
        async def mock_send(orders: List[Order]) -> List[OrderResult]:
            return [
                OrderResult(success=True, order_id=o.order_id)
                for o in orders
            ]

        processor.set_handlers(
            send_handler=mock_send,
            query_handler=None,
            cancel_handler=None,
        )

        result = await processor.batch_send(sample_orders[:5])

        assert isinstance(result, BatchResult)
        assert result.success_count == 5
        assert result.failed_count == 0
        assert result.success_rate == 1.0

    @pytest.mark.asyncio
    async def test_batch_send_partial_failure(self, batch_config, sample_orders):
        """测试批量发送部分失败"""
        processor = BatchOrderProcessor(batch_config)

        async def mock_send(orders: List[Order]) -> List[OrderResult]:
            results = []
            for i, o in enumerate(orders):
                if i % 2 == 0:
                    results.append(OrderResult(success=True, order_id=o.order_id))
                else:
                    results.append(OrderResult(success=False, message="Failed"))
            return results

        processor.set_handlers(send_handler=mock_send, query_handler=None, cancel_handler=None)

        result = await processor.batch_send(sample_orders[:4])

        assert result.success_count == 2
        assert result.failed_count == 2
        assert result.success_rate == 0.5

    @pytest.mark.asyncio
    async def test_batch_query(self, batch_config):
        """测试批量查询"""
        processor = BatchOrderProcessor(batch_config)

        async def mock_query(order_id: str) -> Optional[Order]:
            return Order(
                symbol="TEST.SH",
                side=Side.BUY,
                order_type=OrderType.LIMIT,
                quantity=Decimal("100"),
                order_id=order_id,
            )

        processor.set_handlers(send_handler=None, query_handler=mock_query, cancel_handler=None)

        order_ids = ["id1", "id2", "id3"]
        results = await processor.batch_query(order_ids)

        assert len(results) == 3
        assert all(oid in results for oid in order_ids)

    @pytest.mark.asyncio
    async def test_batch_cancel(self, batch_config):
        """测试批量撤销"""
        processor = BatchOrderProcessor(batch_config)

        async def mock_cancel(order_id: str) -> OrderResult:
            return OrderResult(success=True, order_id=order_id)

        processor.set_handlers(send_handler=None, query_handler=None, cancel_handler=mock_cancel)

        order_ids = ["id1", "id2", "id3"]
        result = await processor.batch_cancel(order_ids)

        assert result.success_count == 3
        assert result.failed_count == 0

    @pytest.mark.asyncio
    async def test_batch_result_get_by_order_id(self, batch_config, sample_orders):
        """测试批量结果查询"""
        processor = BatchOrderProcessor(batch_config)

        async def mock_send(orders: List[Order]) -> List[OrderResult]:
            return [
                OrderResult(success=True, order_id=o.order_id)
                for o in orders
            ]

        processor.set_handlers(send_handler=mock_send, query_handler=None, cancel_handler=None)

        orders = sample_orders[:3]
        result = await processor.batch_send(orders)

        order_id = orders[0].order_id
        found_result = result.get_by_order_id(order_id)

        assert found_result is not None
        assert found_result.success is True

        not_found = result.get_by_order_id("nonexistent")
        assert not_found is None

    @pytest.mark.asyncio
    async def test_processor_get_stats(self, batch_config):
        """测试处理器统计"""
        processor = BatchOrderProcessor(batch_config)

        stats = processor.get_stats()

        assert "total_sent" in stats
        assert "queue_size" in stats
        assert "task_pool" in stats


# ==================== Test OrderRateLimiter ====================

class TestOrderRateLimiter:
    """订单速率限制器测试"""

    @pytest.mark.asyncio
    async def test_rate_limiter_acquire(self):
        """测试速率限制获取"""
        limiter = OrderRateLimiter(
            max_orders_per_second=100.0,
            max_orders_per_minute=1000.0,
        )

        # 应该能够获取令牌
        assert await limiter.acquire(1.0) is True

        # 连续获取会消耗令牌
        acquired = 0
        for _ in range(200):
            if await limiter.acquire(1.0):
                acquired += 1
            else:
                break

        # 应该成功获取一些令牌
        assert acquired >= 1

    @pytest.mark.asyncio
    async def test_rate_limiter_wait_and_acquire(self):
        """测试等待并获取"""
        limiter = OrderRateLimiter(
            max_orders_per_second=2.0,
            max_orders_per_minute=100.0,
        )

        # 消耗所有令牌
        for _ in range(5):
            await limiter.acquire(1.0)

        # 等待并获取
        result = await limiter.wait_and_acquire(1.0, timeout=1.0)
        assert result is True

    @pytest.mark.asyncio
    async def test_rate_limiter_wait_timeout(self):
        """测试等待超时"""
        limiter = OrderRateLimiter(
            max_orders_per_second=0.1,  # 非常慢的速率
            max_orders_per_minute=0.1,
        )

        # 消耗令牌
        await limiter.acquire(1.0)

        # 应该超时
        result = await limiter.wait_and_acquire(1.0, timeout=0.01)
        assert result is False


# ==================== Test PriorityOrder ====================

class TestPriorityOrder:
    """优先级订单测试"""

    def test_priority_order_comparison(self):
        """测试优先级比较"""
        order1 = PriorityOrder(priority=1, order=MagicMock())
        order2 = PriorityOrder(priority=2, order=MagicMock())

        assert order1 < order2
        assert not order2 < order1

    def test_priority_order_same_priority_fifo(self):
        """测试相同优先级时FIFO"""
        from datetime import datetime, timedelta

        now = datetime.now()
        order1 = PriorityOrder(priority=5, order=MagicMock(), timestamp=now)
        order2 = PriorityOrder(priority=5, order=MagicMock(), timestamp=now + timedelta(seconds=1))

        assert order1 < order2


# ==================== High Concurrency Tests ====================

class TestHighConcurrency:
    """高并发测试"""

    @pytest.mark.asyncio
    async def test_concurrent_batch_send(self, batch_config):
        """测试并发批量发送"""
        processor = BatchOrderProcessor(batch_config)

        async def mock_send(orders: List[Order]) -> List[OrderResult]:
            await asyncio.sleep(0.01)  # 模拟网络延迟
            return [
                OrderResult(success=True, order_id=o.order_id)
                for o in orders
            ]

        processor.set_handlers(send_handler=mock_send, query_handler=None, cancel_handler=None)
        await processor.start()

        # 并发发送多个批次
        tasks = []
        for i in range(5):
            orders = [
                Order(
                    symbol=f"STOCK{i}{j}.SH",
                    side=Side.BUY,
                    order_type=OrderType.LIMIT,
                    quantity=Decimal("100"),
                )
                for j in range(10)
            ]
            tasks.append(processor.batch_send(orders))

        results = await asyncio.gather(*tasks)

        await processor.stop()

        # 验证所有批次都成功
        assert len(results) == 5
        for result in results:
            assert result.success_count == 10

    @pytest.mark.asyncio
    async def test_connection_pool_under_load(self):
        """测试连接池在负载下的表现"""
        config = ConnectionConfig(max_connections=5, min_connections=2)
        pool = ConnectionPool(config)

        mock_connection = MagicMock()
        mock_connection.send = AsyncMock(return_value=True)

        mock_connector = AsyncMock(return_value=mock_connection)
        pool.set_connector(mock_connector)

        await pool.start()
        await asyncio.sleep(0.1)

        # 模拟高并发获取连接
        async def worker():
            conn = await pool.acquire(timeout=1.0)
            if conn:
                await conn.send("message")
                await asyncio.sleep(0.01)
                await pool.release(conn)
                return True
            return False

        tasks = [worker() for _ in range(20)]
        results = await asyncio.gather(*tasks)

        await pool.stop()

        # 大部分应该成功
        assert sum(results) >= 15

    @pytest.mark.asyncio
    async def test_batch_processor_under_load(self, batch_config):
        """测试批量处理器在高负载下的表现"""
        processor = BatchOrderProcessor(batch_config)

        async def mock_send(orders: List[Order]) -> List[OrderResult]:
            await asyncio.sleep(0.005)
            return [OrderResult(success=True, order_id=o.order_id) for o in orders]

        processor.set_handlers(send_handler=mock_send, query_handler=None, cancel_handler=None)
        await processor.start()

        # 生成大量订单
        total_orders = 100
        orders = [
            Order(
                symbol=f"LOAD{i:03d}.SH",
                side=Side.BUY,
                order_type=OrderType.LIMIT,
                quantity=Decimal("100"),
            )
            for i in range(total_orders)
        ]

        start_time = datetime.now()
        result = await processor.batch_send(orders, batch_size=20)
        duration = (datetime.now() - start_time).total_seconds()

        await processor.stop()

        assert result.success_count == total_orders
        assert duration < 5.0  # 应该在5秒内完成

    @pytest.mark.asyncio
    async def test_mixed_operations(self, batch_config):
        """测试混合操作"""
        processor = BatchOrderProcessor(batch_config)

        send_count = 0
        query_count = 0
        cancel_count = 0

        async def mock_send(orders: List[Order]) -> List[OrderResult]:
            nonlocal send_count
            send_count += len(orders)
            return [OrderResult(success=True, order_id=o.order_id) for o in orders]

        async def mock_query(order_id: str) -> Optional[Order]:
            nonlocal query_count
            query_count += 1
            return Order(symbol="TEST.SH", side=Side.BUY, order_type=OrderType.LIMIT, quantity=Decimal("100"))

        async def mock_cancel(order_id: str) -> OrderResult:
            nonlocal cancel_count
            cancel_count += 1
            return OrderResult(success=True, order_id=order_id)

        processor.set_handlers(
            send_handler=mock_send,
            query_handler=mock_query,
            cancel_handler=mock_cancel,
        )
        await processor.start()

        # 执行混合操作
        orders = [Order(symbol=f"MIX{i}.SH", side=Side.BUY, order_type=OrderType.LIMIT, quantity=Decimal("100")) for i in range(10)]

        send_task = processor.batch_send(orders[:5])
        query_task = processor.batch_query([f"id{i}" for i in range(5)])
        cancel_task = processor.batch_cancel([f"id{i}" for i in range(5)])

        await asyncio.gather(send_task, query_task, cancel_task)

        await processor.stop()

        assert send_count == 5
        assert query_count == 5
        assert cancel_count == 5


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
