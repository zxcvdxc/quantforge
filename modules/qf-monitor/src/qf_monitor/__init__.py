"""QuantForge 监控报警模块

提供实时监控、异常检测和多种渠道报警功能。
"""

from .monitor import Monitor, MonitorConfig
from .checks import (
    CheckResult,
    AccountCheck,
    PositionCheck,
    OrderCheck,
    StrategyCheck,
    DataDelayCheck,
    HealthCheck,
)
from .alerts import Alert, AlertLevel, AlertManager

__version__ = "0.1.0"

__all__ = [
    # Monitor
    "Monitor",
    "MonitorConfig",
    # Checks
    "CheckResult",
    "AccountCheck",
    "PositionCheck",
    "OrderCheck",
    "StrategyCheck",
    "DataDelayCheck",
    "HealthCheck",
    # Alerts
    "Alert",
    "AlertLevel",
    "AlertManager",
]
