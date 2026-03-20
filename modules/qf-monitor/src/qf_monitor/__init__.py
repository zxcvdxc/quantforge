"""QuantForge 监控报警模块

提供实时监控、异常检测和多种渠道报警功能。
支持批量检查、报警限流、报警风暴防护等高级特性。
"""

from .batch_processor import (
    AlertHistoryEntry,
    AlertRateLimiter,
    AlertRateLimitConfig,
    BatchCheckConfig,
    BatchCheckProcessor,
    BatchCheckResult,
    CheckPriority,
)
from .checks import (
    AccountCheck,
    CheckResult,
    DataDelayCheck,
    HealthCheck,
    OrderCheck,
    PositionCheck,
    StrategyCheck,
    DatabaseHealthCheck,
    SystemHealthCheck,
)
from .monitor import Monitor, MonitorConfig
from .alerts import Alert, AlertLevel, AlertManager

__version__ = "0.2.0"

__all__ = [
    # Monitor
    "Monitor",
    "MonitorConfig",
    # Checks
    "CheckResult",
    "HealthCheck",
    "AccountCheck",
    "PositionCheck",
    "OrderCheck",
    "StrategyCheck",
    "DataDelayCheck",
    "DatabaseHealthCheck",
    "SystemHealthCheck",
    # Alerts
    "Alert",
    "AlertLevel",
    "AlertManager",
    # Batch Processor
    "BatchCheckProcessor",
    "BatchCheckConfig",
    "BatchCheckResult",
    "CheckPriority",
    "AlertRateLimiter",
    "AlertRateLimitConfig",
    "AlertHistoryEntry",
]
