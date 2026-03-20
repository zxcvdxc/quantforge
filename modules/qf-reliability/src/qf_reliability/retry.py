"""重试机制 (Retry Mechanism)

提供指数退避重试、可配置重试策略
"""
import time
import random
import logging
import asyncio
from enum import Enum, auto
from typing import Callable, Optional, Type, List, Dict, Any, Union, Tuple
from functools import wraps
from dataclasses import dataclass

logger = logging.getLogger(__name__)


class RetryStrategy(Enum):
    """重试策略"""
    FIXED = auto()           # 固定间隔
    EXPONENTIAL = auto()     # 指数退避
    LINEAR = auto()          # 线性增长
    RANDOM = auto()          # 随机间隔


@dataclass
class RetryConfig:
    """重试配置"""
    max_attempts: int = 3                    # 最大尝试次数
    base_delay: float = 1.0                  # 基础延迟（秒）
    max_delay: float = 60.0                  # 最大延迟（秒）
    strategy: RetryStrategy = RetryStrategy.EXPONENTIAL
    exponential_base: float = 2.0            # 指数基数
    jitter: bool = True                      # 是否添加随机抖动
    jitter_max: float = 0.1                  # 最大抖动比例
    retry_on_exceptions: Tuple[Type[Exception], ...] = (Exception,)
    retry_on_result: Optional[Callable[[Any], bool]] = None  # 根据结果判断是否需要重试
    on_retry: Optional[Callable[[Exception, int, float], None]] = None  # 重试回调
    on_giveup: Optional[Callable[[Exception], None]] = None  # 放弃回调
    
    def __post_init__(self):
        if isinstance(self.retry_on_exceptions, list):
            self.retry_on_exceptions = tuple(self.retry_on_exceptions)


class RetryManager:
    """重试管理器
    
    使用示例:
        # 方式1: 直接使用
        retry = RetryManager(max_attempts=5, base_delay=2.0)
        result = retry.execute(unreliable_func, *args)
        
        # 方式2: 装饰器
        @retry_with_backoff(max_attempts=5)
        def call_api(url):
            return requests.get(url)
    """
    
    def __init__(self, config: Optional[RetryConfig] = None, **kwargs):
        """
        初始化重试管理器
        
        Args:
            config: 重试配置对象
            **kwargs: 配置参数，覆盖config中的值
        """
        self.config = config or RetryConfig()
        
        # 用kwargs覆盖配置
        for key, value in kwargs.items():
            if hasattr(self.config, key):
                setattr(self.config, key, value)
        
        # 确保 retry_on_exceptions 是元组
        if isinstance(self.config.retry_on_exceptions, list):
            self.config.retry_on_exceptions = tuple(self.config.retry_on_exceptions)
        
        # 统计
        self._stats = {
            "total_attempts": 0,
            "successful": 0,
            "failed": 0,
            "retries": 0
        }
    
    @property
    def stats(self) -> Dict[str, Any]:
        """获取统计信息"""
        return self._stats.copy()
    
    def calculate_delay(self, attempt: int) -> float:
        """
        计算重试延迟
        
        Args:
            attempt: 当前尝试次数（从1开始）
            
        Returns:
            延迟秒数
        """
        config = self.config
        
        if config.strategy == RetryStrategy.FIXED:
            delay = config.base_delay
        elif config.strategy == RetryStrategy.EXPONENTIAL:
            delay = config.base_delay * (config.exponential_base ** (attempt - 1))
        elif config.strategy == RetryStrategy.LINEAR:
            delay = config.base_delay * attempt
        elif config.strategy == RetryStrategy.RANDOM:
            delay = random.uniform(0, config.base_delay * attempt)
        else:
            delay = config.base_delay
        
        # 应用最大延迟限制
        delay = min(delay, config.max_delay)
        
        # 添加抖动
        if config.jitter:
            jitter_amount = delay * config.jitter_max * random.uniform(-1, 1)
            delay = max(0, delay + jitter_amount)
        
        return delay
    
    def should_retry(self, exception: Exception, attempt: int) -> bool:
        """
        判断是否应重试
        
        Args:
            exception: 捕获的异常
            attempt: 当前尝试次数
            
        Returns:
            是否应重试
        """
        if attempt >= self.config.max_attempts:
            return False
        
        return isinstance(exception, self.config.retry_on_exceptions)
    
    def execute(self, func: Callable, *args, **kwargs) -> Any:
        """
        执行函数，带重试机制
        
        Args:
            func: 要执行的函数
            *args: 位置参数
            **kwargs: 关键字参数
            
        Returns:
            函数执行结果
            
        Raises:
            RetryExhaustedError: 重试次数用尽
            Exception: 最后一次尝试的异常
        """
        last_exception = None
        
        for attempt in range(1, self.config.max_attempts + 1):
            self._stats["total_attempts"] += 1
            
            try:
                result = func(*args, **kwargs)
                
                # 检查结果是否需要重试
                if self.config.retry_on_result and self.config.retry_on_result(result):
                    if attempt < self.config.max_attempts:
                        delay = self.calculate_delay(attempt)
                        logger.warning(
                            f"Retry {attempt}/{self.config.max_attempts} after {delay:.2f}s "
                            f"(result check failed)"
                        )
                        if self.config.on_retry:
                            self.config.on_retry(None, attempt, delay)
                        time.sleep(delay)
                        self._stats["retries"] += 1
                        continue
                
                self._stats["successful"] += 1
                return result
                
            except self.config.retry_on_exceptions as e:
                last_exception = e
                
                if not self.should_retry(e, attempt):
                    logger.error(f"Exception not retryable: {e}")
                    break
                
                if attempt >= self.config.max_attempts:
                    logger.error(f"Max attempts ({self.config.max_attempts}) reached")
                    break
                
                delay = self.calculate_delay(attempt)
                logger.warning(
                    f"Retry {attempt}/{self.config.max_attempts} after {delay:.2f}s: {e}"
                )
                
                if self.config.on_retry:
                    self.config.on_retry(e, attempt, delay)
                
                time.sleep(delay)
                self._stats["retries"] += 1
        
        self._stats["failed"] += 1
        
        if self.config.on_giveup:
            self.config.on_giveup(last_exception)
        
        raise RetryExhaustedError(
            f"Function failed after {self.config.max_attempts} attempts"
        ) from last_exception
    
    async def execute_async(self, func: Callable, *args, **kwargs) -> Any:
        """异步执行函数，带重试机制"""
        last_exception = None
        
        for attempt in range(1, self.config.max_attempts + 1):
            self._stats["total_attempts"] += 1
            
            try:
                if asyncio.iscoroutinefunction(func):
                    result = await func(*args, **kwargs)
                else:
                    result = func(*args, **kwargs)
                
                # 检查结果是否需要重试
                if self.config.retry_on_result and self.config.retry_on_result(result):
                    if attempt < self.config.max_attempts:
                        delay = self.calculate_delay(attempt)
                        logger.warning(
                            f"Retry {attempt}/{self.config.max_attempts} after {delay:.2f}s "
                            f"(result check failed)"
                        )
                        if self.config.on_retry:
                            self.config.on_retry(None, attempt, delay)
                        await asyncio.sleep(delay)
                        self._stats["retries"] += 1
                        continue
                
                self._stats["successful"] += 1
                return result
                
            except self.config.retry_on_exceptions as e:
                last_exception = e
                
                if not self.should_retry(e, attempt):
                    logger.error(f"Exception not retryable: {e}")
                    break
                
                if attempt >= self.config.max_attempts:
                    logger.error(f"Max attempts ({self.config.max_attempts}) reached")
                    break
                
                delay = self.calculate_delay(attempt)
                logger.warning(
                    f"Retry {attempt}/{self.config.max_attempts} after {delay:.2f}s: {e}"
                )
                
                if self.config.on_retry:
                    self.config.on_retry(e, attempt, delay)
                
                await asyncio.sleep(delay)
                self._stats["retries"] += 1
        
        self._stats["failed"] += 1
        
        if self.config.on_giveup:
            self.config.on_giveup(last_exception)
        
        raise RetryExhaustedError(
            f"Function failed after {self.config.max_attempts} attempts"
        ) from last_exception


