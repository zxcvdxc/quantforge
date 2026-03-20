"""混沌测试 (Chaos Engineering)

随机故障注入，测试系统容错能力和恢复能力
"""
import random
import asyncio
import logging
import inspect
from enum import Enum, auto
from typing import Callable, Optional, List, Dict, Any, Union, Type
from functools import wraps
from dataclasses import dataclass
from contextlib import contextmanager

logger = logging.getLogger(__name__)


class FailureType(Enum):
    """故障类型"""
    EXCEPTION = auto()           # 抛出异常
    DELAY = auto()               # 延迟响应
    TIMEOUT = auto()             # 超时
    RETURN_NONE = auto()         # 返回None
    RETURN_ERROR = auto()        # 返回错误值
    MEMORY_PRESSURE = auto()     # 内存压力（模拟）
    CPU_PRESSURE = auto()        # CPU压力（模拟）


@dataclass
class ChaosConfig:
    """混沌测试配置"""
    enabled: bool = True
    failure_rate: float = 0.1           # 故障率 (0-1)
    failure_types: List[FailureType] = None
    delay_min_ms: float = 100.0         # 最小延迟（毫秒）
    delay_max_ms: float = 5000.0        # 最大延迟（毫秒）
    exception_types: List[Type[Exception]] = None
    error_value: Any = None             # 错误返回值
    target_functions: List[str] = None  # 目标函数列表（None表示所有）
    
    def __post_init__(self):
        if self.failure_types is None:
            self.failure_types = [FailureType.EXCEPTION, FailureType.DELAY]
        if self.exception_types is None:
            self.exception_types = [Exception, RuntimeError, ConnectionError]


class ChaosEngine:
    """混沌引擎 - 故障注入
    
    使用示例:
        chaos = ChaosEngine(failure_rate=0.2)
        
        # 启用故障注入
        chaos.enable()
        
        # 在代码中标记可能被注入故障的点
        @chaos.inject(FailureType.EXCEPTION)
        def critical_function():
            return do_something()
            
        # 使用上下文管理器
        with chaos.session(failure_rate=0.5):
            result = unreliable_operation()
    """
    
    _instance = None
    
    def __new__(cls, *args, **kwargs):
        """单例模式"""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self, config: Optional[ChaosConfig] = None, **kwargs):
        if hasattr(self, '_initialized'):
            return
        self._initialized = True
        
        self.config = config or ChaosConfig()
        self._enabled = self.config.enabled
        
        # 统计
        self._stats = {
            "injected_failures": 0,
            "injected_delays": 0,
            "injected_timeouts": 0,
            "total_calls": 0
        }
    
    @property
    def enabled(self) -> bool:
        return self._enabled
    
    def enable(self):
        """启用故障注入"""
        self._enabled = True
        logger.warning("Chaos engineering enabled - failures will be injected!")
    
    def disable(self):
        """禁用故障注入"""
        self._enabled = False
        logger.info("Chaos engineering disabled")
    
    @property
    def stats(self) -> Dict[str, Any]:
        """获取统计信息"""
        return self._stats.copy()
    
    def should_inject(self, func_name: Optional[str] = None) -> bool:
        """判断是否应注入故障"""
        if not self._enabled:
            return False
        
        if self.config.target_functions and func_name:
            if func_name not in self.config.target_functions:
                return False
        
        return random.random() < self.config.failure_rate
    
    def inject_failure(self, failure_type: Optional[FailureType] = None):
        """注入故障"""
        if failure_type is None:
            failure_type = random.choice(self.config.failure_types)
        
        if failure_type == FailureType.EXCEPTION:
            exc_type = random.choice(self.config.exception_types)
            raise exc_type(f"Chaos: Injected {exc_type.__name__}")
        
        elif failure_type == FailureType.DELAY:
            delay_ms = random.uniform(self.config.delay_min_ms, self.config.delay_max_ms)
            logger.info(f"Chaos: Injecting delay of {delay_ms:.0f}ms")
            time.sleep(delay_ms / 1000)
        
        elif failure_type == FailureType.TIMEOUT:
            logger.info("Chaos: Injecting timeout")
            raise TimeoutError("Chaos: Injected timeout")
        
        elif failure_type == FailureType.RETURN_NONE:
            logger.info("Chaos: Returning None")
            return None
        
        elif failure_type == FailureType.RETURN_ERROR:
            logger.info(f"Chaos: Returning error value: {self.config.error_value}")
            return self.config.error_value
        
        elif failure_type == FailureType.MEMORY_PRESSURE:
            # 模拟内存压力 - 创建大对象
            logger.info("Chaos: Simulating memory pressure")
            _ = [0] * (10 ** 6)  # 临时大列表
        
        elif failure_type == FailureType.CPU_PRESSURE:
            # 模拟CPU压力 - 密集计算
            logger.info("Chaos: Simulating CPU pressure")
            for _ in range(10 ** 7):
                pass
    
    def inject(self, failure_type: Optional[FailureType] = None, failure_rate: Optional[float] = None):
        """
        故障注入装饰器
        
        Args:
            failure_type: 故障类型，None表示随机
            failure_rate: 故障率，None表示使用配置值
        """
        def decorator(func: Callable) -> Callable:
            rate = failure_rate if failure_rate is not None else self.config.failure_rate
            
            if asyncio.iscoroutinefunction(func):
                @wraps(func)
                async def async_wrapper(*args, **kwargs):
                    self._stats["total_calls"] += 1
                    
                    if self._enabled and random.random() < rate:
                        ft = failure_type or random.choice(self.config.failure_types)
                        self._inject_async(ft)
                    
                    return await func(*args, **kwargs)
                return async_wrapper
            else:
                @wraps(func)
                def wrapper(*args, **kwargs):
                    self._stats["total_calls"] += 1
                    
                    if self._enabled and random.random() < rate:
                        ft = failure_type or random.choice(self.config.failure_types)
                        
                        if ft == FailureType.DELAY:
                            delay_ms = random.uniform(
                                self.config.delay_min_ms,
                                self.config.delay_max_ms
                            )
                            logger.info(f"Chaos: Injecting delay of {delay_ms:.0f}ms")
                            import time
                            time.sleep(delay_ms / 1000)
                            self._stats["injected_delays"] += 1
                        elif ft == FailureType.EXCEPTION:
                            exc_type = random.choice(self.config.exception_types)
                            self._stats["injected_failures"] += 1
                            raise exc_type(f"Chaos: Injected {exc_type.__name__}")
                        elif ft == FailureType.TIMEOUT:
                            self._stats["injected_timeouts"] += 1
                            raise TimeoutError("Chaos: Injected timeout")
                        elif ft == FailureType.RETURN_NONE:
                            self._stats["injected_failures"] += 1
                            return None
                        elif ft == FailureType.RETURN_ERROR:
                            self._stats["injected_failures"] += 1
                            return self.config.error_value
                    
                    return func(*args, **kwargs)
                return wrapper
        
        return decorator
    
    def _inject_async(self, failure_type: FailureType):
        """异步故障注入"""
        if failure_type == FailureType.EXCEPTION:
            exc_type = random.choice(self.config.exception_types)
            self._stats["injected_failures"] += 1
            raise exc_type(f"Chaos: Injected {exc_type.__name__}")
        elif failure_type == FailureType.TIMEOUT:
            self._stats["injected_timeouts"] += 1
            raise TimeoutError("Chaos: Injected timeout")
    
    @contextmanager
    def session(self, **kwargs):
        """
        混沌测试会话上下文管理器
        
        使用示例:
            with chaos.session(failure_rate=0.5, enabled=True):
                result = operation()
        """
        # 保存原始配置
        old_config = {
            "enabled": self._enabled,
            "failure_rate": self.config.failure_rate,
            "failure_types": self.config.failure_types.copy(),
        }
        
        # 应用临时配置
        if "enabled" in kwargs:
            self._enabled = kwargs["enabled"]
        if "failure_rate" in kwargs:
            self.config.failure_rate = kwargs["failure_rate"]
        if "failure_types" in kwargs:
            self.config.failure_types = kwargs["failure_types"]
        
        try:
            yield self
        finally:
            # 恢复原始配置
            self._enabled = old_config["enabled"]
            self.config.failure_rate = old_config["failure_rate"]
            self.config.failure_types = old_config["failure_types"]


