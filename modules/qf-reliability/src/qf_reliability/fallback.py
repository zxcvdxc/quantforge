"""优雅降级 (Graceful Degradation)

当依赖服务不可用时，切换到备用方案，保证核心功能可用
"""
import time
import logging
import pickle
import json
import hashlib
from enum import Enum, auto
from typing import Callable, Optional, Type, Dict, Any, List, Union, Tuple
from functools import wraps
from dataclasses import dataclass, asdict
from pathlib import Path

logger = logging.getLogger(__name__)


class DegradationStrategy(Enum):
    """降级策略"""
    CACHE = auto()           # 使用缓存数据
    STATIC = auto()          # 使用静态/默认值
    ALTERNATIVE = auto()     # 使用备用服务
    PARTIAL = auto()         # 返回部分数据
    DISABLE = auto()         # 禁用功能


@dataclass
class FallbackConfig:
    """降级配置"""
    strategy: DegradationStrategy = DegradationStrategy.CACHE
    cache_ttl: float = 300.0           # 缓存有效期（秒）
    static_value: Any = None           # 静态默认值
    alternative_func: Optional[Callable] = None  # 备用函数
    partial_data_provider: Optional[Callable] = None  # 部分数据提供者
    degradation_notice: bool = True    # 是否发送降级通知


class LocalCache:
    """本地文件缓存 - 用于数据库故障时"""
    
    def __init__(self, cache_dir: str = ".fallback_cache"):
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(exist_ok=True)
        self._memory_cache: Dict[str, Tuple[Any, float]] = {}
    
    def _get_cache_key(self, key: str) -> str:
        """生成缓存键"""
        return hashlib.md5(key.encode()).hexdigest()
    
    def _get_cache_path(self, key: str) -> Path:
        """获取缓存文件路径"""
        cache_key = self._get_cache_key(key)
        return self.cache_dir / f"{cache_key}.cache"
    
    def get(self, key: str, ttl: Optional[float] = None) -> Optional[Any]:
        """
        获取缓存值
        
        Args:
            key: 缓存键
            ttl: 有效期（秒），None表示永不过期
            
        Returns:
            缓存值或None
        """
        # 先检查内存缓存
        if key in self._memory_cache:
            value, timestamp = self._memory_cache[key]
            if ttl is None or time.time() - timestamp < ttl:
                logger.debug(f"Memory cache hit for key: {key}")
                return value
            else:
                del self._memory_cache[key]
        
        # 检查文件缓存
        cache_path = self._get_cache_path(key)
        if cache_path.exists():
            try:
                with open(cache_path, 'rb') as f:
                    data = pickle.load(f)
                    value, timestamp = data['value'], data['timestamp']
                    
                    if ttl is None or time.time() - timestamp < ttl:
                        logger.debug(f"File cache hit for key: {key}")
                        # 恢复到内存缓存
                        self._memory_cache[key] = (value, timestamp)
                        return value
                    else:
                        cache_path.unlink()
                        
            except Exception as e:
                logger.warning(f"Failed to read cache file: {e}")
        
        return None
    
    def set(self, key: str, value: Any):
        """
        设置缓存值
        
        Args:
            key: 缓存键
            value: 缓存值
        """
        timestamp = time.time()
        
        # 保存到内存
        self._memory_cache[key] = (value, timestamp)
        
        # 保存到文件
        cache_path = self._get_cache_path(key)
        try:
            with open(cache_path, 'wb') as f:
                pickle.dump({'value': value, 'timestamp': timestamp}, f)
        except Exception as e:
            logger.warning(f"Failed to write cache file: {e}")
    
    def delete(self, key: str):
        """删除缓存"""
        if key in self._memory_cache:
            del self._memory_cache[key]
        
        cache_path = self._get_cache_path(key)
        if cache_path.exists():
            cache_path.unlink()
    
    def clear(self):
        """清除所有缓存"""
        self._memory_cache.clear()
        for cache_file in self.cache_dir.glob("*.cache"):
            cache_file.unlink()
    
    def cleanup_expired(self, ttl: float):
        """清理过期缓存"""
        current_time = time.time()
        
        # 清理内存缓存
        expired_keys = [
            k for k, (_, ts) in self._memory_cache.items()
            if current_time - ts >= ttl
        ]
        for key in expired_keys:
            del self._memory_cache[key]
        
        # 清理文件缓存
        for cache_file in self.cache_dir.glob("*.cache"):
            try:
                with open(cache_file, 'rb') as f:
                    data = pickle.load(f)
                    if current_time - data['timestamp'] >= ttl:
                        cache_file.unlink()
            except Exception:
                pass


