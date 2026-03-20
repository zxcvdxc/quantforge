"""批量订单处理器 - 高性能异步订单处理

提供订单批量处理功能，支持批量发送、批量查询、批量撤销等操作，
通过连接池和异步批处理大幅提升订单处理性能。
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any, Callable, Coroutine, Dict, List, Optional, Tuple, TypeVar, Generic
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor

from .models import Order, OrderResult, OrderStatus, Side, OrderType, AccountType
from .connection_pool import ConnectionPool, AsyncTaskPool

logger = logging.getLogger(__name__)

T = TypeVar('T')


@dataclass
class BatchConfig:
    """批量处理配置"""
    # 批处理大小
    batch_size: int = 100
    
    # 批处理超时（毫秒）
    batch_timeout_ms: float = 50.0
    
    # 最大并发数
    max_concurrency: int = 10
    
    # 重试配置
    max_retries: int = 3
    retry_delay_ms: float = 100.0
    
    # 队列配置
    max_queue_size: int = 10000
    
    # 是否启用优先级
    enable_priority: bool = True


@dataclass
class BatchResult:
    """批量操作结果"""
    success_count: int = 0
    failed_count: int = 0
    results: List[Tuple[str, OrderResult]] = field(default_factory=list)
    duration_ms: float = 0.0
    
    def get_by_order_id(self, order_id: str) -> Optional[OrderResult]:
        """根据订单ID获取结果"""
        for oid, result in self.results:
            if oid == order_id:
                return result
        return None
    
    @property
    def success_rate(self) -> float:
        """成功率"""
        total = self.success_count + self.failed_count
        return self.success_count / total if total > 0 else 0.0


@dataclass
class PriorityOrder:
    """带优先级的订单"""
    priority: int  # 数值越小优先级越高
    order: Order
    timestamp: datetime = field(default_factory=datetime.now)
    
    def __lt__(self, other: PriorityOrder) -> bool:
        # 先比较优先级，再比较时间戳（FIFO）
        if self.priority != other.priority:
            return self.priority < other.priority
        return self.timestamp < other.timestamp


class BatchOrderProcessor:
    """批量订单处理器
    
    功能：
    - 订单批量发送，降低网络延迟
    - 批量查询和撤销
    - 优先级队列支持
    - 自动批处理和流量控制
    - 连接池复用
    
    Example:
        processor = BatchOrderProcessor(config)
        await processor.start()
        
        # 批量发送订单
        orders = [order1, order2, order3]
        results = await processor.batch_send(orders)
        
        # 批量查询
        order_ids = ["id1", "id2", "id3"]
        results = await processor.batch_query(order_ids)
    """
    
    def __init__(
        self,
        config: Optional[BatchConfig] = None,
        connection_pool: Optional[ConnectionPool] = None,
    ) -> None:
        self.config = config or BatchConfig()
        self.connection_pool = connection_pool
        self._task_pool = AsyncTaskPool(max_workers=self.config.max_concurrency)
        
        # 订单队列
        self._send_queue: asyncio.PriorityQueue[Tuple[int, int, PriorityOrder]] = asyncio.PriorityQueue(
            maxsize=self.config.max_queue_size
        )
        self._query_queue: asyncio.Queue[Tuple[str, asyncio.Future]] = asyncio.Queue()
        self._cancel_queue: asyncio.Queue[Tuple[str, asyncio.Future]] = asyncio.Queue()
        
        # 处理器状态
        self._running = False
        self._batch_processor_task: Optional[asyncio.Task] = None
        self._sequence = 0  # 用于优先级队列排序
        
        # 回调函数
        self._send_handler: Optional[Callable[[List[Order]], Coroutine[Any, Any, List[OrderResult]]]] = None
        self._query_handler: Optional[Callable[[str], Coroutine[Any, Any, Optional[Order]]]] = None
        self._cancel_handler: Optional[Callable[[str], Coroutine[Any, Any, OrderResult]]] = None
        
        # 统计
        self._stats = {
            "total_sent": 0,
            "total_queried": 0,
            "total_cancelled": 0,
            "batches_processed": 0,
            "queue_high_watermark": 0,
        }
    
    def set_handlers(
        self,
        send_handler: Callable[[List[Order]], Coroutine[Any, Any, List[OrderResult]]],
        query_handler: Callable[[str], Coroutine[Any, Any, Optional[Order]]],
        cancel_handler: Callable[[str], Coroutine[Any, Any, OrderResult]],
    ) -> None:
        """设置处理函数"""
        self._send_handler = send_handler
        self._query_handler = query_handler
        self._cancel_handler = cancel_handler
    
    async def start(self) -> None:
        """启动处理器"""
        if self._running:
            return
        
        self._running = True
        
        # 启动批处理任务
        self._batch_processor_task = asyncio.create_task(self._batch_processor_loop())
        
        logger.info("Batch order processor started")
    
    async def stop(self) -> None:
        """停止处理器"""
        if not self._running:
            return
        
        self._running = False
        
        # 取消批处理任务
        if self._batch_processor_task:
            self._batch_processor_task.cancel()
            try:
                await self._batch_processor_task
            except asyncio.CancelledError:
                pass
        
        # 取消所有任务池中的任务
        await self._task_pool.cancel_all()
        
        logger.info("Batch order processor stopped")
    
    async def submit_order(
        self,
        order: Order,
        priority: int = 5,
        wait_result: bool = True,
        timeout: float = 30.0,
    ) -> Optional[OrderResult]:
        """提交单个订单到队列
        
        Args:
            order: 订单对象
            priority: 优先级（1-10，1最高）
            wait_result: 是否等待处理结果
            timeout: 等待超时时间
        
        Returns:
            OrderResult: 处理结果，如果 wait_result=False 返回 None
        """
        priority_order = PriorityOrder(priority=priority, order=order)
        
        if wait_result:
            future: asyncio.Future[OrderResult] = asyncio.get_event_loop().create_future()
            
            try:
                self._sequence += 1
                await asyncio.wait_for(
                    self._send_queue.put((priority, self._sequence, priority_order)),
                    timeout=5.0
                )
            except asyncio.TimeoutError:
                return OrderResult(
                    success=False,
                    message="Queue is full",
                    error_code="QUEUE_FULL",
                )
            
            try:
                result = await asyncio.wait_for(future, timeout=timeout)
                return result
            except asyncio.TimeoutError:
                return OrderResult(
                    success=False,
                    message="Processing timeout",
                    error_code="TIMEOUT",
                )
        else:
            self._sequence += 1
            try:
                await asyncio.wait_for(
                    self._send_queue.put((priority, self._sequence, priority_order)),
                    timeout=5.0
                )
                return None
            except asyncio.TimeoutError:
                return OrderResult(
                    success=False,
                    message="Queue is full",
                    error_code="QUEUE_FULL",
                )
    
    async def batch_send(
        self,
        orders: List[Order],
        priority: int = 5,
        batch_size: Optional[int] = None,
    ) -> BatchResult:
        """批量发送订单
        
        Args:
            orders: 订单列表
            priority: 优先级
            batch_size: 批处理大小（默认使用配置）
        
        Returns:
            BatchResult: 批量处理结果
        """
        start_time = datetime.now()
        batch_size = batch_size or self.config.batch_size
        
        # 分批处理
        all_results: List[Tuple[str, OrderResult]] = []
        
        for i in range(0, len(orders), batch_size):
            batch = orders[i:i + batch_size]
            batch_results = await self._process_send_batch(batch, priority)
            all_results.extend(batch_results)
        
        duration = (datetime.now() - start_time).total_seconds() * 1000
        
        success_count = sum(1 for _, r in all_results if r.success)
        failed_count = len(all_results) - success_count
        
        return BatchResult(
            success_count=success_count,
            failed_count=failed_count,
            results=all_results,
            duration_ms=duration,
        )
    
    async def batch_query(
        self,
        order_ids: List[str],
        batch_size: Optional[int] = None,
    ) -> Dict[str, Optional[Order]]:
        """批量查询订单
        
        Args:
            order_ids: 订单ID列表
            batch_size: 批处理大小
        
        Returns:
            Dict[str, Optional[Order]]: 订单ID到订单的映射
        """
        batch_size = batch_size or self.config.batch_size
        results: Dict[str, Optional[Order]] = {}
        
        for i in range(0, len(order_ids), batch_size):
            batch = order_ids[i:i + batch_size]
            batch_results = await self._process_query_batch(batch)
            results.update(batch_results)
        
        return results
    
    async def batch_cancel(
        self,
        order_ids: List[str],
        batch_size: Optional[int] = None,
    ) -> BatchResult:
        """批量撤销订单
        
        Args:
            order_ids: 订单ID列表
            batch_size: 批处理大小
        
        Returns:
            BatchResult: 批量处理结果
        """
        start_time = datetime.now()
        batch_size = batch_size or self.config.batch_size
        
        all_results: List[Tuple[str, OrderResult]] = []
        
        for i in range(0, len(order_ids), batch_size):
            batch = order_ids[i:i + batch_size]
            batch_results = await self._process_cancel_batch(batch)
            all_results.extend(batch_results)
        
        duration = (datetime.now() - start_time).total_seconds() * 1000
        
        success_count = sum(1 for _, r in all_results if r.success)
        failed_count = len(all_results) - success_count
        
        return BatchResult(
            success_count=success_count,
            failed_count=failed_count,
            results=all_results,
            duration_ms=duration,
        )
    
    async def _batch_processor_loop(self) -> None:
        """批处理主循环"""
        while self._running:
            try:
                batch: List[Tuple[int, int, PriorityOrder]] = []
                futures: List[asyncio.Future] = []
                
                # 收集一批订单
                try:
                    # 等待第一个订单
                    item = await asyncio.wait_for(
                        self._send_queue.get(),
                        timeout=1.0
                    )
                    batch.append(item)
                    
                    # 收集更多订单，直到达到批处理大小或超时
                    deadline = asyncio.get_event_loop().time() + (self.config.batch_timeout_ms / 1000)
                    while len(batch) < self.config.batch_size:
                        timeout = max(0, deadline - asyncio.get_event_loop().time())
                        if timeout <= 0:
                            break
                        try:
                            item = await asyncio.wait_for(
                                self._send_queue.get(),
                                timeout=timeout
                            )
                            batch.append(item)
                        except asyncio.TimeoutError:
                            break
                except asyncio.TimeoutError:
                    continue
                
                # 处理这批订单
                if batch:
                    orders = [item[2].order for item in batch]
                    results = await self._process_send_batch_with_retry(orders)
                    
                    # 设置 future 结果
                    for (_, _, priority_order), (_, result) in zip(batch, results):
                        # 通知等待的调用者
                        pass  # 实际实现中需要设置 future
                    
                    self._stats["batches_processed"] += 1
                    
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Batch processor error: {e}")
                await asyncio.sleep(1.0)
    
    async def _process_send_batch(
        self,
        orders: List[Order],
        priority: int = 5,
    ) -> List[Tuple[str, OrderResult]]:
        """处理发送批次"""
        if not self._send_handler:
            return [
                (order.order_id, OrderResult(
                    success=False,
                    message="No send handler configured",
                    error_code="NO_HANDLER",
                ))
                for order in orders
            ]
        
        try:
            results = await self._task_pool.submit(self._send_handler(orders))
            return [(order.order_id, result) for order, result in zip(orders, results)]
        except Exception as e:
            logger.error(f"Batch send error: {e}")
            return [
                (order.order_id, OrderResult(
                    success=False,
                    message=str(e),
                    error_code="BATCH_ERROR",
                ))
                for order in orders
            ]
    
    async def _process_send_batch_with_retry(
        self,
        orders: List[Order],
    ) -> List[Tuple[str, OrderResult]]:
        """带重试的批处理"""
        results = await self._process_send_batch(orders)
        
        # 收集失败的订单
        failed_orders = [
            order for order, (_, result) in zip(orders, results)
            if not result.success
        ]
        
        # 重试
        for attempt in range(self.config.max_retries):
            if not failed_orders:
                break
            
            await asyncio.sleep(self.config.retry_delay_ms / 1000 * (2 ** attempt))
            
            retry_results = await self._process_send_batch(failed_orders)
            
            # 更新结果
            for order, (_, result) in zip(failed_orders, retry_results):
                idx = next(i for i, (oid, _) in enumerate(results) if oid == order.order_id)
                results[idx] = (order.order_id, result)
            
            failed_orders = [
                order for order, (_, result) in zip(failed_orders, retry_results)
                if not result.success
            ]
        
        return results
    
    async def _process_query_batch(
        self,
        order_ids: List[str],
    ) -> Dict[str, Optional[Order]]:
        """处理查询批次"""
        if not self._query_handler:
            return {order_id: None for order_id in order_ids}
        
        async def query_one(order_id: str) -> Tuple[str, Optional[Order]]:
            try:
                order = await self._query_handler(order_id)
                return (order_id, order)
            except Exception as e:
                logger.error(f"Query error for {order_id}: {e}")
                return (order_id, None)
        
        tasks = [query_one(order_id) for order_id in order_ids]
        results = await asyncio.gather(*tasks)
        
        return dict(results)
    
    async def _process_cancel_batch(
        self,
        order_ids: List[str],
    ) -> List[Tuple[str, OrderResult]]:
        """处理撤销批次"""
        if not self._cancel_handler:
            return [
                (order_id, OrderResult(
                    success=False,
                    message="No cancel handler configured",
                    error_code="NO_HANDLER",
                ))
                for order_id in order_ids
            ]
        
        async def cancel_one(order_id: str) -> Tuple[str, OrderResult]:
            try:
                result = await self._cancel_handler(order_id)
                return (order_id, result)
            except Exception as e:
                logger.error(f"Cancel error for {order_id}: {e}")
                return (order_id, OrderResult(
                    success=False,
                    message=str(e),
                    error_code="CANCEL_ERROR",
                ))
        
        tasks = [cancel_one(order_id) for order_id in order_ids]
        results = await asyncio.gather(*tasks)
        
        return list(results)
    
    def get_stats(self) -> Dict[str, Any]:
        """获取统计信息"""
        return {
            **self._stats,
            "queue_size": self._send_queue.qsize(),
            "task_pool": self._task_pool.get_stats(),
        }


class OrderRateLimiter:
    """订单速率限制器
    
    用于控制订单发送频率，防止超过交易所限制。
    """
    
    def __init__(
        self,
        max_orders_per_second: float = 100.0,
        max_orders_per_minute: float = 1000.0,
    ) -> None:
        self.max_orders_per_second = max_orders_per_second
        self.max_orders_per_minute = max_orders_per_minute
        
        self._second_bucket = 0.0
        self._minute_bucket = 0.0
        self._last_update = asyncio.get_event_loop().time()
        self._lock = asyncio.Lock()
    
    async def acquire(self, tokens: float = 1.0) -> bool:
        """获取发送许可
        
        Args:
            tokens: 需要消耗的令牌数
        
        Returns:
            bool: 是否获得许可
        """
        async with self._lock:
            now = asyncio.get_event_loop().time()
            elapsed = now - self._last_update
            self._last_update = now
            
            # 补充令牌
            self._second_bucket = min(
                self.max_orders_per_second,
                self._second_bucket + elapsed * self.max_orders_per_second
            )
            self._minute_bucket = min(
                self.max_orders_per_minute,
                self._minute_bucket + elapsed * (self.max_orders_per_minute / 60)
            )
            
            # 检查是否有足够令牌
            if self._second_bucket >= tokens and self._minute_bucket >= tokens:
                self._second_bucket -= tokens
                self._minute_bucket -= tokens
                return True
            
            return False
    
    async def wait_and_acquire(self, tokens: float = 1.0, timeout: float = 10.0) -> bool:
        """等待并获取发送许可"""
        start_time = asyncio.get_event_loop().time()
        
        while asyncio.get_event_loop().time() - start_time < timeout:
            if await self.acquire(tokens):
                return True
            await asyncio.sleep(0.01)
        
        return False
