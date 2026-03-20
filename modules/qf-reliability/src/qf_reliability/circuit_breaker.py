"""断路器模式 (Circuit Breaker Pattern)

防止级联故障，自动检测服务健康状态并进行熔断/恢复
"""
import time
import logging
import threading
from enum import Enum, auto
from typing import Callable, Optional, Type, List, Dict, Any, Union
from functools import wraps
from dataclasses import dataclass

logger = logging.getLogger(__name__)


class CircuitState(Enum):
    """断路器状态"""
    CLOSED = auto()      # 关闭状态 - 正常通行
    OPEN = auto()        # 打开状态 - 熔断，拒绝请求
    HALF_OPEN = auto()   # 半开状态 - 尝试恢复


@dataclass
class CircuitBreakerConfig:
    """断路器配置"""
    failure_threshold: int = 5           # 失败阈值，超过则熔断
    success_threshold: int = 3           # 恢复阈值，连续成功次数
    timeout: float = 60.0                # 熔断后等待时间（秒）
    half_open_max_calls: int = 3         # 半开状态最大尝试次数
    expected_exceptions: Tuple[Type[Exception], ...] = (Exception,)  # 触发熔断的异常类型
    
    def __post_init__(self):
        if isinstance(self.expected_exceptions, list):
            self.expected_exceptions = tuple(self.expected_exceptions)


class CircuitBreaker:
    """断路器 - 防止级联故障
    
    状态流转:
    CLOSED -> OPEN: 失败次数 >= failure_threshold
    OPEN -> HALF_OPEN: 等待时间 >= timeout
    HALF_OPEN -> CLOSED: 成功次数 >= success_threshold
    HALF_OPEN -> OPEN: 任何失败
    
    使用示例:
        # 方式1: 直接使用
        breaker = CircuitBreaker("mysql", failure_threshold=5)
        result = breaker.call(db_query_func, *args)
        
        # 方式2: 装饰器
        @circuit_breaker(failure_threshold=5)
        def query_db(sql):
            return execute(sql)
    """
    
    _instances: Dict[str, "CircuitBreaker"] = {}
    _lock = threading.Lock()
    
    def __new__(cls, name: str, *args, **kwargs):
        """单例模式 - 同名断路器共享状态"""
        with cls._lock:
            if name not in cls._instances:
                instance = super().__new__(cls)
                cls._instances[name] = instance
            return cls._instances[name]
    
    def __init__(
        self,
        name: str,
        failure_threshold: int = 5,
        success_threshold: int = 3,
        timeout: float = 60.0,
        half_open_max_calls: int = 3,
        expected_exceptions: Optional[List[Type[Exception]]] = None,
        fallback_func: Optional[Callable] = None
    ):
        """
        初始化断路器
        
        Args:
            name: 断路器名称（唯一标识）
            failure_threshold: 失败阈值
            success_threshold: 恢复阈值
            timeout: 熔断后等待时间
            half_open_max_calls: 半开状态最大尝试次数
            expected_exceptions: 触发熔断的异常类型列表
            fallback_func: 熔断时的降级函数
        """
        # 避免重复初始化
        if hasattr(self, '_initialized'):
            return
        self._initialized = True
        
        self.name = name
        self.config = CircuitBreakerConfig(
            failure_threshold=failure_threshold,
            success_threshold=success_threshold,
            timeout=timeout,
            half_open_max_calls=half_open_max_calls,
            expected_exceptions=tuple(expected_exceptions or [Exception])
        )
        self.fallback_func = fallback_func
        
        # 状态
        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._success_count = 0
        self._half_open_calls = 0
        self._last_failure_time: Optional[float] = None
        self._state_lock = threading.RLock()
        
        # 统计
        self._stats = {
            "total_calls": 0,
            "success_calls": 0,
            "failure_calls": 0,
            "rejected_calls": 0,
            "state_changes": 0
        }
    
    @property
    def state(self) -> CircuitState:
        """获取当前状态"""
        with self._state_lock:
            self._try_transition()
            return self._state
    
    @property
    def stats(self) -> Dict[str, Any]:
        """获取统计信息"""
        with self._state_lock:
            return {
                **self._stats,
                "current_state": self._state.name,
                "failure_count": self._failure_count,
                "success_count": self._success_count,
                "half_open_calls": self._half_open_calls
            }
    
    def _try_transition(self):
        """尝试状态转换"""
        if self._state == CircuitState.OPEN:
            # 检查是否可以进入半开状态
            if self._last_failure_time is not None:
                elapsed = time.time() - self._last_failure_time
                if elapsed >= self.config.timeout:
                    logger.info(f"[{self.name}] Timeout reached, transitioning to HALF_OPEN")
                    self._state = CircuitState.HALF_OPEN
                    self._half_open_calls = 0
                    self._success_count = 0
                    self._stats["state_changes"] += 1
    
    def _on_success(self):
        """处理成功"""
        with self._state_lock:
            self._failure_count = 0
            
            if self._state == CircuitState.HALF_OPEN:
                self._success_count += 1
                self._half_open_calls += 1
                
                if self._success_count >= self.config.success_threshold:
                    logger.info(f"[{self.name}] Recovery successful, transitioning to CLOSED")
                    self._state = CircuitState.CLOSED
                    self._half_open_calls = 0
                    self._stats["state_changes"] += 1
            
            self._stats["success_calls"] += 1
    
    def _on_failure(self, exception: Exception):
        """处理失败"""
        with self._state_lock:
            self._failure_count += 1
            self._last_failure_time = time.time()
            
            if self._state == CircuitState.HALF_OPEN:
                logger.warning(f"[{self.name}] Failure in HALF_OPEN, transitioning to OPEN")
                self._state = CircuitState.OPEN
                self._stats["state_changes"] += 1
            elif self._state == CircuitState.CLOSED:
                if self._failure_count >= self.config.failure_threshold:
                    logger.error(
                        f"[{self.name}] Failure threshold reached ({self._failure_count}), "
                        f"transitioning to OPEN"
                    )
                    self._state = CircuitState.OPEN
                    self._stats["state_changes"] += 1
            
            self._stats["failure_calls"] += 1
    
    def _should_allow_call(self) -> bool:
        """检查是否允许调用"""
        with self._state_lock:
            self._try_transition()
            
            if self._state == CircuitState.CLOSED:
                return True
            elif self._state == CircuitState.OPEN:
                return False
            elif self._state == CircuitState.HALF_OPEN:
                if self._half_open_calls < self.config.half_open_max_calls:
                    self._half_open_calls += 1
                    return True
                return False
            return False
    
    def call(self, func: Callable, *args, **kwargs) -> Any:
        """
        执行被保护的函数
        
        Args:
            func: 要执行的函数
            *args: 位置参数
            **kwargs: 关键字参数
            
        Returns:
            函数执行结果
            
        Raises:
            CircuitBreakerOpenError: 断路器打开时
            Exception: 原函数抛出的异常
        """
        self._stats["total_calls"] += 1
        
        if not self._should_allow_call():
            self._stats["rejected_calls"] += 1
            logger.warning(f"[{self.name}] Call rejected - circuit is OPEN")
            
            if self.fallback_func:
                logger.info(f"[{self.name}] Executing fallback function")
                return self.fallback_func(*args, **kwargs)
            
            raise CircuitBreakerOpenError(f"Circuit breaker '{self.name}' is OPEN")
        
        try:
            result = func(*args, **kwargs)
            self._on_success()
            return result
        except self.config.expected_exceptions as e:
            self._on_failure(e)
            raise
    
    async def call_async(self, func: Callable, *args, **kwargs) -> Any:
        """异步执行被保护的函数"""
        import asyncio
        
        self._stats["total_calls"] += 1
        
        if not self._should_allow_call():
            self._stats["rejected_calls"] += 1
            logger.warning(f"[{self.name}] Call rejected - circuit is OPEN")
            
            if self.fallback_func:
                logger.info(f"[{self.name}] Executing fallback function")
                if asyncio.iscoroutinefunction(self.fallback_func):
                    return await self.fallback_func(*args, **kwargs)
                return self.fallback_func(*args, **kwargs)
            
            raise CircuitBreakerOpenError(f"Circuit breaker '{self.name}' is OPEN")
        
        try:
            if asyncio.iscoroutinefunction(func):
                result = await func(*args, **kwargs)
            else:
                result = func(*args, **kwargs)
            self._on_success()
            return result
        except self.config.expected_exceptions as e:
            self._on_failure(e)
            raise
    
    def reset(self):
        """手动重置断路器"""
        with self._state_lock:
            self._state = CircuitState.CLOSED
            self._failure_count = 0
            self._success_count = 0
            self._half_open_calls = 0
            self._last_failure_time = None
            logger.info(f"[{self.name}] Circuit breaker manually reset to CLOSED")


