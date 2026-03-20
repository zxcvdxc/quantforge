"""WebSocket 连接池 - 高性能连接管理

提供 WebSocket 连接池，支持连接复用、自动重连、心跳检测等功能。
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Coroutine, Dict, List, Optional, Set, TypeVar, Generic
from enum import Enum, auto
import weakref

logger = logging.getLogger(__name__)

T = TypeVar('T')


class ConnectionState(Enum):
    """连接状态"""
    DISCONNECTED = auto()
    CONNECTING = auto()
    CONNECTED = auto()
    RECONNECTING = auto()
    CLOSED = auto()


@dataclass
class ConnectionConfig:
    """连接配置"""
    # 连接参数
    max_connections: int = 10
    min_connections: int = 1
    
    # 超时设置
    connect_timeout: float = 10.0
    send_timeout: float = 5.0
    receive_timeout: float = 30.0
    
    # 心跳设置
    heartbeat_interval: float = 30.0
    heartbeat_timeout: float = 10.0
    
    # 重连设置
    enable_reconnect: bool = True
    max_reconnect_attempts: int = 5
    reconnect_delay: float = 1.0
    max_reconnect_delay: float = 60.0
    reconnect_backoff: float = 2.0
    
    # 连接存活时间
    max_idle_time: float = 300.0
    max_lifetime: float = 3600.0


@dataclass
class ConnectionStats:
    """连接统计信息"""
    created_at: float = field(default_factory=time.time)
    last_used: float = field(default_factory=time.time)
    messages_sent: int = 0
    messages_received: int = 0
    bytes_sent: int = 0
    bytes_received: int = 0
    reconnect_count: int = 0
    error_count: int = 0


class PooledConnection:
    """连接池中的连接封装"""
    
    def __init__(
        self,
        connection_id: str,
        config: ConnectionConfig,
    ) -> None:
        self.connection_id = connection_id
        self.config = config
        self.state = ConnectionState.DISCONNECTED
        self.stats = ConnectionStats()
        self._connection: Any = None
        self._lock = asyncio.Lock()
        self._last_heartbeat: float = 0.0
        self._in_use: bool = False
        self._message_handlers: List[Callable[[Any], None]] = []
        self._error_handlers: List[Callable[[Exception], None]] = []
        self._close_handlers: List[Callable[[], None]] = []
        
    @property
    def is_available(self) -> bool:
        """连接是否可用"""
        return self.state == ConnectionState.CONNECTED and not self._in_use
    
    @property
    def is_healthy(self) -> bool:
        """连接是否健康"""
        if self.state != ConnectionState.CONNECTED:
            return False
        
        # 检查心跳超时
        if self.config.heartbeat_interval > 0:
            time_since_heartbeat = time.time() - self._last_heartbeat
            if time_since_heartbeat > self.config.heartbeat_interval + self.config.heartbeat_timeout:
                return False
        
        # 检查空闲超时
        idle_time = time.time() - self.stats.last_used
        if idle_time > self.config.max_idle_time:
            return False
        
        return True
    
    @property
    def age(self) -> float:
        """连接年龄（秒）"""
        return time.time() - self.stats.created_at
    
    @property
    def in_use(self) -> bool:
        """是否正在使用中"""
        return self._in_use
    
    def acquire(self) -> bool:
        """获取连接使用权"""
        if self._in_use or not self.is_available:
            return False
        self._in_use = True
        self.stats.last_used = time.time()
        return True
    
    def release(self) -> None:
        """释放连接"""
        self._in_use = False
        self.stats.last_used = time.time()
    
    async def connect(self, connector: Callable[[], Coroutine[Any, Any, Any]]) -> bool:
        """建立连接"""
        async with self._lock:
            if self.state in (ConnectionState.CONNECTED, ConnectionState.CONNECTING):
                return True
            
            self.state = ConnectionState.CONNECTING
            try:
                self._connection = await asyncio.wait_for(
                    connector(),
                    timeout=self.config.connect_timeout
                )
                self.state = ConnectionState.CONNECTED
                self._last_heartbeat = time.time()
                logger.debug(f"Connection {self.connection_id} connected")
                return True
            except Exception as e:
                self.state = ConnectionState.DISCONNECTED
                self.stats.error_count += 1
                logger.error(f"Connection {self.connection_id} failed: {e}")
                return False
    
    async def disconnect(self) -> None:
        """断开连接"""
        async with self._lock:
            if self._connection and hasattr(self._connection, 'close'):
                try:
                    await self._connection.close()
                except Exception as e:
                    logger.warning(f"Error closing connection {self.connection_id}: {e}")
            self._connection = None
            self.state = ConnectionState.CLOSED
            self._in_use = False
            
            for handler in self._close_handlers:
                try:
                    handler()
                except Exception as e:
                    logger.error(f"Close handler error: {e}")
    
    async def send(self, message: Any) -> bool:
        """发送消息"""
        if not self._connection or self.state != ConnectionState.CONNECTED:
            return False
        
        try:
            if hasattr(self._connection, 'send'):
                await asyncio.wait_for(
                    self._connection.send(message),
                    timeout=self.config.send_timeout
                )
            elif hasattr(self._connection, 'send_str'):
                await asyncio.wait_for(
                    self._connection.send_str(message),
                    timeout=self.config.send_timeout
                )
            elif hasattr(self._connection, 'send_bytes'):
                await asyncio.wait_for(
                    self._connection.send_bytes(message),
                    timeout=self.config.send_timeout
                )
            else:
                return False
            
            self.stats.messages_sent += 1
            self.stats.bytes_sent += len(str(message))
            return True
        except Exception as e:
            self.stats.error_count += 1
            logger.error(f"Send error on {self.connection_id}: {e}")
            return False
    
    async def receive(self) -> Optional[Any]:
        """接收消息"""
        if not self._connection or self.state != ConnectionState.CONNECTED:
            return None
        
        try:
            message = await asyncio.wait_for(
                self._connection.receive(),
                timeout=self.config.receive_timeout
            )
            self.stats.messages_received += 1
            self.stats.bytes_received += len(str(message))
            self._last_heartbeat = time.time()
            return message
        except asyncio.TimeoutError:
            return None
        except Exception as e:
            self.stats.error_count += 1
            logger.error(f"Receive error on {self.connection_id}: {e}")
            return None
    
    def on_message(self, handler: Callable[[Any], None]) -> None:
        """注册消息处理器"""
        self._message_handlers.append(handler)
    
    def on_error(self, handler: Callable[[Exception], None]) -> None:
        """注册错误处理器"""
        self._error_handlers.append(handler)
    
    def on_close(self, handler: Callable[[], None]) -> None:
        """注册关闭处理器"""
        self._close_handlers.append(handler)
    
    def notify_message(self, message: Any) -> None:
        """通知消息"""
        for handler in self._message_handlers:
            try:
                handler(message)
            except Exception as e:
                logger.error(f"Message handler error: {e}")
    
    def notify_error(self, error: Exception) -> None:
        """通知错误"""
        for handler in self._error_handlers:
            try:
                handler(error)
            except Exception as e:
                logger.error(f"Error handler error: {e}")


class ConnectionPool:
    """WebSocket 连接池
    
    功能：
    - 连接复用和池化管理
    - 自动重连机制
    - 心跳检测
    - 连接健康检查
    - 连接数动态调整
    
    Example:
        pool = ConnectionPool(ConnectionConfig(max_connections=5))
        
        # 获取连接
        conn = await pool.acquire()
        try:
            await conn.send("message")
            response = await conn.receive()
        finally:
            await pool.release(conn)
    """
    
    def __init__(self, config: Optional[ConnectionConfig] = None) -> None:
        self.config = config or ConnectionConfig()
        self._connections: Dict[str, PooledConnection] = {}
        self._connector: Optional[Callable[[], Coroutine[Any, Any, Any]]] = None
        self._running = False
        self._maintenance_task: Optional[asyncio.Task] = None
        self._semaphore = asyncio.Semaphore(self.config.max_connections)
        self._lock = asyncio.Lock()
        self._connection_counter = 0
        self._global_stats = {
            "total_acquired": 0,
            "total_released": 0,
            "total_reconnects": 0,
        }
    
    def set_connector(self, connector: Callable[[], Coroutine[Any, Any, Any]]) -> None:
        """设置连接创建器"""
        self._connector = connector
    
    async def start(self) -> None:
        """启动连接池"""
        if self._running:
            return
        
        self._running = True
        
        # 创建最小连接数
        for _ in range(self.config.min_connections):
            await self._create_connection()
        
        # 启动维护任务
        self._maintenance_task = asyncio.create_task(self._maintenance_loop())
        logger.info(f"Connection pool started with {len(self._connections)} connections")
    
    async def stop(self) -> None:
        """停止连接池"""
        if not self._running:
            return
        
        self._running = False
        
        # 取消维护任务
        if self._maintenance_task:
            self._maintenance_task.cancel()
            try:
                await self._maintenance_task
            except asyncio.CancelledError:
                pass
        
        # 关闭所有连接
        async with self._lock:
            for conn in list(self._connections.values()):
                await conn.disconnect()
            self._connections.clear()
        
        logger.info("Connection pool stopped")
    
    async def acquire(self, timeout: Optional[float] = None) -> Optional[PooledConnection]:
        """获取连接
        
        Args:
            timeout: 等待超时时间（秒）
        
        Returns:
            PooledConnection: 可用连接，超时返回 None
        """
        timeout = timeout or self.config.connect_timeout
        deadline = time.time() + timeout
        
        while time.time() < deadline:
            # 尝试获取现有可用连接
            async with self._lock:
                for conn in self._connections.values():
                    if conn.acquire():
                        self._global_stats["total_acquired"] += 1
                        return conn
            
            # 如果没有可用连接，尝试创建新连接
            if len(self._connections) < self.config.max_connections:
                new_conn = await self._create_connection()
                if new_conn and new_conn.acquire():
                    self._global_stats["total_acquired"] += 1
                    return new_conn
            
            # 等待一小段时间后重试
            await asyncio.sleep(0.1)
        
        logger.warning(f"Acquire connection timeout after {timeout}s")
        return None
    
    async def release(self, connection: PooledConnection) -> None:
        """释放连接"""
        if connection:
            connection.release()
            self._global_stats["total_released"] += 1
    
    async def _create_connection(self) -> Optional[PooledConnection]:
        """创建新连接"""
        if not self._connector:
            logger.error("No connector set")
            return None
        
        async with self._lock:
            if len(self._connections) >= self.config.max_connections:
                return None
            
            self._connection_counter += 1
            conn_id = f"conn_{self._connection_counter}"
            conn = PooledConnection(conn_id, self.config)
            
            if await conn.connect(self._connector):
                self._connections[conn_id] = conn
                return conn
            else:
                return None
    
    async def _maintenance_loop(self) -> None:
        """维护循环"""
        while self._running:
            try:
                await self._maintain_connections()
                await asyncio.sleep(5.0)  # 每5秒检查一次
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Maintenance loop error: {e}")
                await asyncio.sleep(1.0)
    
    async def _maintain_connections(self) -> None:
        """维护连接"""
        async with self._lock:
            to_remove = []
            to_reconnect = []
            
            for conn_id, conn in self._connections.items():
                # 检查连接是否过期
                if conn.age > self.config.max_lifetime:
                    to_remove.append(conn_id)
                    continue
                
                # 检查连接健康状态
                if not conn.is_healthy:
                    if conn.state == ConnectionState.CLOSED:
                        to_remove.append(conn_id)
                    elif self.config.enable_reconnect and conn.stats.reconnect_count < self.config.max_reconnect_attempts:
                        to_reconnect.append(conn_id)
            
            # 移除过期连接
            for conn_id in to_remove:
                conn = self._connections.pop(conn_id)
                await conn.disconnect()
                logger.debug(f"Removed expired connection {conn_id}")
            
            # 重连不健康的连接
            for conn_id in to_reconnect:
                conn = self._connections.get(conn_id)
                if conn and not conn.in_use:
                    conn.stats.reconnect_count += 1
                    self._global_stats["total_reconnects"] += 1
                    await conn.disconnect()
                    if await conn.connect(self._connector):
                        logger.debug(f"Reconnected {conn_id}")
                    else:
                        logger.warning(f"Failed to reconnect {conn_id}")
            
            # 确保最小连接数
            while len(self._connections) < self.config.min_connections:
                new_conn = await self._create_connection()
                if not new_conn:
                    break
    
    def get_stats(self) -> Dict[str, Any]:
        """获取连接池统计信息"""
        available = sum(1 for c in self._connections.values() if c.is_available)
        in_use = sum(1 for c in self._connections.values() if c.in_use)
        
        return {
            "total_connections": len(self._connections),
            "available": available,
            "in_use": in_use,
            **self._global_stats,
        }
    
    async def broadcast(self, message: Any) -> Dict[str, bool]:
        """广播消息到所有可用连接"""
        results = {}
        async with self._lock:
            for conn_id, conn in self._connections.items():
                if conn.state == ConnectionState.CONNECTED:
                    results[conn_id] = await conn.send(message)
        return results


class AsyncTaskPool:
    """异步任务池 - 用于管理并发任务"""
    
    def __init__(self, max_workers: int = 10) -> None:
        self.max_workers = max_workers
        self._semaphore = asyncio.Semaphore(max_workers)
        self._tasks: Set[asyncio.Task] = set()
        self._lock = asyncio.Lock()
    
    async def submit(self, coro: Coroutine[Any, Any, T]) -> T:
        """提交异步任务"""
        async with self._semaphore:
            task = asyncio.create_task(coro)
            async with self._lock:
                self._tasks.add(task)
            
            try:
                result = await task
                return result
            finally:
                async with self._lock:
                    self._tasks.discard(task)
    
    async def submit_many(self, coros: List[Coroutine[Any, Any, T]]) -> List[T]:
        """批量提交异步任务"""
        return await asyncio.gather(*[self.submit(c) for c in coros])
    
    async def cancel_all(self) -> None:
        """取消所有任务"""
        async with self._lock:
            for task in list(self._tasks):
                task.cancel()
            self._tasks.clear()
    
    def get_stats(self) -> Dict[str, int]:
        """获取任务池统计"""
        return {
            "max_workers": self.max_workers,
            "active_tasks": len(self._tasks),
            "available_slots": self.max_workers - len(self._tasks),
        }