def chaos_test(
    failure_rate: float = 0.1,
    failure_types: Optional[List[FailureType]] = None,
    exception_types: Optional[List[Type[Exception]]] = None,
    enabled: bool = True
):
    """
    混沌测试装饰器
    
    Args:
        failure_rate: 故障率 (0-1)
        failure_types: 故障类型列表
        exception_types: 异常类型列表
        enabled: 是否启用
        
    使用示例:
        @chaos_test(failure_rate=0.2, failure_types=[FailureType.EXCEPTION])
        def test_function():
            return something()
    """
    config = ChaosConfig(
        enabled=enabled,
        failure_rate=failure_rate,
        failure_types=failure_types or [FailureType.EXCEPTION],
        exception_types=exception_types or [Exception]
    )
    engine = ChaosEngine(config)
    
    def decorator(func: Callable) -> Callable:
        return engine.inject()(func)
    
    return decorator


class FaultInjector:
    """故障注入器 - 细粒度控制故障注入"""
    
    def __init__(self):
        self._fault_points: Dict[str, Dict[str, Any]] = {}
    
    def register_fault_point(
        self,
        name: str,
        failure_rate: float = 0.0,
        failure_type: FailureType = FailureType.EXCEPTION,
        condition: Optional[Callable] = None
    ):
        """
        注册故障注入点
        
        Args:
            name: 注入点名称
            failure_rate: 故障率
            failure_type: 故障类型
            condition: 额外条件函数
        """
        self._fault_points[name] = {
            "failure_rate": failure_rate,
            "failure_type": failure_type,
            "condition": condition,
            "triggered": 0
        }
    
    def maybe_fail(self, name: str, context: Optional[Dict] = None):
        """
        在故障注入点尝试注入故障
        
        Args:
            name: 注入点名称
            context: 上下文信息
        """
        if name not in self._fault_points:
            return
        
        point = self._fault_points[name]
        
        # 检查条件
        if point["condition"] and not point["condition"](context):
            return
        
        # 随机决定是否注入故障
        if random.random() < point["failure_rate"]:
            point["triggered"] += 1
            self._inject(point["failure_type"])
    
    def _inject(self, failure_type: FailureType):
        """执行故障注入"""
        if failure_type == FailureType.EXCEPTION:
            raise RuntimeError(f"Injected fault: {failure_type.name}")
        elif failure_type == FailureType.DELAY:
            import time
            time.sleep(random.uniform(0.1, 1.0))
        elif failure_type == FailureType.TIMEOUT:
            raise TimeoutError("Injected timeout")
    
    def get_stats(self) -> Dict[str, Any]:
        """获取故障注入统计"""
        return {
            name: {
                "failure_rate": point["failure_rate"],
                "failure_type": point["failure_type"].name,
                "triggered": point["triggered"]
            }
            for name, point in self._fault_points.items()
        }


import time