class FallbackManager:
    """降级管理器
    
    管理多种降级策略:
    - 缓存降级: 使用本地/远程缓存
    - 静态降级: 返回默认值
    - 备用服务: 切换到备用API/服务
    - 部分数据: 返回简化版数据
    
    使用示例:
        fallback_mgr = FallbackManager()
        
        # 注册降级策略
        fallback_mgr.register_strategy("market_data", DegradationStrategy.CACHE)
        
        # 执行带降级的操作
        result = fallback_mgr.execute(
            "market_data",
            fetch_market_data,
            symbol="BTC"
        )
    """
    
    _instance = None
    
    def __new__(cls, *args, **kwargs):
        """单例模式"""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self, cache_dir: str = ".fallback_cache"):
        if hasattr(self, '_initialized'):
            return
        self._initialized = True
        
        self._cache = LocalCache(cache_dir)
        self._strategies: Dict[str, DegradationStrategy] = {}
        self._configs: Dict[str, FallbackConfig] = {}
        self._degradation_notices: Dict[str, bool] = {}
        
        # 统计
        self._stats = {
            "total_calls": 0,
            "primary_success": 0,
            "fallback_success": 0,
            "total_failures": 0,
            "degradation_events": 0
        }
    
    @property
    def stats(self) -> Dict[str, Any]:
        """获取统计信息"""
        return self._stats.copy()
    
    def register_strategy(
        self,
        name: str,
        strategy: DegradationStrategy,
        config: Optional[FallbackConfig] = None
    ):
        """
        注册降级策略
        
        Args:
            name: 策略名称
            strategy: 降级策略
            config: 配置选项
        """
        self._strategies[name] = strategy
        self._configs[name] = config or FallbackConfig(strategy=strategy)
        logger.info(f"Registered fallback strategy '{name}': {strategy.name}")
    
    def execute(
        self,
        name: str,
        primary_func: Callable,
        *args,
        fallback_value: Any = None,
        cache_key: Optional[str] = None,
        **kwargs
    ) -> Any:
        """
        执行带降级保护的操作
        
        Args:
            name: 策略名称
            primary_func: 主函数
            *args: 主函数参数
            fallback_value: 默认降级值
            cache_key: 缓存键
            **kwargs: 主函数关键字参数
            
        Returns:
            执行结果或降级值
        """
        self._stats["total_calls"] += 1
        
        config = self._configs.get(name, FallbackConfig())
        cache_key = cache_key or f"{name}:{str(args)}:{str(kwargs)}"
        
        try:
            # 尝试执行主函数
            result = primary_func(*args, **kwargs)
            self._stats["primary_success"] += 1
            
            # 缓存结果用于后续降级
            if config.strategy in (DegradationStrategy.CACHE,):
                self._cache.set(cache_key, result)
            
            return result
            
        except Exception as e:
            logger.warning(f"Primary function failed for '{name}': {e}")
            
            # 执行降级
            self._stats["degradation_events"] += 1
            return self._execute_fallback(name, cache_key, config, fallback_value, e)
    
    def _execute_fallback(
        self,
        name: str,
        cache_key: str,
        config: FallbackConfig,
        fallback_value: Any,
        original_error: Exception
    ) -> Any:
        """执行降级逻辑"""
        
        if config.strategy == DegradationStrategy.CACHE:
            # 尝试使用缓存
            cached = self._cache.get(cache_key, config.cache_ttl)
            if cached is not None:
                logger.info(f"Using cached data for '{name}'")
                self._stats["fallback_success"] += 1
                if config.degradation_notice:
                    self._send_degradation_notice(name, "Using cached data", original_error)
                return cached
            logger.warning(f"No cached data available for '{name}'")
            
        elif config.strategy == DegradationStrategy.STATIC:
            # 使用静态值
            value = config.static_value if config.static_value is not None else fallback_value
            if value is not None:
                logger.info(f"Using static value for '{name}'")
                self._stats["fallback_success"] += 1
                if config.degradation_notice:
                    self._send_degradation_notice(name, "Using static value", original_error)
                return value
                
        elif config.strategy == DegradationStrategy.ALTERNATIVE:
            # 使用备用服务
            if config.alternative_func:
                try:
                    result = config.alternative_func()
                    logger.info(f"Using alternative service for '{name}'")
                    self._stats["fallback_success"] += 1
                    if config.degradation_notice:
                        self._send_degradation_notice(name, "Using alternative service", original_error)
                    return result
                except Exception as alt_e:
                    logger.error(f"Alternative service also failed: {alt_e}")
                    
        elif config.strategy == DegradationStrategy.PARTIAL:
            # 返回部分数据
            if config.partial_data_provider:
                try:
                    result = config.partial_data_provider()
                    logger.info(f"Using partial data for '{name}'")
                    self._stats["fallback_success"] += 1
                    if config.degradation_notice:
                        self._send_degradation_notice(name, "Using partial data", original_error)
                    return result
                except Exception as partial_e:
                    logger.error(f"Partial data provider failed: {partial_e}")
        
        self._stats["total_failures"] += 1
        raise DegradationFailedError(
            f"All fallback strategies failed for '{name}'"
        ) from original_error
    
    def _send_degradation_notice(self, name: str, message: str, error: Exception):
        """发送降级通知"""
        if name not in self._degradation_notices:
            self._degradation_notices[name] = True
            logger.warning(
                f"[DEGRADATION] Service '{name}' degraded: {message}. "
                f"Original error: {error}"
            )
    
    def clear_notice(self, name: str):
        """清除降级通知状态"""
        if name in self._degradation_notices:
            del self._degradation_notices[name]
    
    def reset_stats(self):
        """重置统计"""
        self._stats = {
            "total_calls": 0,
            "primary_success": 0,
            "fallback_success": 0,
            "total_failures": 0,
            "degradation_events": 0
        }


