"""报警模块

提供报警管理和多种通知渠道支持。
"""

import asyncio
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional, Protocol

import structlog

logger = structlog.get_logger()


class AlertLevel(Enum):
    """报警级别"""

    DEBUG = "debug"
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"

    @property
    def priority(self) -> int:
        """获取优先级数值（越高越紧急）"""
        priorities = {
            AlertLevel.DEBUG: 0,
            AlertLevel.INFO: 1,
            AlertLevel.WARNING: 2,
            AlertLevel.ERROR: 3,
            AlertLevel.CRITICAL: 4,
        }
        return priorities.get(self, 1)


@dataclass
class Alert:
    """报警信息"""

    level: AlertLevel
    title: str
    message: str
    details: Dict[str, Any] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=datetime.now)
    alert_id: str = field(default_factory=lambda: f"{datetime.now().timestamp()}")

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "alert_id": self.alert_id,
            "level": self.level.value,
            "title": self.title,
            "message": self.message,
            "details": self.details,
            "timestamp": self.timestamp.isoformat(),
        }

    def format_message(self) -> str:
        """格式化报警消息"""
        lines = [
            f"【{self.level.value.upper()}】{self.title}",
            f"时间: {self.timestamp.strftime('%Y-%m-%d %H:%M:%S')}",
            f"消息: {self.message}",
        ]
        if self.details:
            lines.append("详情:")
            for key, value in self.details.items():
                if key != "severity":
                    lines.append(f"  {key}: {value}")
        return "\n".join(lines)


class Notifier(Protocol):
    """通知器协议"""

    async def send(self, alert: Alert) -> bool:
        """发送报警

        Args:
            alert: 报警信息

        Returns:
            是否发送成功
        """
        ...


class AlertManager:
    """报警管理器"""

    def __init__(self):
        """初始化报警管理器"""
        self._notifiers: Dict[str, Notifier] = {}
        self._min_level: AlertLevel = AlertLevel.INFO
        self._history: List[Alert] = []
        self._max_history: int = 1000

    def add_notifier(self, name: str, notifier: Notifier) -> None:
        """添加通知器

        Args:
            name: 通知器名称
            notifier: 通知器实例
        """
        self._notifiers[name] = notifier
        logger.info(f"notifier_added", name=name)

    def remove_notifier(self, name: str) -> bool:
        """移除通知器

        Args:
            name: 通知器名称

        Returns:
            是否成功移除
        """
        if name in self._notifiers:
            del self._notifiers[name]
            logger.info(f"notifier_removed", name=name)
            return True
        return False

    def set_min_level(self, level: AlertLevel) -> None:
        """设置最小报警级别

        Args:
            level: 最小报警级别
        """
        self._min_level = level

    async def send_alert(self, alert: Alert) -> Dict[str, bool]:
        """发送报警

        Args:
            alert: 报警信息

        Returns:
            各通知器发送结果
        """
        # 过滤低于最小级别的报警
        if alert.level.priority < self._min_level.priority:
            logger.debug(f"alert_filtered", level=alert.level.value)
            return {}

        # 保存到历史
        self._history.append(alert)
        if len(self._history) > self._max_history:
            self._history.pop(0)

        # 发送给所有通知器
        results = {}
        tasks = []

        for name, notifier in self._notifiers.items():
            task = asyncio.create_task(self._send_with_timeout(name, notifier, alert))
            tasks.append((name, task))

        for name, task in tasks:
            try:
                results[name] = await task
            except Exception as e:
                logger.error(f"notifier_failed", name=name, error=str(e))
                results[name] = False

        logger.info(
            f"alert_sent",
            level=alert.level.value,
            title=alert.title,
            results=results,
        )

        return results

    async def _send_with_timeout(
        self, name: str, notifier: Notifier, alert: Alert
    ) -> bool:
        """带超时的发送"""
        try:
            return await asyncio.wait_for(notifier.send(alert), timeout=10.0)
        except asyncio.TimeoutError:
            logger.error(f"notifier_timeout", name=name)
            return False
        except Exception as e:
            logger.error(f"notifier_error", name=name, error=str(e))
            return False

    def get_history(
        self,
        level: Optional[AlertLevel] = None,
        limit: int = 100,
    ) -> List[Alert]:
        """获取报警历史

        Args:
            level: 过滤级别
            limit: 返回数量限制

        Returns:
            报警历史列表
        """
        history = self._history
        if level:
            history = [a for a in history if a.level == level]
        return history[-limit:]

    def clear_history(self) -> None:
        """清空报警历史"""
        self._history.clear()

    def get_notifier_names(self) -> List[str]:
        """获取通知器名称列表"""
        return list(self._notifiers.keys())

    def has_notifiers(self) -> bool:
        """是否有配置通知器"""
        return len(self._notifiers) > 0
