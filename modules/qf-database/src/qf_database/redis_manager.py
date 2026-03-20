"""Redis缓存管理器 - 实时数据缓存

性能优化特性:
- 优化的连接池配置
- Pipeline批量操作支持
- 连接池健康检查
- 操作统计和监控
"""
import json
import pickle
import time
import logging
from typing import Optional, Any, List, Dict, Union, Tuple
from datetime import datetime, timezone
from decimal import Decimal

import redis
from redis.client import Redis
from redis.connection import ConnectionPool
from redis.exceptions import RedisError, ConnectionError as RedisConnectionError, TimeoutError

from .models import Tick, Kline

logger = logging.getLogger(__name__)


class RedisManager:
    """Redis缓存管理器 - 优化版
    
    连接池优化配置:
    - max_connections: 最大连接数，默认100
    - socket_timeout: 套接字超时，默认5.0秒
    - socket_connect_timeout: 连接超时，默认5.0秒
    - socket_keepalive: 保持连接活跃
    - health_check_interval: 健康检查间隔，默认30秒
    
    性能特性:
    - 连接池复用
    - Pipeline批量操作
    - 自动重连机制
    - 操作统计
    """
    
    # 默认连接池配置
    DEFAULT_MAX_CONNECTIONS = 100
    DEFAULT_SOCKET_TIMEOUT = 5.0
    DEFAULT_SOCKET_CONNECT_TIMEOUT = 5.0
    DEFAULT_HEALTH_CHECK_INTERVAL = 30
    
    # 键名前缀
    KEY_PREFIX_TICK = "tick:"
    KEY_PREFIX_KLINE = "kline:"
    KEY_PREFIX_TICKER = "ticker:"
    KEY_PREFIX_ORDERBOOK = "orderbook:"
    KEY_PREFIX_POSITION = "position:"
    KEY_PREFIX_RATE_LIMIT = "ratelimit:"
    
    def __init__(
        self,
        host: str = "localhost",
        port: int = 6379,
        db: int = 0,
        password: Optional[str] = None,
        # 连接池配置
        max_connections: int = None,
        socket_timeout: float = None,
        socket_connect_timeout: float = None,
        socket_keepalive: bool = True,
        health_check_interval: int = None,
        # 行为配置
        decode_responses: bool = False,
        retry_on_timeout: bool = True,
        retry_on_error: List[type] = None
    ):
        """
        初始化Redis管理器
        
        Args:
            host: 主机地址
            port: 端口
            db: 数据库编号
            password: 密码
            max_connections: 最大连接数 (默认100)
            socket_timeout: 套接字超时秒数 (默认5.0)
            socket_connect_timeout: 连接超时秒数 (默认5.0)
            socket_keepalive: 是否保持连接活跃
            health_check_interval: 健康检查间隔秒数 (默认30)
            decode_responses: 是否自动解码响应
            retry_on_timeout: 超时时是否重试
            retry_on_error: 错误类型列表，遇到时重试
        """
        self.host = host
        self.port = port
        self.db = db
        
        # 操作统计
        self._stats = {
            "total_ops": 0,
            "failed_ops": 0,
            "pipeline_ops": 0,
            "cache_hits": 0,
            "cache_misses": 0
        }
        
        # 使用默认配置
        max_connections = max_connections or self.DEFAULT_MAX_CONNECTIONS
        socket_timeout = socket_timeout or self.DEFAULT_SOCKET_TIMEOUT
        socket_connect_timeout = socket_connect_timeout or self.DEFAULT_SOCKET_CONNECT_TIMEOUT
        health_check_interval = health_check_interval or self.DEFAULT_HEALTH_CHECK_INTERVAL
        
        # 创建连接池 - 优化配置
        self.pool = ConnectionPool(
            host=host,
            port=port,
            db=db,
            password=password,
            max_connections=max_connections,
            socket_timeout=socket_timeout,
            socket_connect_timeout=socket_connect_timeout,
            socket_keepalive=socket_keepalive,
            health_check_interval=health_check_interval,
            decode_responses=decode_responses
        )
        
        # 创建客户端 - 使用连接池
        self.client: Redis = redis.Redis(
            connection_pool=self.pool,
            retry_on_timeout=retry_on_timeout,
            retry_on_error=retry_on_error or [RedisConnectionError, TimeoutError]
        )
        
        self._connected = False
        
        logger.info(f"RedisManager initialized with max_connections={max_connections}")
    
    def connect(self) -> bool:
        """
        测试Redis连接
        
        Returns:
            是否连接成功
        """
        try:
            start_time = time.time()
            self.client.ping()
            latency = time.time() - start_time
            
            self._connected = True
            logger.debug(f"Redis connection successful, latency={latency*1000:.2f}ms")
            return True
            
        except RedisConnectionError as e:
            logger.error(f"Redis connection failed (ConnectionError): {e}")
            self._connected = False
            return False
        except TimeoutError as e:
            logger.error(f"Redis connection failed (Timeout): {e}")
            self._connected = False
            return False
        except Exception as e:
            logger.error(f"Redis connection failed: {e}")
            self._connected = False
            return False
    
    def disconnect(self) -> None:
        """断开连接并释放连接池"""
        try:
            self.pool.disconnect()
            logger.info("Redis connection pool disconnected")
        except Exception as e:
            logger.warning(f"Error during disconnect: {e}")
        finally:
            self._connected = False
    
    def ping(self) -> bool:
        """测试连接是否存活"""
        try:
            return self.client.ping()
        except Exception as e:
            logger.warning(f"Redis ping failed: {e}")
            return False
    
    def health_check(self) -> Tuple[bool, float, Optional[str]]:
        """
        健康检查
        
        Returns:
            (是否健康, 延迟毫秒, 错误信息)
        """
        try:
            start_time = time.time()
            self.client.ping()
            latency = (time.time() - start_time) * 1000
            return True, latency, None
        except Exception as e:
            return False, 0.0, str(e)
    
    def get_pool_status(self) -> Dict[str, Any]:
        """
        获取连接池状态
        
        Returns:
            连接池状态字典
        """
        return {
            "max_connections": self.pool.max_connections,
            "in_use": len(self.pool._in_use_connections) if hasattr(self.pool, '_in_use_connections') else -1,
            "available": len(self.pool._available_connections) if hasattr(self.pool, '_available_connections') else -1,
        }
    
    def get_stats(self) -> Dict[str, Any]:
        """获取操作统计信息"""
        stats = self._stats.copy()
        total_cache_ops = stats["cache_hits"] + stats["cache_misses"]
        stats["cache_hit_rate"] = (
            stats["cache_hits"] / total_cache_ops * 100
            if total_cache_ops > 0 else 0
        )
        return stats
    
    def reset_stats(self) -> None:
        """重置统计信息"""
        self._stats = {
            "total_ops": 0,
            "failed_ops": 0,
            "pipeline_ops": 0,
            "cache_hits": 0,
            "cache_misses": 0
        }
    
    # ==================== 基础操作 ====================
    
    def set(
        self,
        key: str,
        value: Any,
        ttl: Optional[int] = None,
        serialize: str = "json"
    ) -> bool:
        """
        设置键值 - 优化版
        
        Args:
            key: 键名
            value: 值
            ttl: 过期时间(秒)
            serialize: 序列化方式 (json/pickle/raw)
            
        Returns:
            是否设置成功
        """
        self._stats["total_ops"] += 1
        
        try:
            if serialize == "json":
                value = json.dumps(value, default=self._json_serializer)
            elif serialize == "pickle":
                value = pickle.dumps(value)
            
            if ttl:
                self.client.setex(key, ttl, value)
            else:
                self.client.set(key, value)
            
            return True
            
        except Exception as e:
            self._stats["failed_ops"] += 1
            logger.warning(f"Redis set failed for key {key}: {e}")
            return False
    
    def get(
        self,
        key: str,
        default: Any = None,
        deserialize: str = "json"
    ) -> Any:
        """
        获取键值 - 优化版
        
        Args:
            key: 键名
            default: 默认值
            deserialize: 反序列化方式 (json/pickle/raw)
            
        Returns:
            值或默认值
        """
        self._stats["total_ops"] += 1
        
        try:
            value = self.client.get(key)
            
            if value is None:
                self._stats["cache_misses"] += 1
                return default
            
            self._stats["cache_hits"] += 1
            
            if deserialize == "json":
                return json.loads(value)
            elif deserialize == "pickle":
                return pickle.loads(value)
            else:
                return value
                
        except Exception as e:
            self._stats["failed_ops"] += 1
            logger.warning(f"Redis get failed for key {key}: {e}")
            return default
    
    def set_batch(
        self,
        items: Dict[str, Any],
        ttl: Optional[int] = None,
        serialize: str = "json"
    ) -> bool:
        """
        批量设置键值 - 使用Pipeline优化
        
        Args:
            items: 键值对字典
            ttl: 过期时间(秒)
            serialize: 序列化方式
            
        Returns:
            是否设置成功
        """
        if not items:
            return True
        
        self._stats["total_ops"] += len(items)
        self._stats["pipeline_ops"] += 1
        
        try:
            pipe = self.client.pipeline()
            
            for key, value in items.items():
                if serialize == "json":
                    value = json.dumps(value, default=self._json_serializer)
                elif serialize == "pickle":
                    value = pickle.dumps(value)
                
                if ttl:
                    pipe.setex(key, ttl, value)
                else:
                    pipe.set(key, value)
            
            pipe.execute()
            return True
            
        except Exception as e:
            self._stats["failed_ops"] += len(items)
            logger.warning(f"Redis set_batch failed: {e}")
            return False
    
    def get_batch(
        self,
        keys: List[str],
        deserialize: str = "json"
    ) -> Dict[str, Any]:
        """
        批量获取键值 - 使用Pipeline优化
        
        Args:
            keys: 键名列表
            deserialize: 反序列化方式
            
        Returns:
            键值对字典 (只返回存在的键)
        """
        if not keys:
            return {}
        
        self._stats["total_ops"] += len(keys)
        self._stats["pipeline_ops"] += 1
        
        try:
            pipe = self.client.pipeline()
            for key in keys:
                pipe.get(key)
            
            results = pipe.execute()
            
            output = {}
            for key, value in zip(keys, results):
                if value is not None:
                    self._stats["cache_hits"] += 1
                    if deserialize == "json":
                        output[key] = json.loads(value)
                    elif deserialize == "pickle":
                        output[key] = pickle.loads(value)
                    else:
                        output[key] = value
                else:
                    self._stats["cache_misses"] += 1
            
            return output
            
        except Exception as e:
            self._stats["failed_ops"] += len(keys)
            logger.warning(f"Redis get_batch failed: {e}")
            return {}
    
    def delete(self, key: str) -> bool:
        """
        删除键
        
        Args:
            key: 键名
            
        Returns:
            是否删除成功
        """
        self._stats["total_ops"] += 1
        
        try:
            self.client.delete(key)
            return True
        except Exception as e:
            self._stats["failed_ops"] += 1
            logger.warning(f"Redis delete failed for key {key}: {e}")
            return False
    
    def delete_batch(self, keys: List[str]) -> int:
        """
        批量删除键 - 使用Pipeline优化
        
        Args:
            keys: 键名列表
            
        Returns:
            成功删除的键数量
        """
        if not keys:
            return 0
        
        self._stats["total_ops"] += len(keys)
        self._stats["pipeline_ops"] += 1
        
        try:
            pipe = self.client.pipeline()
            for key in keys:
                pipe.delete(key)
            
            results = pipe.execute()
            deleted_count = sum(results)
            return deleted_count
            
        except Exception as e:
            self._stats["failed_ops"] += len(keys)
            logger.warning(f"Redis delete_batch failed: {e}")
            return 0
    
    def exists(self, key: str) -> bool:
        """
        检查键是否存在
        
        Args:
            key: 键名
            
        Returns:
            是否存在
        """
        try:
            return self.client.exists(key) > 0
        except Exception:
            return False
    
    def ttl(self, key: str) -> int:
        """
        获取键剩余生存时间
        
        Args:
            key: 键名
            
        Returns:
            剩余秒数，-1表示永不过期，-2表示不存在
        """
        try:
            return self.client.ttl(key)
        except Exception:
            return -2
    
    def expire(self, key: str, seconds: int) -> bool:
        """
        设置键过期时间
        
        Args:
            key: 键名
            seconds: 过期秒数
            
        Returns:
            是否设置成功
        """
        try:
            return self.client.expire(key, seconds)
        except Exception:
            return False
    
    # ==================== Tick缓存 ====================
    
    def cache_tick(self, tick: Tick, ttl: int = 60) -> bool:
        """
        缓存Tick数据
        
        Args:
            tick: Tick数据
            ttl: 过期时间(秒)
            
        Returns:
            是否缓存成功
        """
        try:
            key = f"{self.KEY_PREFIX_TICK}{tick.exchange}:{tick.symbol}"
            data = {
                "symbol": tick.symbol,
                "exchange": tick.exchange,
                "timestamp": tick.timestamp.isoformat(),
                "price": str(tick.price),
                "quantity": str(tick.quantity),
                "side": tick.side,
                "trade_id": tick.trade_id
            }
            return self.set(key, data, ttl=ttl)
        except Exception as e:
            print(f"缓存Tick失败: {e}")
            return False
    
    def get_cached_tick(self, symbol: str, exchange: str) -> Optional[Tick]:
        """
        获取缓存的Tick数据
        
        Args:
            symbol: 交易对
            exchange: 交易所
            
        Returns:
            Tick数据或None
        """
        try:
            key = f"{self.KEY_PREFIX_TICK}{exchange}:{symbol}"
            data = self.get(key)
            
            if not data:
                return None
            
            return Tick(
                symbol=data["symbol"],
                exchange=data["exchange"],
                timestamp=datetime.fromisoformat(data["timestamp"]),
                price=Decimal(data["price"]),
                quantity=Decimal(data["quantity"]),
                side=data["side"],
                trade_id=data["trade_id"]
            )
        except Exception as e:
            print(f"获取缓存Tick失败: {e}")
            return None
    
    def cache_ticks_batch(self, ticks: List[Tick], ttl: int = 60) -> bool:
        """
        批量缓存Tick数据
        
        Args:
            ticks: Tick数据列表
            ttl: 过期时间(秒)
            
        Returns:
            是否缓存成功
        """
        try:
            pipe = self.client.pipeline()
            
            for tick in ticks:
                key = f"{self.KEY_PREFIX_TICK}{tick.exchange}:{tick.symbol}"
                data = {
                    "symbol": tick.symbol,
                    "exchange": tick.exchange,
                    "timestamp": tick.timestamp.isoformat(),
                    "price": str(tick.price),
                    "quantity": str(tick.quantity),
                    "side": tick.side,
                    "trade_id": tick.trade_id
                }
                pipe.setex(key, ttl, json.dumps(data))
            
            pipe.execute()
            return True
        except Exception as e:
            print(f"批量缓存Tick失败: {e}")
            return False
    
    # ==================== K线缓存 ====================
    
    def cache_kline(self, kline: Kline, ttl: int = 300) -> bool:
        """
        缓存K线数据
        
        Args:
            kline: K线数据
            ttl: 过期时间(秒)
            
        Returns:
            是否缓存成功
        """
        try:
            key = f"{self.KEY_PREFIX_KLINE}{kline.exchange}:{kline.symbol}:{kline.interval}"
            data = {
                "symbol": kline.symbol,
                "exchange": kline.exchange,
                "interval": kline.interval,
                "timestamp": kline.timestamp.isoformat(),
                "open": str(kline.open),
                "high": str(kline.high),
                "low": str(kline.low),
                "close": str(kline.close),
                "volume": str(kline.volume),
                "quote_volume": str(kline.quote_volume),
                "trades": kline.trades
            }
            return self.set(key, data, ttl=ttl)
        except Exception as e:
            print(f"缓存K线失败: {e}")
            return False
    
    def get_cached_kline(
        self,
        symbol: str,
        exchange: str,
        interval: str
    ) -> Optional[Kline]:
        """
        获取缓存的K线数据
        
        Args:
            symbol: 交易对
            exchange: 交易所
            interval: 时间间隔
            
        Returns:
            K线数据或None
        """
        try:
            key = f"{self.KEY_PREFIX_KLINE}{exchange}:{symbol}:{interval}"
            data = self.get(key)
            
            if not data:
                return None
            
            return Kline(
                symbol=data["symbol"],
                exchange=data["exchange"],
                interval=data["interval"],
                timestamp=datetime.fromisoformat(data["timestamp"]),
                open=Decimal(data["open"]),
                high=Decimal(data["high"]),
                low=Decimal(data["low"]),
                close=Decimal(data["close"]),
                volume=Decimal(data["volume"]),
                quote_volume=Decimal(data["quote_volume"]),
                trades=data["trades"]
            )
        except Exception as e:
            print(f"获取缓存K线失败: {e}")
            return None
    
    # ==================== Ticker缓存 ====================
    
    def cache_ticker(
        self,
        symbol: str,
        exchange: str,
        ticker_data: Dict[str, Any],
        ttl: int = 10
    ) -> bool:
        """
        缓存Ticker数据
        
        Args:
            symbol: 交易对
            exchange: 交易所
            ticker_data: Ticker数据字典
            ttl: 过期时间(秒)
            
        Returns:
            是否缓存成功
        """
        try:
            key = f"{self.KEY_PREFIX_TICKER}{exchange}:{symbol}"
            ticker_data["_cached_at"] = datetime.utcnow().isoformat()
            return self.set(key, ticker_data, ttl=ttl)
        except Exception as e:
            print(f"缓存Ticker失败: {e}")
            return False
    
    def get_cached_ticker(self, symbol: str, exchange: str) -> Optional[Dict[str, Any]]:
        """
        获取缓存的Ticker数据
        
        Args:
            symbol: 交易对
            exchange: 交易所
            
        Returns:
            Ticker数据或None
        """
        try:
            key = f"{self.KEY_PREFIX_TICKER}{exchange}:{symbol}"
            return self.get(key)
        except Exception as e:
            print(f"获取缓存Ticker失败: {e}")
            return None
    
    # ==================== OrderBook缓存 ====================
    
    def cache_orderbook(
        self,
        symbol: str,
        exchange: str,
        orderbook_data: Dict[str, Any],
        ttl: int = 5
    ) -> bool:
        """
        缓存OrderBook数据
        
        Args:
            symbol: 交易对
            exchange: 交易所
            orderbook_data: OrderBook数据字典
            ttl: 过期时间(秒)
            
        Returns:
            是否缓存成功
        """
        try:
            key = f"{self.KEY_PREFIX_ORDERBOOK}{exchange}:{symbol}"
            orderbook_data["_cached_at"] = datetime.utcnow().isoformat()
            return self.set(key, orderbook_data, ttl=ttl)
        except Exception as e:
            print(f"缓存OrderBook失败: {e}")
            return False
    
    def get_cached_orderbook(self, symbol: str, exchange: str) -> Optional[Dict[str, Any]]:
        """
        获取缓存的OrderBook数据
        
        Args:
            symbol: 交易对
            exchange: 交易所
            
        Returns:
            OrderBook数据或None
        """
        try:
            key = f"{self.KEY_PREFIX_ORDERBOOK}{exchange}:{symbol}"
            return self.get(key)
        except Exception as e:
            print(f"获取缓存OrderBook失败: {e}")
            return None
    
    # ==================== 持仓缓存 ====================
    
    def cache_position(
        self,
        account_id: str,
        symbol: str,
        position_data: Dict[str, Any],
        ttl: int = 60
    ) -> bool:
        """
        缓存持仓数据
        
        Args:
            account_id: 账户ID
            symbol: 交易对
            position_data: 持仓数据字典
            ttl: 过期时间(秒)
            
        Returns:
            是否缓存成功
        """
        try:
            key = f"{self.KEY_PREFIX_POSITION}{account_id}:{symbol}"
            position_data["_cached_at"] = datetime.utcnow().isoformat()
            return self.set(key, position_data, ttl=ttl)
        except Exception as e:
            print(f"缓存持仓失败: {e}")
            return False
    
    def get_cached_position(self, account_id: str, symbol: str) -> Optional[Dict[str, Any]]:
        """
        获取缓存的持仓数据
        
        Args:
            account_id: 账户ID
            symbol: 交易对
            
        Returns:
            持仓数据或None
        """
        try:
            key = f"{self.KEY_PREFIX_POSITION}{account_id}:{symbol}"
            return self.get(key)
        except Exception as e:
            print(f"获取缓存持仓失败: {e}")
            return None
    
    def delete_position(self, account_id: str, symbol: str) -> bool:
        """
        删除持仓缓存
        
        Args:
            account_id: 账户ID
            symbol: 交易对
            
        Returns:
            是否删除成功
        """
        try:
            key = f"{self.KEY_PREFIX_POSITION}{account_id}:{symbol}"
            return self.delete(key)
        except Exception as e:
            print(f"删除持仓缓存失败: {e}")
            return False
    
    # ==================== 限流控制 ====================
    
    def rate_limit_check(
        self,
        key: str,
        max_requests: int,
        window_seconds: int
    ) -> tuple[bool, int, int]:
        """
        检查限流
        
        Args:
            key: 限流键
            max_requests: 最大请求数
            window_seconds: 时间窗口(秒)
            
        Returns:
            (是否允许, 当前请求数, 剩余秒数)
        """
        try:
            full_key = f"{self.KEY_PREFIX_RATE_LIMIT}{key}"
            current = self.client.get(full_key)
            
            if current is None:
                # 首次请求
                pipe = self.client.pipeline()
                pipe.setex(full_key, window_seconds, 1)
                pipe.execute()
                return True, 1, window_seconds
            
            current_count = int(current)
            
            if current_count >= max_requests:
                # 超过限流
                ttl = self.client.ttl(full_key)
                return False, current_count, ttl if ttl > 0 else window_seconds
            
            # 增加计数
            self.client.incr(full_key)
            return True, current_count + 1, self.client.ttl(full_key)
        except Exception as e:
            print(f"限流检查失败: {e}")
            # 出错时允许请求通过
            return True, 0, 0
    
    def reset_rate_limit(self, key: str) -> bool:
        """
        重置限流计数
        
        Args:
            key: 限流键
            
        Returns:
            是否重置成功
        """
        try:
            full_key = f"{self.KEY_PREFIX_RATE_LIMIT}{key}"
            return self.delete(full_key)
        except Exception as e:
            print(f"重置限流失败: {e}")
            return False
    
    # ==================== 发布订阅 ====================
    
    def publish(self, channel: str, message: Any) -> int:
        """
        发布消息
        
        Args:
            channel: 频道名
            message: 消息内容
            
        Returns:
            接收消息的客户端数
        """
        try:
            if isinstance(message, (dict, list)):
                message = json.dumps(message, default=self._json_serializer)
            return self.client.publish(channel, message)
        except Exception as e:
            print(f"发布消息失败: {e}")
            return 0
    
    def subscribe(self, *channels: str):
        """
        订阅频道
        
        Args:
            *channels: 频道名列表
            
        Returns:
            PubSub对象
        """
        try:
            pubsub = self.client.pubsub()
            pubsub.subscribe(*channels)
            return pubsub
        except Exception as e:
            print(f"订阅频道失败: {e}")
            return None
    
    # ==================== 分布式锁 ====================
    
    def acquire_lock(
        self,
        lock_name: str,
        ttl: int = 30,
        blocking: bool = False,
        blocking_timeout: int = 0
    ) -> bool:
        """
        获取分布式锁
        
        Args:
            lock_name: 锁名称
            ttl: 锁超时时间(秒)
            blocking: 是否阻塞等待
            blocking_timeout: 阻塞超时时间(秒)
            
        Returns:
            是否获取成功
        """
        try:
            lock_key = f"lock:{lock_name}"
            
            if not blocking:
                # 非阻塞模式
                return self.client.set(lock_key, "1", nx=True, ex=ttl) is not None
            
            # 阻塞模式
            import time
            start_time = time.time()
            while True:
                if self.client.set(lock_key, "1", nx=True, ex=ttl):
                    return True
                
                if blocking_timeout and (time.time() - start_time) >= blocking_timeout:
                    return False
                
                time.sleep(0.1)
        except Exception as e:
            print(f"获取锁失败: {e}")
            return False
    
    def release_lock(self, lock_name: str) -> bool:
        """
        释放分布式锁
        
        Args:
            lock_name: 锁名称
            
        Returns:
            是否释放成功
        """
        try:
            lock_key = f"lock:{lock_name}"
            return self.client.delete(lock_key) > 0
        except Exception as e:
            print(f"释放锁失败: {e}")
            return False
    
    # ==================== 工具方法 ====================
    
    def _json_serializer(self, obj):
        """JSON序列化辅助函数"""
        if isinstance(obj, Decimal):
            return str(obj)
        if isinstance(obj, datetime):
            return obj.isoformat()
        raise TypeError(f"Object of type {type(obj)} is not JSON serializable")
    
    def keys(self, pattern: str = "*") -> List[str]:
        """
        获取匹配模式的键列表
        
        Args:
            pattern: 匹配模式
            
        Returns:
            键列表
        """
        try:
            return [k.decode() if isinstance(k, bytes) else k 
                    for k in self.client.keys(pattern)]
        except Exception as e:
            print(f"获取键列表失败: {e}")
            return []
    
    def flush_db(self) -> bool:
        """
        清空当前数据库
        
        Returns:
            是否清空成功
        """
        try:
            self.client.flushdb()
            return True
        except Exception as e:
            print(f"清空数据库失败: {e}")
            return False
    
    def info(self) -> Dict[str, Any]:
        """
        获取Redis服务器信息
        
        Returns:
            服务器信息字典
        """
        try:
            info = self.client.info()
            return {k.decode() if isinstance(k, bytes) else k: 
                    v.decode() if isinstance(v, bytes) else v 
                    for k, v in info.items()}
        except Exception as e:
            print(f"获取服务器信息失败: {e}")
            return {}
    
    @property
    def is_connected(self) -> bool:
        """是否已连接"""
        return self._connected