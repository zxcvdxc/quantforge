"""qf-reliability: QuantForge 可靠性模块

提供断路器、重试机制、优雅降级和健康检查功能
"""

from .circuit_breaker import CircuitBreaker, circuit_breaker, CircuitState
from .retry import retry_with_backoff, RetryConfig, RetryStrategy
from .fallback import FallbackManager, fallback, DegradationStrategy
from .health_check import HealthChecker, HealthStatus, health_check
from .chaos import ChaosEngine, chaos_test, FailureType

__version__ = "0.1.0"
__all__ = [
    # 断路器
    "CircuitBreaker",
    "circuit_breaker",
    "CircuitState",
    # 重试机制
    "retry_with_backoff",
    "RetryConfig",
    "RetryStrategy",
    # 优雅降级
    "FallbackManager",
    "fallback",
    "DegradationStrategy",
    # 健康检查
    "HealthChecker",
    "HealthStatus",
    "health_check",
    # 混沌测试
    "ChaosEngine",
    "chaos_test",
    "FailureType",
]