class CircuitBreakerOpenError(Exception):
    """断路器打开异常"""
    pass


def circuit_breaker(
    name: Optional[str] = None,
    failure_threshold: int = 5,
    success_threshold: int = 3,
    timeout: float = 60.0,
    half_open_max_calls: int = 3,
    expected_exceptions: Optional[List[Type[Exception]]] = None,
    fallback_func: Optional[Callable] = None
):
    """
    断路器装饰器
    
    Args:
        name: 断路器名称，默认为函数名
        failure_threshold: 失败阈值
        success_threshold: 恢复阈值
        timeout: 熔断后等待时间
        half_open_max_calls: 半开状态最大尝试次数
        expected_exceptions: 触发熔断的异常类型列表
        fallback_func: 熔断时的降级函数
        
    使用示例:
        @circuit_breaker(name="mysql_query", failure_threshold=5)
        def query_database(sql):
            return execute(sql)
            
        @circuit_breaker(name="api_call", timeout=30.0)
        async def fetch_data(url):
            return await aiohttp.get(url)
    """
    def decorator(func: Callable) -> Callable:
        breaker_name = name or func.__name__
        breaker = CircuitBreaker(
            name=breaker_name,
            failure_threshold=failure_threshold,
            success_threshold=success_threshold,
            timeout=timeout,
            half_open_max_calls=half_open_max_calls,
            expected_exceptions=expected_exceptions,
            fallback_func=fallback_func
        )
        
        if asyncio.iscoroutinefunction(func):
            @wraps(func)
            async def async_wrapper(*args, **kwargs):
                return await breaker.call_async(func, *args, **kwargs)
            async_wrapper._circuit_breaker = breaker
            return async_wrapper
        else:
            @wraps(func)
            def wrapper(*args, **kwargs):
                return breaker.call(func, *args, **kwargs)
            wrapper._circuit_breaker = breaker
            return wrapper
    
    return decorator


import asyncio
from typing import Tuple
