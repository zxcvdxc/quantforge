"""Redis缓存管理器 - 实时数据缓存"""
import json
import pickle
from typing import Optional, Any, List, Dict, Union
from datetime import datetime, timedelta
from decimal import Decimal

import redis
from redis.client import Redis

from .models import Tick, Kline


class RedisManager:
    """Redis缓存管理器"""
    
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
        socket_timeout: float = 5.0,
        socket_connect_timeout: float = 5.0,
        max_connections: int = 50,
        decode_responses: bool = False
    ):
        """
        初始化Redis管理器
        
        Args:
            host: 主机地址
            port: 端口
            db: 数据库编号
            password: 密码
            socket_timeout: 套接字超时
            socket_connect_timeout: 连接超时
            max_connections: 最大连接数
            decode_responses: 是否自动解码响应
        """
        self.host = host
        self.port = port
        self.db = db
        
        # 创建连接池
        self.pool = redis.ConnectionPool(
            host=host,
            port=port,
            db=db,
            password=password,
            socket_timeout=socket_timeout,
            socket_connect_timeout=socket_connect_timeout,
            max_connections=max_connections,
            decode_responses=decode_responses
        )
        
        # 创建客户端
        self.client: Redis = redis.Redis(connection_pool=self.pool)
        
        self._connected = False
    
    def connect(self) -> bool:
        """
        测试Redis连接
        
        Returns:
            是否连接成功
        """
        try:
            self.client.ping()
            self._connected = True
            return True
        except Exception as e:
            print(f"Redis连接失败: {e}")
            self._connected = False
            return False
    
    def disconnect(self) -> None:
        """断开连接"""
        self.pool.disconnect()
        self._connected = False
    
    def ping(self) -> bool:
        """测试连接是否存活"""
        try:
            return self.client.ping()
        except:
            return False
    
    # ==================== 基础操作 ====================
    
    def set(
        self,
        key: str,
        value: Any,
        ttl: Optional[int] = None,
        serialize: str = "json"
    ) -> bool:
        """
        设置键值
        
        Args:
            key: 键名
            value: 值
            ttl: 过期时间(秒)
            serialize: 序列化方式 (json/pickle/raw)
            
        Returns:
            是否设置成功
        """
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
            print(f"Redis设置失败: {e}")
            return False
    
    def get(
        self,
        key: str,
        default: Any = None,
        deserialize: str = "json"
    ) -> Any:
        """
        获取键值
        
        Args:
            key: 键名
            default: 默认值
            deserialize: 反序列化方式 (json/pickle/raw)
            
        Returns:
            值或默认值
        """
        try:
            value = self.client.get(key)
            
            if value is None:
                return default
            
            if deserialize == "json":
                return json.loads(value)
            elif deserialize == "pickle":
                return pickle.loads(value)
            else:
                return value
        except Exception as e:
            print(f"Redis获取失败: {e}")
            return default
    
    def delete(self, key: str) -> bool:
        """
        删除键
        
        Args:
            key: 键名
            
        Returns:
            是否删除成功
        """
        try:
            self.client.delete(key)
            return True
        except Exception as e:
            print(f"Redis删除失败: {e}")
            return False
    
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