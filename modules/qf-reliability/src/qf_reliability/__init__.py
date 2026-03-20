"""qf-reliability: QuantForge 可靠性模块

提供断路器、重试机制、优雅降级和健康检查功能
"""

from .circuit_breaker import CircuitBreaker, circuit_breaker, CircuitState, CircuitBreakerOpenError
from .retry import retry_with_backoff, RetryConfig, RetryStrategy, RetryExhaustedError, RetryManager
from .fallback import FallbackManager, fallback, DegradationStrategy, DegradationFailedError, LocalCache
from .chaos import ChaosEngine, chaos_test, FailureType, ChaosConfig, FaultInjector
from .health_check import (
    HealthChecker, HealthStatus, health_check, ServiceEndpoint, FailoverManager,
    HealthCheckResult
)

__version__ = "0.1.0"
__all__ = [
    # 断路器
    "CircuitBreaker",
    "circuit_breaker",
    "CircuitState",
    "CircuitBreakerOpenError",
    # 重试机制
    "retry_with_backoff",
    "RetryConfig",
    "RetryStrategy",
    "RetryExhaustedError",
    "RetryManager",
    # 优雅降级
    "FallbackManager",
    "fallback",
    "DegradationStrategy",
    "DegradationFailedError",
    "LocalCache",
    # 健康检查
    "HealthChecker",
    "HealthStatus",
    "health_check",
    "ServiceEndpoint",
    "FailoverManager",
    "HealthCheckResult",
    # 混沌测试
    "ChaosEngine",
    "chaos_test",
    "FailureType",
    "ChaosConfig",
    "FaultInjector",
]
