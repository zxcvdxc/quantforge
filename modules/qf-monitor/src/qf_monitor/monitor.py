"""监控核心模块

提供 Monitor 类和 MonitorConfig 配置类，实现实时监控、异常检测和报警功能。
"""

import asyncio
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Callable, Dict, List, Optional, Set, Type

import structlog

from .alerts import Alert, AlertLevel, AlertManager
from .checks import CheckResult, HealthCheck

logger = structlog.get_logger()


@dataclass
class MonitorConfig:
    """监控配置"""

    # 检查间隔（秒）
    check_interval: int = 30
    # 数据延迟阈值（秒）
    data_delay_threshold: int = 60
    # 健康检查阈值
    cpu_threshold: float = 80.0
    memory_threshold: float = 80.0
    disk_threshold: float = 90.0
    # 报警配置
    alert_cooldown: int = 300  # 报警冷却时间（秒）
    # 监控项开关
    enable_account_check: bool = True
    enable_position_check: bool = True
    enable_order_check: bool = True
    enable_strategy_check: bool = True
    enable_data_delay_check: bool = True
    enable_health_check: bool = True


class Monitor:
    """QuantForge 监控核心类

    提供实时监控、异常检测和报警功能。

    Example:
        >>> config = MonitorConfig(check_interval=30)
        >>> monitor = Monitor(config)
        >>> await monitor.start()
    """

    def __init__(self, config: Optional[MonitorConfig] = None):
        """初始化监控器

        Args:
            config: 监控配置，默认为 None 使用默认配置
        """
        self.config = config or MonitorConfig()
        self._running = False
        self._checks: List[HealthCheck] = []
        self._alert_manager = AlertManager()
        self._callbacks: Dict[str, List[Callable[[CheckResult], None]]] = {}
        self._alert_history: Dict[str, datetime] = {}
        self._stats: Dict[str, Any] = {
            "checks_total": 0,
            "checks_passed": 0,
            "checks_failed": 0,
            "alerts_sent": 0,
            "last_check": None,
        }
        self._lock = asyncio.Lock()

    def register_check(self, check: HealthCheck) -> None:
        """注册健康检查项

        Args:
            check: 健康检查实例
        """
        self._checks.append(check)
        logger.info(f"registered_check", check_type=check.__class__.__name__)

    def unregister_check(self, check_type: Type[HealthCheck]) -> bool:
        """注销健康检查项

        Args:
            check_type: 检查项类型

        Returns:
            是否成功移除
        """
        for i, check in enumerate(self._checks):
            if isinstance(check, check_type):
                del self._checks[i]
                logger.info(f"unregistered_check", check_type=check_type.__name__)
                return True
        return False

    def add_callback(
        self, event: str, callback: Callable[[CheckResult], None]
    ) -> None:
        """添加事件回调

        Args:
            event: 事件名称 ('check_passed', 'check_failed', 'alert_triggered')
            callback: 回调函数
        """
        if event not in self._callbacks:
            self._callbacks[event] = []
        self._callbacks[event].append(callback)

    def remove_callback(
        self, event: str, callback: Callable[[CheckResult], None]
    ) -> bool:
        """移除事件回调

        Args:
            event: 事件名称
            callback: 回调函数

        Returns:
            是否成功移除
        """
        if event in self._callbacks:
            try:
                self._callbacks[event].remove(callback)
                return True
            except ValueError:
                pass
        return False

    def _trigger_callbacks(self, event: str, result: CheckResult) -> None:
        """触发事件回调"""
        if event in self._callbacks:
            for callback in self._callbacks[event]:
                try:
                    callback(result)
                except Exception as e:
                    logger.error("callback_error", event_name=event, error_msg=str(e))

    async def check_once(self) -> List[CheckResult]:
        """执行一次检查

        Returns:
            所有检查项的结果列表
        """
        results: List[CheckResult] = []

        for check in self._checks:
            try:
                result = await check.check()
                results.append(result)

                async with self._lock:
                    self._stats["checks_total"] += 1
                    if result.is_healthy:
                        self._stats["checks_passed"] += 1
                        self._trigger_callbacks("check_passed", result)
                    else:
                        self._stats["checks_failed"] += 1
                        self._trigger_callbacks("check_failed", result)
                        await self._handle_alert(result)

            except Exception as e:
                logger.error(f"check_error", check_type=check.__class__.__name__, error=str(e))
                result = CheckResult(
                    name=check.__class__.__name__,
                    is_healthy=False,
                    message=f"检查执行异常: {str(e)}",
                    details={"error": str(e)},
                )
                results.append(result)

        self._stats["last_check"] = datetime.now().isoformat()
        return results

    async def _handle_alert(self, result: CheckResult) -> None:
        """处理报警

        Args:
            result: 检查结果
        """
        # 检查冷却时间
        now = datetime.now()
        if result.name in self._alert_history:
            last_alert = self._alert_history[result.name]
            if (now - last_alert).total_seconds() < self.config.alert_cooldown:
                return  # 冷却中，不发送

        # 确定报警级别
        level = self._determine_alert_level(result)

        # 创建并发送报警
        alert = Alert(
            level=level,
            title=f"[{result.name}] {result.message}",
            message=result.message,
            details=result.details,
            timestamp=now,
        )

        await self._alert_manager.send_alert(alert)
        self._alert_history[result.name] = now
        self._stats["alerts_sent"] += 1
        self._trigger_callbacks("alert_triggered", result)

        logger.warning(f"alert_sent", alert_level=level.value, check_name=result.name)

    def _determine_alert_level(self, result: CheckResult) -> AlertLevel:
        """根据检查结果确定报警级别

        Args:
            result: 检查结果

        Returns:
            报警级别
        """
        if not result.is_healthy:
            # 根据严重程度和类型判断
            severity = result.details.get("severity", "warning")
            if severity == "critical":
                return AlertLevel.CRITICAL
            elif severity == "error":
                return AlertLevel.ERROR
            elif severity == "warning":
                return AlertLevel.WARNING
        return AlertLevel.INFO

    async def start(self) -> None:
        """启动监控循环"""
        if self._running:
            return

        self._running = True
        logger.info("monitor_started", check_interval=self.config.check_interval)

        while self._running:
            try:
                await self.check_once()
            except Exception as e:
                logger.error(f"monitor_loop_error", error=str(e))

            # 等待下一次检查
            for _ in range(self.config.check_interval):
                if not self._running:
                    break
                await asyncio.sleep(1)

    def stop(self) -> None:
        """停止监控循环"""
        self._running = False
        logger.info("monitor_stopped")

    async def check_status(self) -> Dict[str, Any]:
        """获取监控状态

        Returns:
            监控状态字典
        """
        results = await self.check_once()
        return {
            "running": self._running,
            "checks": len(self._checks),
            "results": [
                {
                    "name": r.name,
                    "healthy": r.is_healthy,
                    "message": r.message,
                }
                for r in results
            ],
            "stats": self._stats.copy(),
        }

    def get_stats(self) -> Dict[str, Any]:
        """获取统计信息

        Returns:
            统计信息字典
        """
        return self._stats.copy()

    def add_notifier(self, name: str, notifier: Any) -> None:
        """添加通知器

        Args:
            name: 通知器名称
            notifier: 通知器实例
        """
        self._alert_manager.add_notifier(name, notifier)

    def remove_notifier(self, name: str) -> bool:
        """移除通知器

        Args:
            name: 通知器名称

        Returns:
            是否成功移除
        """
        return self._alert_manager.remove_notifier(name)

    @property
    def is_running(self) -> bool:
        """是否正在运行"""
        return self._running

    @property
    def registered_checks(self) -> List[str]:
        """已注册的检查项名称列表"""
        return [check.__class__.__name__ for check in self._checks]