class DegradationFailedError(Exception):
    """降级失败异常"""
    pass


def fallback(
    strategy: DegradationStrategy = DegradationStrategy.CACHE,
    cache_ttl: float = 300.0,
    static_value: Any = None,
    alternative_func: Optional[Callable] = None,
    cache_key_func: Optional[Callable] = None
):
    """
    降级装饰器
    
    Args:
        strategy: 降级策略
        cache_ttl: 缓存有效期
        static_value: 静态默认值
        alternative_func: 备用函数
        cache_key_func: 缓存键生成函数
        
    使用示例:
        @fallback(strategy=DegradationStrategy.CACHE, cache_ttl=300)
        def get_market_data(symbol):
            return fetch_from_api(symbol)
            
        @fallback(
            strategy=DegradationStrategy.STATIC,
            static_value={"price": 0, "volume": 0}
        )
        def get_ticker(symbol):
            return fetch_ticker(symbol)
    """
    def decorator(func: Callable) -> Callable:
        manager = FallbackManager()
        func_name = func.__name__
        
        # 注册策略
        config = FallbackConfig(
            strategy=strategy,
            cache_ttl=cache_ttl,
            static_value=static_value,
            alternative_func=alternative_func
        )
        manager.register_strategy(func_name, strategy, config)
        
        @wraps(func)
        def wrapper(*args, **kwargs):
            cache_key = None
            if cache_key_func:
                cache_key = cache_key_func(*args, **kwargs)
            
            return manager.execute(
                func_name,
                func,
                *args,
                cache_key=cache_key,
                **kwargs
            )
        
        return wrapper
    
    return decorator


class HistoricalDataFallback:
    """历史数据降级 - 当实时数据不可用时使用历史数据"""
    
    def __init__(self, history_retriever: Optional[Callable] = None):
        self.history_retriever = history_retriever
        self._cache = LocalCache(".history_cache")
    
    def get_with_fallback(
        self,
        realtime_func: Callable,
        symbol: str,
        max_age: float = 3600.0
    ) -> Dict[str, Any]:
        """
        获取数据，带历史数据降级
        
        Args:
            realtime_func: 获取实时数据的函数
            symbol: 交易标的
            max_age: 历史数据最大年龄（秒）
            
        Returns:
            数据字典，包含degraded标记
        """
        try:
            data = realtime_func()
            # 缓存结果
            self._cache.set(f"{symbol}:data", {
                "data": data,
                "timestamp": time.time(),
                "is_realtime": True
            })
            return {
                "data": data,
                "is_realtime": True,
                "degraded": False
            }
        except Exception as e:
            logger.warning(f"Realtime data fetch failed: {e}")
            
            # 尝试获取缓存数据
            cached = self._cache.get(f"{symbol}:data", max_age)
            if cached:
                age = time.time() - cached["timestamp"]
                logger.info(f"Using cached data for {symbol}, age: {age:.0f}s")
                return {
                    "data": cached["data"],
                    "is_realtime": False,
                    "degraded": True,
                    "data_age": age,
                    "warning": f"Using cached data ({age:.0f}s old)"
                }
            
            # 尝试使用历史数据获取器
            if self.history_retriever:
                try:
                    history_data = self.history_retriever(symbol)
                    return {
                        "data": history_data,
                        "is_realtime": False,
                        "degraded": True,
                        "source": "historical",
                        "warning": "Using historical data"
                    }
                except Exception as hist_e:
                    logger.error(f"Historical data fetch also failed: {hist_e}")
            
            raise DegradationFailedError("No data available")