class RetryExhaustedError(Exception):
    """重试次数用尽异常"""
    pass


def retry_with_backoff(
    max_attempts: int = 3,
    base_delay: float = 1.0,
    max_delay: float = 60.0,
    strategy: RetryStrategy = RetryStrategy.EXPONENTIAL,
    exponential_base: float = 2.0,
    jitter: bool = True,
    jitter_max: float = 0.1,
    retry_on_exceptions: Optional[List[Type[Exception]]] = None,
    retry_on_result: Optional[Callable[[Any], bool]] = None,
    on_retry: Optional[Callable[[Exception, int, float], None]] = None,
    on_giveup: Optional[Callable[[Exception], None]] = None
):
    """
    重试装饰器 - 指数退避
    
    Args:
        max_attempts: 最大尝试次数
        base_delay: 基础延迟（秒）
        max_delay: 最大延迟（秒）
        strategy: 重试策略
        exponential_base: 指数基数
        jitter: 是否添加随机抖动
        jitter_max: 最大抖动比例
        retry_on_exceptions: 需要重试的异常类型
        retry_on_result: 根据结果判断是否需要重试的函数
        on_retry: 重试回调函数
        on_giveup: 放弃回调函数
        
    使用示例:
        @retry_with_backoff(max_attempts=5, base_delay=2.0)
        def unreliable_function():
            # 可能失败的代码
            pass
            
        @retry_with_backoff(
            max_attempts=3,
            strategy=RetryStrategy.FIXED,
            retry_on_exceptions=[ConnectionError, TimeoutError]
        )
        async def async_function():
            # 异步代码
            pass
    """
    def decorator(func: Callable) -> Callable:
        config = RetryConfig(
            max_attempts=max_attempts,
            base_delay=base_delay,
            max_delay=max_delay,
            strategy=strategy,
            exponential_base=exponential_base,
            jitter=jitter,
            jitter_max=jitter_max,
            retry_on_exceptions=tuple(retry_on_exceptions or [Exception]),
            retry_on_result=retry_on_result,
            on_retry=on_retry,
            on_giveup=on_giveup
        )
        retry_manager = RetryManager(config)
        
        if asyncio.iscoroutinefunction(func):
            @wraps(func)
            async def async_wrapper(*args, **kwargs):
                return await retry_manager.execute_async(func, *args, **kwargs)
            async_wrapper._retry_manager = retry_manager
            return async_wrapper
        else:
            @wraps(func)
            def wrapper(*args, **kwargs):
                return retry_manager.execute(func, *args, **kwargs)
            wrapper._retry_manager = retry_manager
            return wrapper
    
    return decorator


def retry_fixed(
    max_attempts: int = 3,
    delay: float = 1.0,
    **kwargs
):
    """固定间隔重试装饰器"""
    return retry_with_backoff(
        max_attempts=max_attempts,
        base_delay=delay,
        strategy=RetryStrategy.FIXED,
        **kwargs
    )


def retry_linear(
    max_attempts: int = 3,
    base_delay: float = 1.0,
    max_delay: float = 60.0,
    **kwargs
):
    """线性增长重试装饰器"""
    return retry_with_backoff(
        max_attempts=max_attempts,
        base_delay=base_delay,
        max_delay=max_delay,
        strategy=RetryStrategy.LINEAR,
        **kwargs
    )
