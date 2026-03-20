"""QuantForge Risk Management Module.

This module provides comprehensive risk management functionality for trading systems,
including position limits, stop-loss/take-profit management, circuit breakers,
VaR calculations, and anomaly detection.
"""

from .manager import RiskManager, RiskManagerConfig, RiskReport
from .limits import PositionLimits, PositionLimitConfig, LimitCheckResult, LimitCheckStatus
from .circuit_breaker import (
    CircuitBreaker, CircuitBreakerConfig, CircuitBreakerState,
    CircuitBreakerLevel, CircuitBreakerType
)
from .stop_loss import StopLossManager, StopLossConfig, StopLossResult, OrderSide
from .var import VaRCalculator, VaRResult, VaRMethod
from .anomaly import AnomalyDetector, AnomalyConfig, AnomalyResult, AnomalyType, AnomalySeverity

__version__ = "0.1.0"
__all__ = [
    "RiskManager",
    "RiskManagerConfig",
    "RiskReport",
    "PositionLimits",
    "PositionLimitConfig",
    "LimitCheckResult",
    "LimitCheckStatus",
    "CircuitBreaker",
    "CircuitBreakerConfig",
    "CircuitBreakerState",
    "CircuitBreakerLevel",
    "CircuitBreakerType",
    "StopLossManager",
    "StopLossConfig",
    "StopLossResult",
    "OrderSide",
    "VaRCalculator",
    "VaRResult",
    "VaRMethod",
    "AnomalyDetector",
    "AnomalyConfig",
    "AnomalyResult",
    "AnomalyType",
    "AnomalySeverity",
]
